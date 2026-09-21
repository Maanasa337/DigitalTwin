"""Keycloak JWT verification, role guards and the T3 second factor."""

import hmac
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import ForbiddenError, ServiceUnavailableError, UnauthorizedError

ROLES = frozenset({"technician", "manager", "engineer", "admin"})
WRITE_ROLES = ("engineer", "admin")


@dataclass(frozen=True)
class CurrentUser:
    sub: str
    name: str
    email: str | None
    roles: frozenset[str]

    def has_any(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


class TokenVerifier:
    def __init__(self, jwks_url: str, issuer: str, audience: str) -> None:
        self._jwks = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600, timeout=5)
        self._issuer = issuer
        self._audience = audience

    def ping(self) -> None:
        self._jwks.get_jwk_set()

    def verify(self, token: str) -> CurrentUser:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientConnectionError as exc:
            raise ServiceUnavailableError("Identity provider unreachable") from exc
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid token") from exc
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid or expired token") from exc
        return user_from_claims(claims)


def user_from_claims(claims: dict) -> CurrentUser:
    realm_roles = claims.get("realm_access", {}).get("roles", [])
    return CurrentUser(
        sub=claims["sub"],
        name=claims.get("name") or claims.get("preferred_username") or claims["sub"],
        email=claims.get("email"),
        roles=frozenset(realm_roles).intersection(ROLES),
    )


@lru_cache
def get_token_verifier() -> TokenVerifier:
    s = get_settings()
    return TokenVerifier(
        f"{s.keycloak_realm_url}/protocol/openid-connect/certs", s.keycloak_issuer, s.keycloak_client_id
    )


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> CurrentUser:
    if credentials is None:
        raise UnauthorizedError("Bearer token required")
    return verifier.verify(credentials.credentials)


def require_role(*roles: str) -> Callable[..., CurrentUser]:
    def guard(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.has_any(*roles):
            raise ForbiddenError(f"Requires one of the roles: {', '.join(roles)}")
        return user

    return guard


class SecondFactor:
    """Checks the PIN stored as Keycloak user attribute `tv_pin`; the PIN never travels inside a token."""

    def __init__(self, realm_url: str, admin_url: str, client_id: str, client_secret: str) -> None:
        self._token_url = f"{realm_url}/protocol/openid-connect/token"
        self._admin_url = admin_url
        self._client = (client_id, client_secret)
        self._token: tuple[str, float] | None = None
        self._lock = threading.Lock()

    def _service_token(self, http: httpx.Client) -> str:
        with self._lock:
            if self._token and self._token[1] > time.monotonic() + 10:
                return self._token[0]
            resp = http.post(
                self._token_url,
                data={"grant_type": "client_credentials"},
                auth=self._client,
            )
            resp.raise_for_status()
            body = resp.json()
            self._token = (body["access_token"], time.monotonic() + body["expires_in"])
            return self._token[0]

    def verify(self, sub: str, pin: str) -> bool:
        try:
            with httpx.Client(timeout=5) as http:
                token = self._service_token(http)
                resp = http.get(f"{self._admin_url}/users/{sub}", headers={"Authorization": f"Bearer {token}"})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("Identity provider unreachable") from exc
        stored = (resp.json().get("attributes") or {}).get("tv_pin") or []
        return bool(stored) and hmac.compare_digest(stored[0].encode(), pin.encode())


@lru_cache
def get_second_factor() -> SecondFactor:
    s = get_settings()
    return SecondFactor(
        s.keycloak_realm_url,
        f"{s.keycloak_internal_url}/admin/realms/{s.keycloak_realm}",
        s.keycloak_client_id,
        s.keycloak_client_secret,
    )
