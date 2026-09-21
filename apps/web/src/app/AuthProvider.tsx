import { Button, Result, Spin } from 'antd';
import type { KeycloakTokenParsed } from 'keycloak-js';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { Role } from '../api/types';
import { authDisabled, getAccessToken, initAuth, keycloak, logout, ROLES } from '../lib/auth';
import { AuthContext, makeAuthValue, type AuthContextValue, type AuthUser } from './authContext';

const DEV_USER: AuthUser = { sub: 'dev', name: 'Developer', email: null, roles: [...ROLES] };

interface TokenClaims extends KeycloakTokenParsed {
  name?: string;
  preferred_username?: string;
  email?: string;
}

function userFromToken(parsed: TokenClaims | undefined): AuthUser {
  const granted = parsed?.realm_access?.roles ?? [];
  return {
    sub: parsed?.sub ?? '',
    name: parsed?.name ?? parsed?.preferred_username ?? '',
    email: parsed?.email ?? null,
    roles: ROLES.filter((role): role is Role => granted.includes(role)),
  };
}

type AuthState = { kind: 'loading' } | { kind: 'ready'; value: AuthContextValue } | { kind: 'error' };

const initialState: AuthState = authDisabled
  ? { kind: 'ready', value: makeAuthValue(DEV_USER, getAccessToken, logout) }
  : { kind: 'loading' };

export function AuthProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [state, setState] = useState<AuthState>(initialState);

  useEffect(() => {
    if (authDisabled) return;
    let active = true;
    initAuth()
      .then((authenticated) => {
        if (!active || !authenticated) return;
        const user = userFromToken(keycloak.tokenParsed as TokenClaims | undefined);
        setState({ kind: 'ready', value: makeAuthValue(user, getAccessToken, logout) });
      })
      .catch(() => active && setState({ kind: 'error' }));
    return () => {
      active = false;
    };
  }, []);

  if (state.kind === 'loading') {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
        <Spin size="large" tip={t('auth.signingIn')}>
          <div style={{ width: 120, height: 80 }} />
        </Spin>
      </div>
    );
  }
  if (state.kind === 'error') {
    return (
      <Result
        status="error"
        title={t('auth.failed')}
        extra={
          <Button type="primary" onClick={() => window.location.reload()}>
            {t('common.retry')}
          </Button>
        }
      />
    );
  }
  return <AuthContext.Provider value={state.value}>{children}</AuthContext.Provider>;
}
