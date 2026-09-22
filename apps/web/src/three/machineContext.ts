import { createContext, useContext } from 'react';

export type Vec3 = [number, number, number];

export interface MachineContextValue {
  /** Component health 0–100 by component `code` (§7.2); a missing code renders neutral. */
  health: Record<string, number | null | undefined>;
  /** Colour of structural (non-component) meshes: frame, base, columns. */
  housing: string;
  hovered?: string | null;
  onHover?: (code: string | null, point?: Vec3) => void;
}

export const MachineContext = createContext<MachineContextValue>({ health: {}, housing: '#3a4250' });

export function useMachine(): MachineContextValue {
  return useContext(MachineContext);
}

export const HOUSING_COLOR = { dark: '#3a4250', light: '#aab1bc' } as const;
