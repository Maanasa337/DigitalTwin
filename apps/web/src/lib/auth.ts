import Keycloak from 'keycloak-js';

import type { Role } from '../api/types';

export const ROLES: readonly Role[] = ['technician', 'manager', 'engineer', 'admin'];

export const authDisabled = import.meta.env.VITE_AUTH_DISABLED === 'true';

export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:8081',
  realm: 'twinvoice',
  clientId: 'twinvoice-web',
});

let initPromise: Promise<boolean> | null = null;

export function initAuth(): Promise<boolean> {
  initPromise ??= keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256', checkLoginIframe: false });
  return initPromise;
}

export async function getAccessToken(): Promise<string | undefined> {
  if (authDisabled) return undefined;
  try {
    await keycloak.updateToken(30);
  } catch {
    await keycloak.login();
    return undefined;
  }
  return keycloak.token;
}

export function login(): void {
  if (!authDisabled) void keycloak.login();
}

export function logout(): void {
  if (!authDisabled) void keycloak.logout({ redirectUri: window.location.origin });
}
