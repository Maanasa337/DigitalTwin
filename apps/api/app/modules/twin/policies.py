"""Ditto policies shared by all twins. Retiring a twin moves it to the read-only policy (FR-DT-01, FR-DT-10)."""

from typing import Any

ACTIVE_POLICY_ID = "twinvoice:active"
RETIRED_POLICY_ID = "twinvoice:retired"
THING_NAMESPACE = "twinvoice"

# Subjects use Ditto pre-authentication: the API forwards "pre:<subject>" on the internal network only.
SYSTEM_SUBJECT = "pre:twinvoice-api"
ROLE_SUBJECT = "pre:role-{role}"

_RW = {"grant": ["READ", "WRITE"], "revoke": []}
_R = {"grant": ["READ"], "revoke": []}


def _subjects(*names: str) -> dict[str, Any]:
    return {name: {"type": "twinvoice"} for name in names}


def _roles(*roles: str) -> dict[str, Any]:
    return _subjects(*(ROLE_SUBJECT.format(role=r) for r in roles))


ACTIVE_POLICY: dict[str, Any] = {
    "entries": {
        "system": {
            "subjects": _subjects(SYSTEM_SUBJECT),
            "resources": {"thing:/": _RW, "policy:/": _RW, "message:/": _RW},
        },
        "engineer": {
            "subjects": _roles("engineer", "admin"),
            "resources": {"thing:/": _RW, "message:/": _RW},
        },
        "reader": {
            "subjects": _roles("technician", "manager"),
            "resources": {"thing:/": _R, "message:/": _R},
        },
    }
}

RETIRED_POLICY: dict[str, Any] = {
    "entries": {
        "system": {"subjects": _subjects(SYSTEM_SUBJECT), "resources": {"thing:/": _R, "policy:/": _RW}},
        "reader": {
            "subjects": _roles("technician", "manager", "engineer", "admin"),
            "resources": {"thing:/": _R},
        },
    }
}


def thing_id(code: str) -> str:
    return f"{THING_NAMESPACE}:{code}"
