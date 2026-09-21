import { describe, expect, it } from 'vitest';

import type { TwinTree } from '../../api/types';
import { buildNodes, collectKeys, filterNodes, findAsset } from './treeData';

const tree: TwinTree = {
  plants: [
    {
      id: 'p1',
      code: 'pune',
      name: 'Pune plant',
      health: 90,
      lines: [
        {
          id: 'l1',
          code: 'line-a',
          name: 'Line A',
          health: 88,
          assets: [
            {
              id: 'a1',
              code: 'cnc-01',
              name: 'CNC mill 1',
              asset_type: 'cnc_mill',
              status: 'RUNNING',
              fidelity_level: 3,
              health: null,
              components: [{ id: 'c1', code: 'spindle', name: 'Spindle', component_type: 'spindle', health: null, rul: null }],
            },
            {
              id: 'a2',
              code: 'comp-01',
              name: 'Compressor 1',
              asset_type: 'compressor',
              status: 'IDLE',
              fidelity_level: 2,
              health: 70,
              components: [],
            },
          ],
        },
      ],
    },
  ],
};

describe('twin tree data', () => {
  const nodes = buildNodes(tree);

  it('keeps ancestors of matching nodes when filtering', () => {
    const filtered = filterNodes(nodes, 'SPINDLE');
    expect(collectKeys(filtered)).toEqual(['plant:p1', 'line:l1', 'asset:cnc-01']);
    expect(filtered[0].children[0].children).toHaveLength(1);
  });

  it('matches by name and returns nothing for unknown queries', () => {
    expect(filterNodes(nodes, 'compressor')[0].children[0].children.map((n) => n.key)).toEqual(['asset:comp-01']);
    expect(filterNodes(nodes, 'zzz')).toEqual([]);
  });

  it('finds assets by code', () => {
    expect(findAsset(tree, 'comp-01')?.id).toBe('a2');
    expect(findAsset(tree, 'missing')).toBeUndefined();
    expect(findAsset(tree, null)).toBeUndefined();
  });
});
