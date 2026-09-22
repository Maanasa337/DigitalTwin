import type { AssetStatus } from '../api/types';
import { assetStatusLevel, healthLevel, STATUS_PALETTE, type StatusLevel } from '../lib/status';

export interface PartMaterial {
  level: StatusLevel;
  color: string;
  emissive: string;
  emissiveIntensity: number;
}

/** Worse bands glow harder, so a failing part reads from across the plant view. */
const GLOW: Record<StatusLevel, number> = { neutral: 0, good: 0.05, warning: 0.2, serious: 0.3, critical: 0.45 };

const SEVERITY: Record<StatusLevel, number> = { neutral: 0, good: 1, warning: 2, serious: 3, critical: 4 };

/** Health band → status colour (§9.2), used as both base and emissive colour of a component mesh. */
export function healthMaterial(health: number | null | undefined): PartMaterial {
  const level = healthLevel(health);
  const color = STATUS_PALETTE[level].color;
  return { level, color, emissive: color, emissiveIntensity: GLOW[level] };
}

export function worstLevel(...levels: StatusLevel[]): StatusLevel {
  return levels.reduce<StatusLevel>((worst, level) => (SEVERITY[level] > SEVERITY[worst] ? level : worst), 'neutral');
}

/** The plant view colours a machine by whichever is worse: its run state or its health band. */
export function assetLevel(status: AssetStatus | null | undefined, health: number | null | undefined): StatusLevel {
  return worstLevel(status ? assetStatusLevel(status) : 'neutral', healthLevel(health));
}
