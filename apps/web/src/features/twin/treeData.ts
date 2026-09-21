import type { TreeAsset, TreeComponent, TreeLine, TreePlant, TwinTree } from '../../api/types';

export type TwinNode =
  | { kind: 'plant'; key: string; item: TreePlant; children: TwinNode[] }
  | { kind: 'line'; key: string; item: TreeLine; children: TwinNode[] }
  | { kind: 'asset'; key: string; item: TreeAsset; children: TwinNode[] }
  | { kind: 'component'; key: string; item: TreeComponent; asset: TreeAsset; children: TwinNode[] };

export function assetKey(code: string): string {
  return `asset:${code}`;
}

export function buildNodes(tree: TwinTree): TwinNode[] {
  return tree.plants.map((plant) => ({
    kind: 'plant',
    key: `plant:${plant.id}`,
    item: plant,
    children: plant.lines.map((line) => ({
      kind: 'line',
      key: `line:${line.id}`,
      item: line,
      children: line.assets.map((asset) => ({
        kind: 'asset',
        key: assetKey(asset.code),
        item: asset,
        children: asset.components.map((component) => ({
          kind: 'component',
          key: `component:${asset.code}:${component.id}`,
          item: component,
          asset,
          children: [],
        })),
      })),
    })),
  }));
}

function matches(node: TwinNode, query: string): boolean {
  return node.item.code.toLowerCase().includes(query) || node.item.name.toLowerCase().includes(query);
}

export function filterNodes(nodes: TwinNode[], rawQuery: string): TwinNode[] {
  const query = rawQuery.trim().toLowerCase();
  if (!query) return nodes;
  return nodes.flatMap((node) => {
    if (matches(node, query)) return [node];
    const children = filterNodes(node.children, query);
    return children.length ? [{ ...node, children }] : [];
  });
}

export function collectKeys(nodes: TwinNode[], predicate: (node: TwinNode) => boolean = () => true): string[] {
  return nodes.flatMap((node) => [
    ...(predicate(node) && node.children.length ? [node.key] : []),
    ...collectKeys(node.children, predicate),
  ]);
}

export function findAsset(tree: TwinTree, code: string | null): TreeAsset | undefined {
  if (!code) return undefined;
  for (const plant of tree.plants) {
    for (const line of plant.lines) {
      const asset = line.assets.find((a) => a.code === code);
      if (asset) return asset;
    }
  }
  return undefined;
}
