import type { AssetPosition, AssetType, TwinTree } from '../api/types';

/** Grid pitch in metres when an asset has no stored floor position: machines along a line, lines apart. */
export const GRID_PITCH = { x: 6, z: 8 } as const;

export interface LayoutAsset {
  code: string;
  position: AssetPosition | null;
  /** Index of the asset's line across the whole plant. */
  line: number;
  /** Order of the asset within its line. */
  sequence: number;
}

export interface Placement {
  code: string;
  x: number;
  y: number;
  z: number;
  rot: number;
}

export interface LayoutBounds {
  cx: number;
  cz: number;
  width: number;
  depth: number;
  /** Half the diagonal: enough to frame every machine from a camera on the diagonal. */
  radius: number;
}

/**
 * Places each asset on the floor. A stored `position` wins; otherwise the asset goes on a grid with
 * one row per line, each row centred on x = 0 and the rows centred on z = 0.
 */
export function layoutAssets(assets: LayoutAsset[]): Placement[] {
  const perLine = new Map<number, number>();
  for (const asset of assets) perLine.set(asset.line, Math.max(perLine.get(asset.line) ?? 0, asset.sequence + 1));
  const lines = [...perLine.keys()].sort((a, b) => a - b);
  const row = new Map(lines.map((line, index) => [line, index]));

  return assets.map(({ code, position, line, sequence }) => {
    if (position) return { code, x: position.x, y: position.y, z: position.z, rot: position.rot };
    const count = perLine.get(line) ?? 1;
    return {
      code,
      x: (sequence - (count - 1) / 2) * GRID_PITCH.x,
      y: 0,
      z: ((row.get(line) ?? 0) - (lines.length - 1) / 2) * GRID_PITCH.z,
      rot: 0,
    };
  });
}

/** Floor extent of the placements plus a margin, for sizing the floor and framing the camera. */
export function layoutBounds(placements: Placement[], margin = 4): LayoutBounds {
  if (placements.length === 0) return { cx: 0, cz: 0, width: margin * 2, depth: margin * 2, radius: margin };
  const xs = placements.map((p) => p.x);
  const zs = placements.map((p) => p.z);
  const [minX, maxX, minZ, maxZ] = [Math.min(...xs), Math.max(...xs), Math.min(...zs), Math.max(...zs)];
  const width = maxX - minX + margin * 2;
  const depth = maxZ - minZ + margin * 2;
  return { cx: (minX + maxX) / 2, cz: (minZ + maxZ) / 2, width, depth, radius: Math.hypot(width, depth) / 2 };
}

export interface PlantAsset extends LayoutAsset {
  id: string;
  name: string;
  assetType: AssetType;
}

/** Flattens the plant → line → asset tree into layout input, numbering lines across plants. */
export function plantAssets(tree: TwinTree): PlantAsset[] {
  const out: PlantAsset[] = [];
  let line = 0;
  for (const plant of tree.plants) {
    for (const { assets } of plant.lines) {
      assets.forEach((asset, sequence) =>
        out.push({
          id: asset.id,
          code: asset.code,
          name: asset.name,
          assetType: asset.asset_type,
          position: asset.position ?? null,
          line,
          sequence,
        }),
      );
      line += 1;
    }
  }
  return out;
}
