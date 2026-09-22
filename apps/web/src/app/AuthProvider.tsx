import { ReloadOutlined, WarningFilled } from '@ant-design/icons';
import { Button, Flex, Spin, theme, Typography } from 'antd';
import type { KeycloakTokenParsed } from 'keycloak-js';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { Role } from '../api/types';
import { BrandMark } from '../components/BrandMark';
import { authDisabled, getAccessToken, initAuth, keycloak, logout, ROLES } from '../lib/auth';
import { STATUS_PALETTE } from '../lib/status';
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
      <Splash>
        <Flex vertical align="center" gap={12} role="status" aria-live="polite">
          <Spin size="large" />
          <Typography.Text type="secondary">{t('auth.signingIn')}</Typography.Text>
        </Flex>
      </Splash>
    );
  }
  if (state.kind === 'error') {
    return (
      <Splash>
        <Flex vertical align="center" gap={12} role="alert" style={{ maxWidth: 360 }}>
          <WarningFilled aria-hidden style={{ fontSize: 28, color: STATUS_PALETTE.critical.color }} />
          <Typography.Text strong style={{ fontSize: 16 }}>
            {t('auth.failedTitle')}
          </Typography.Text>
          <Typography.Text type="secondary">{t('auth.failed')}</Typography.Text>
          <Button type="primary" icon={<ReloadOutlined />} autoFocus onClick={() => window.location.reload()}>
            {t('common.retry')}
          </Button>
        </Flex>
      </Splash>
    );
  }
  return <AuthContext.Provider value={state.value}>{children}</AuthContext.Provider>;
}

/** Full-screen brand card shown before the app shell exists (no router, no query client yet). */
function Splash({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  return (
    <main
      style={{
        display: 'grid',
        placeItems: 'center',
        minHeight: '100vh',
        padding: 16,
        background: token.colorBgLayout,
      }}
    >
      <Flex
        vertical
        align="center"
        gap={24}
        style={{
          width: '100%',
          maxWidth: 400,
          padding: '40px 32px',
          textAlign: 'center',
          background: token.colorBgContainer,
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 12,
          boxShadow: token.boxShadowTertiary,
        }}
      >
        <Flex vertical align="center" gap={8}>
          <BrandMark size={48} wordmark={false} />
          <Typography.Title level={1} style={{ margin: 0, fontSize: 28, fontWeight: 700 }}>
            TwinVoice
          </Typography.Title>
          <Typography.Text type="secondary">{t('auth.tagline')}</Typography.Text>
        </Flex>
        {children}
      </Flex>
    </main>
  );
}
