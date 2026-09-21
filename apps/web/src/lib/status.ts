import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExclamationCircleFilled,
  MinusCircleFilled,
  WarningFilled,
} from '@ant-design/icons';

import type { AssetStatus } from '../api/types';

export type StatusLevel = 'good' | 'warning' | 'serious' | 'critical' | 'neutral';

export const STATUS_PALETTE = {
  good: { color: '#0ca30c', lightText: '#006300', Icon: CheckCircleFilled },
  warning: { color: '#fab219', lightText: '#7a5200', Icon: ExclamationCircleFilled },
  serious: { color: '#ec835a', lightText: '#9c4012', Icon: WarningFilled },
  critical: { color: '#d03b3b', lightText: '#a02525', Icon: CloseCircleFilled },
  neutral: { color: '#898781', lightText: '#52514e', Icon: MinusCircleFilled },
} as const satisfies Record<StatusLevel, { color: string; lightText: string; Icon: unknown }>;

const ASSET_STATUS_LEVEL: Record<AssetStatus, StatusLevel> = {
  RUNNING: 'good',
  IDLE: 'warning',
  MAINTENANCE: 'serious',
  DOWN: 'critical',
  UNKNOWN: 'neutral',
};

export function assetStatusLevel(status: AssetStatus): StatusLevel {
  return ASSET_STATUS_LEVEL[status];
}

export function healthLevel(health: number | null | undefined): StatusLevel {
  if (health === null || health === undefined) return 'neutral';
  if (health >= 80) return 'good';
  if (health >= 60) return 'warning';
  if (health >= 40) return 'serious';
  return 'critical';
}

export function damageLevel(damage: number): StatusLevel {
  if (damage < 0.4) return 'good';
  if (damage < 0.6) return 'warning';
  if (damage < 0.8) return 'serious';
  return 'critical';
}

export function statusTextColor(level: StatusLevel, mode: 'dark' | 'light'): string {
  return mode === 'dark' ? STATUS_PALETTE[level].color : STATUS_PALETTE[level].lightText;
}

export function withAlpha(hex: string, alpha: number): string {
  const byte = Math.round(alpha * 255)
    .toString(16)
    .padStart(2, '0');
  return `${hex}${byte}`;
}
