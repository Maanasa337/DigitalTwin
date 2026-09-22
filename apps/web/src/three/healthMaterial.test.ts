import { describe, expect, it } from 'vitest';

import { STATUS_PALETTE } from '../lib/status';
import { assetLevel, healthMaterial, worstLevel } from './healthMaterial';

describe('healthMaterial', () => {
  it.each([
    [100, 'good'],
    [80, 'good'],
    [79, 'warning'],
    [60, 'warning'],
    [59, 'serious'],
    [40, 'serious'],
    [39, 'critical'],
    [0, 'critical'],
  ] as const)('maps health %d to the %s status colour', (health, level) => {
    const material = healthMaterial(health);
    expect(material.level).toBe(level);
    expect(material.color).toBe(STATUS_PALETTE[level].color);
    expect(material.emissive).toBe(STATUS_PALETTE[level].color);
  });

  it('uses the neutral colour and no glow when health is unknown', () => {
    for (const health of [null, undefined]) {
      const material = healthMaterial(health);
      expect(material.level).toBe('neutral');
      expect(material.color).toBe(STATUS_PALETTE.neutral.color);
      expect(material.emissiveIntensity).toBe(0);
    }
  });

  it('glows harder as health worsens', () => {
    const glow = [90, 70, 50, 20].map((h) => healthMaterial(h).emissiveIntensity);
    expect([...glow].sort((a, b) => a - b)).toEqual(glow);
    expect(new Set(glow).size).toBe(glow.length);
  });
});

describe('assetLevel', () => {
  it('takes the worse of run state and health', () => {
    expect(assetLevel('RUNNING', 90)).toBe('good');
    expect(assetLevel('RUNNING', 30)).toBe('critical');
    expect(assetLevel('DOWN', 95)).toBe('critical');
    expect(assetLevel('MAINTENANCE', 70)).toBe('serious');
  });

  it('is neutral only when nothing is known', () => {
    expect(assetLevel(null, null)).toBe('neutral');
    expect(assetLevel('UNKNOWN', undefined)).toBe('neutral');
    expect(assetLevel(undefined, 85)).toBe('good');
  });

  it('ignores neutral when picking the worst level', () => {
    expect(worstLevel('neutral', 'warning')).toBe('warning');
    expect(worstLevel()).toBe('neutral');
  });
});
