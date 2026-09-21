import { createContext, useContext } from 'react';

import type { Role } from '../api/types';

export interface AuthUser {
  sub: string;
  name: string;
  email: string | null;
  roles: Role[];
}

export interface AuthContextValue {
  user: AuthUser;
  hasRole: (...roles: Role[]) => boolean;
  token: () => Promise<string | undefined>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}

export function makeAuthValue(
  user: AuthUser,
  token: AuthContextValue['token'],
  logout: AuthContextValue['logout'],
): AuthContextValue {
  return {
    user,
    hasRole: (...roles) => roles.some((role) => user.roles.includes(role)),
    token,
    logout,
  };
}
