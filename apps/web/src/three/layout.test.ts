import { describe, expect, it } from 'vitest';

import type { TreeAsset, TwinTree } from '../api/types';
import { GRID_PITCH, layoutAssets, layoutBounds, plantAssets } from './layout';

describe('layoutAssets', () => {
  it('uses the stored floor position when there is one', () => {
    const [placed] = layoutAssets([{ code: 'cnc-01', position: { x: 3, y: 0, z: -2, rot: 1.57 }, line: 0, sequence: 0 }]);
    expect(placed).toEqual({ code: 'cnc-01', x: 3, y: 0, z: -2, rot: 1.57 });
  });

  it('otherwise lays each line out as a centred row', () => {
    const placed = layoutAssets([
      { code: 'a', position: null, line: 0, sequence: 0 },
      { code: 'b', position: null, line: 0, sequence: 1 },
      { code: 'c', position: null, line: 0, sequence: 2 },
      { code: 'd', position: null, line: 1, sequence: 0 },
    ]);
    expect(placed.map((p) => p.x)).toEqual([-GRID_PITCH.x, 0, GRID_PITCH.x, 0]);
    expect(placed.map((p) => p.z)).toEqual([-GRID_PITCH.z / 2, -GRID_PITCH.z / 2, -GRID_PITCH.z / 2, GRID_PITCH.z / 2]);
    expect(placed.every((p) => p.y === 0 && p.rot === 0)).toBe(true);
  });

  it('never stacks two unpositioned machines on the same spot', () => {
    const assets = Array.from({ length: 10 }, (_, i) => ({
      code: `m${i}`,
      position: null,
      line: i % 3,
      sequence: Math.floor(i / 3),
    }));
    const spots = new Set(layoutAssets(assets).map((p) => `${p.x},${p.z}`));
    expect(spots.size).toBe(10);
  });
});

describe('layoutBounds', () => {
  it('frames the placements with a margin', () => {
    const bounds = layoutBounds(
      [
        { code: 'a', x: -6, y: 0, z: -4, rot: 0 },
        { code: 'b', x: 6, y: 0, z: 4, rot: 0 },
      ],
      2,
    );
    expect(bounds).toMatchObject({ cx: 0, cz: 0, width: 16, depth: 12 });
    expect(bounds.radius).toBeCloseTo(10);
  });

  it('has a sensible default for an empty plant', () => {
    expect(layoutBounds([], 4)).toMatchObject({ cx: 0, cz: 0, width: 8, depth: 8 });
  });
});

describe('plantAssets', () => {
  const asset = (code: string): TreeAsset => ({
    id: code,
    code,
    name: code,
    asset_type: 'conveyor',
    status: 'RUNNING',
    fidelity_level: 2,
    health: null,
    position: null,
    model_3d_path: null,
    components: [],
  });

  it('numbers lines across plants and keeps the order within a line', () => {
    const tree: TwinTree = {
      plants: [
        {
          id: 'p1',
          code: 'p1',
          name: 'P1',
          health: null,
          lines: [{ id: 'l1', code: 'l1', name: 'L1', health: null, assets: [asset('a'), asset('b')] }],
        },
        {
          id: 'p2',
          code: 'p2',
          name: 'P2',
          health: null,
          lines: [{ id: 'l2', code: 'l2', name: 'L2', health: null, assets: [asset('c')] }],
        },
      ],
    };
    expect(plantAssets(tree).map((a) => [a.code, a.line, a.sequence])).toEqual([
      ['a', 0, 0],
      ['b', 0, 1],
      ['c', 1, 0],
    ]);
  });
});
