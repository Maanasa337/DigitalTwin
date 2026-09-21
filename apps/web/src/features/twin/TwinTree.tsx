import { Flex, Input, Tree, Typography, type TreeDataNode } from 'antd';
import { useMemo, useState, type Key } from 'react';
import { useTranslation } from 'react-i18next';

import type { TwinTree as TwinTreeData } from '../../api/types';
import { HealthDot } from '../../components/HealthDot';
import { StatusTag } from '../../components/StatusTag';
import { FidelityBadge } from './FidelityBadge';
import { assetKey, buildNodes, collectKeys, filterNodes, type TwinNode } from './treeData';

function NodeTitle({ node }: { node: TwinNode }) {
  return (
    <Flex wrap gap={6} align="center" style={{ paddingBlock: 2 }}>
      <HealthDot health={node.item.health} />
      <span>{node.item.name}</span>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {node.item.code}
      </Typography.Text>
      {node.kind === 'asset' && (
        <>
          <StatusTag status={node.item.status} compact />
          <FidelityBadge level={node.item.fidelity_level} compact />
        </>
      )}
    </Flex>
  );
}

function toTreeData(nodes: TwinNode[]): TreeDataNode[] {
  return nodes.map((node) => ({
    key: node.key,
    title: <NodeTitle node={node} />,
    children: toTreeData(node.children),
    isLeaf: node.children.length === 0,
  }));
}

interface TwinTreeProps {
  tree: TwinTreeData;
  selectedCode: string | null;
  onSelect: (code: string) => void;
}

export function TwinTree({ tree, selectedCode, onSelect }: TwinTreeProps) {
  const { t } = useTranslation();
  const nodes = useMemo(() => buildNodes(tree), [tree]);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Key[]>(() => [
    ...collectKeys(nodes, (node) => node.kind !== 'asset'),
    ...(selectedCode ? [assetKey(selectedCode)] : []),
  ]);
  const visible = useMemo(() => filterNodes(nodes, query), [nodes, query]);
  const treeData = useMemo(() => toTreeData(visible), [visible]);
  const nodeByKey = useMemo(() => {
    const map = new Map<string, TwinNode>();
    const walk = (list: TwinNode[]) =>
      list.forEach((node) => {
        map.set(node.key, node);
        walk(node.children);
      });
    walk(nodes);
    return map;
  }, [nodes]);

  const search = (value: string) => {
    setQuery(value);
    if (value.trim()) setExpanded(collectKeys(filterNodes(nodes, value)));
  };

  const select = (keys: Key[]) => {
    const node = nodeByKey.get(String(keys[0]));
    if (node?.kind === 'asset') onSelect(node.item.code);
    else if (node?.kind === 'component') onSelect(node.asset.code);
  };

  return (
    <Flex vertical gap={12}>
      <Input.Search
        allowClear
        placeholder={t('twin.tree.search')}
        aria-label={t('twin.tree.search')}
        value={query}
        onChange={(e) => search(e.target.value)}
      />
      {treeData.length === 0 ? (
        <Typography.Text type="secondary">{t('twin.tree.noMatch')}</Typography.Text>
      ) : (
        <Tree
          blockNode
          showLine
          treeData={treeData}
          expandedKeys={expanded}
          onExpand={setExpanded}
          selectedKeys={selectedCode ? [assetKey(selectedCode)] : []}
          onSelect={select}
        />
      )}
    </Flex>
  );
}
