import { AlertOutlined, AppstoreOutlined, SearchOutlined, TableOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Card, Col, Flex, Input, Row, Segmented, Select, Skeleton, Table, Tooltip, Typography, theme } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ASSET_STATUSES, type Asset, type AssetStatus, type LiveAsset } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { HealthGauge } from '../../components/HealthGauge';
import { PageHeader } from '../../components/PageHeader';
import { RulBadge } from '../../components/RulBadge';
import { StatusTag } from '../../components/StatusTag';
import { useAssets } from '../../hooks/useAssets';
import { useLiveAssetFeed } from '../../hooks/useLiveFeed';
import { useActiveAlarmCounts } from '../../hooks/useTelemetry';
import { assetStatusLevel, STATUS_PALETTE } from '../../lib/status';
import { useLiveTwinStore } from '../../store/liveTwinStore';
import { QueryView } from '../twin/QueryView';

type ViewMode = 'card' | 'table';

/**
 * Fleet overview (§9.7 `/`) — card grid or table of every machine with live status, health and RUL.
 */
export default function Fleet() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const assetsQuery = useAssets({ size: 200 });
  const liveAssets = useLiveTwinStore((s) => s.assets);
  const alarmCounts = useActiveAlarmCounts();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<AssetStatus | 'ALL'>('ALL');
  const [viewMode, setViewMode] = useState<ViewMode>('card');

  const all = assetsQuery.data?.items;
  useLiveAssetFeed(useMemo(() => (all ?? []).map(({ id, code }) => ({ id, code })), [all]));

  const assets = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (all ?? []).filter(
      (a) =>
        (!q || a.name.toLowerCase().includes(q) || a.code.toLowerCase().includes(q)) &&
        (statusFilter === 'ALL' || (liveAssets[a.code]?.status ?? a.status) === statusFilter),
    );
  }, [all, search, statusFilter, liveAssets]);

  const open = (code: string) => navigate(`/machines/${code}`);
  const alarmsFor = (asset: Asset) => Math.max(liveAssets[asset.code]?.alarm_count ?? 0, alarmCounts[asset.id] ?? 0);

  const toolbar = (
    <>
      <Input
        placeholder={t('fleet.search')}
        aria-label={t('fleet.search')}
        prefix={<SearchOutlined aria-hidden />}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        allowClear
        style={{ width: 220 }}
      />
      <Select
        value={statusFilter}
        onChange={setStatusFilter}
        aria-label={t('fleet.statusFilter')}
        style={{ width: 160 }}
        options={[
          { label: t('fleet.allStatuses'), value: 'ALL' },
          ...ASSET_STATUSES.map((s) => ({ label: t(`status.asset.${s}`), value: s })),
        ]}
      />
      <Segmented<ViewMode>
        value={viewMode}
        onChange={setViewMode}
        aria-label={t('fleet.view')}
        options={[
          { value: 'card', icon: <AppstoreOutlined />, title: t('fleet.cards') },
          { value: 'table', icon: <TableOutlined />, title: t('fleet.table') },
        ]}
      />
    </>
  );

  return (
    <>
      <PageHeader title={t('fleet.title')} subtitle={t('fleet.subtitle')} actions={toolbar} />
      {assetsQuery.isPending ? (
        <Row gutter={[16, 16]}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Col key={i} xs={24} sm={12} lg={8} xl={6}>
              <Card>
                <Skeleton active paragraph={{ rows: 3 }} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : (
        <QueryView query={assetsQuery}>
          {() =>
            assets.length === 0 ? (
              <EmptyState description={t('fleet.empty')} />
            ) : viewMode === 'card' ? (
              <Row gutter={[16, 16]}>
                {assets.map((asset) => (
                  <Col key={asset.id} xs={24} sm={12} lg={8} xl={6}>
                    <FleetCard asset={asset} live={liveAssets[asset.code]} alarms={alarmsFor(asset)} onOpen={open} />
                  </Col>
                ))}
              </Row>
            ) : (
              <Table<Asset>
                rowKey="id"
                size="small"
                dataSource={assets}
                pagination={false}
                onRow={(row) => ({ onClick: () => open(row.code), style: { cursor: 'pointer' } })}
                columns={[
                  {
                    title: t('fleet.machine'),
                    dataIndex: 'name',
                    render: (name: string, row) => (
                      <Flex vertical>
                        <Typography.Text strong>{name}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {row.code} · {t(`assetType.${row.asset_type}`, { defaultValue: row.asset_type })}
                        </Typography.Text>
                      </Flex>
                    ),
                  },
                  {
                    title: t('fleet.status'),
                    key: 'status',
                    width: 150,
                    render: (_: unknown, row) => <StatusTag status={liveAssets[row.code]?.status ?? row.status} compact />,
                  },
                  {
                    title: t('fleet.health'),
                    key: 'health',
                    width: 130,
                    render: (_: unknown, row) => <StatusTag health={liveAssets[row.code]?.health ?? null} compact />,
                  },
                  {
                    title: t('fleet.rul'),
                    key: 'rul',
                    render: (_: unknown, row) => {
                      const live = liveAssets[row.code];
                      return <RulBadge point={live?.rul_point} low={live?.rul_low} high={live?.rul_high} />;
                    },
                  },
                  {
                    title: t('fleet.alarms'),
                    key: 'alarms',
                    width: 90,
                    align: 'right',
                    render: (_: unknown, row) => <span className="tabular">{alarmsFor(row)}</span>,
                  },
                ]}
                style={{ background: token.colorBgContainer }}
              />
            )
          }
        </QueryView>
      )}
    </>
  );
}

interface FleetCardProps {
  asset: Asset;
  live?: LiveAsset;
  alarms: number;
  onOpen: (code: string) => void;
}

function FleetCard({ asset, live, alarms, onOpen }: FleetCardProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const status = live?.status ?? asset.status;
  const statusColor = STATUS_PALETTE[assetStatusLevel(status)].color;
  const power = live?.metrics?.power_kw?.v;

  return (
    <Card
      hoverable
      role="link"
      tabIndex={0}
      aria-label={t('fleet.openMachine', { name: asset.name })}
      onClick={() => onOpen(asset.code)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(asset.code);
        }
      }}
      style={{ borderInlineStart: `3px solid ${statusColor}`, cursor: 'pointer' }}
      styles={{ body: { padding: '16px 18px' } }}
    >
      <Flex justify="space-between" align="flex-start" gap={8} style={{ marginBottom: 12 }}>
        <Flex vertical style={{ minWidth: 0 }}>
          <Typography.Text strong style={{ fontSize: 15 }} ellipsis>
            {asset.name}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {asset.code} · {t(`assetType.${asset.asset_type}`, { defaultValue: asset.asset_type })}
          </Typography.Text>
        </Flex>
        <StatusTag status={status} compact />
      </Flex>

      <Flex align="center" gap={16} style={{ marginBottom: 8 }}>
        <HealthGauge health={live?.health ?? null} size={56} />
        <RulBadge point={live?.rul_point ?? null} low={live?.rul_low ?? null} high={live?.rul_high ?? null} />
      </Flex>

      <Flex justify="space-between" align="center" style={{ fontSize: 12, color: token.colorTextSecondary }}>
        <Tooltip title={t('fleet.activeAlarms')}>
          <Flex gap={4} align="center" aria-label={t('fleet.alarmCount', { count: alarms })}>
            <AlertOutlined
              aria-hidden
              style={{ color: alarms > 0 ? STATUS_PALETTE.critical.color : token.colorTextTertiary }}
            />
            <span className="tabular">{alarms}</span>
          </Flex>
        </Tooltip>
        {typeof power === 'number' && (
          <Tooltip title={t('fleet.power')}>
            <Flex gap={4} align="center" className="tabular">
              <ThunderboltOutlined aria-hidden />
              <span>{power.toFixed(1)} kW</span>
            </Flex>
          </Tooltip>
        )}
      </Flex>
    </Card>
  );
}
