import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useSyncExternalStore, type RefObject } from 'react';
import type { Material, MeshStandardMaterial, Object3D } from 'three';

/** §9.4: alarm pulse on a 1.2 s loop. */
export const PULSE_PERIOD_S = 1.2;
const PULSE_GAIN = 0.9;
const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

function subscribeReducedMotion(onChange: () => void): () => void {
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  );
}

/** 0 → 1 → 0 over one period; a cosine so the glow eases in and out rather than blinking. */
export function pulseFactor(elapsedS: number): number {
  return 0.5 - 0.5 * Math.cos(((elapsedS % PULSE_PERIOD_S) / PULSE_PERIOD_S) * 2 * Math.PI);
}

function emissiveMaterials(root: Object3D | null, visit: (m: MeshStandardMaterial) => void): void {
  root?.traverse((node) => {
    const material = (node as Object3D & { material?: Material | Material[] }).material;
    for (const m of Array.isArray(material) ? material : material ? [material] : []) {
      if ('emissiveIntensity' in m) visit(m as MeshStandardMaterial);
    }
  });
}

/**
 * Pulses the emissive glow of every mesh under `ref` while `active` (an asset with open alarms).
 * The canvas renders on demand, so each pulsing frame requests the next one; nothing runs when idle.
 * Parts publish their resting intensity in `material.userData.baseIntensity`, which is restored when
 * the pulse stops. Disabled under `prefers-reduced-motion` (§9.9).
 */
export function useAlarmPulse(ref: RefObject<Object3D | null>, active: boolean): void {
  const reduced = usePrefersReducedMotion();
  const invalidate = useThree((state) => state.invalidate);
  const running = active && !reduced;

  useEffect(() => {
    if (!running) {
      emissiveMaterials(ref.current, (m) => {
        const base = m.userData.baseIntensity;
        if (typeof base === 'number') m.emissiveIntensity = base;
      });
    }
    invalidate();
  }, [running, invalidate, ref]);

  useFrame(({ clock }) => {
    if (!running) return;
    const k = pulseFactor(clock.getElapsedTime());
    emissiveMaterials(ref.current, (m) => {
      const base = typeof m.userData.baseIntensity === 'number' ? m.userData.baseIntensity : 0;
      m.emissiveIntensity = base + k * PULSE_GAIN;
    });
    invalidate();
  });
}
