import { UndoOutlined } from '@ant-design/icons';
import { App, Button, Flex, Popconfirm, Progress, Table, Tag, Typography, type TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';

import { ASSET_STATUSES, type AssetStatus, type SimAsset } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { StatusTag } from '../../components/StatusTag';
import { useApiError } from '../../hooks/useApiError';
import { useResetSimAsset } from '../../hooks/useSimulation';
import { formatNumber } from '../../lib/format';
import { damageLevel, STATUS_PALETTE } from '../../lib/status';

export function toAssetStatus(state: string): AssetStatus {
  const upper = state.toUpperCase();
  return (ASSET_STATUSES as readonly string[]).includes(upper) ? (upper as AssetStatus) : 'UNKNOWN';
}

function DamageBars({ damage }: { damage: Record<string, number> }) {
  const entries = Object.entries(damage).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) return <Typography.Text type="secondary">—</Typography.Text>;
  return (
    <Flex vertical gap={2} style={{ minWidth: 200 }}>
      {entries.map(([component, value]) => {
        const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
        return (
          <Flex key={component} align="center" gap={8}>
            <Typography.Text style={{ width: 96, fontSize: 12 }} ellipsis={{ tooltip: component }}>
              {component}
            </Typography.Text>
            <Progress
              percent={pct}
              size="small"
              strokeColor={STATUS_PALETTE[damageLevel(value)].color}
              status="normal"
              format={(p) => `${p}%`}
              style={{ flex: 1, margin: 0 }}
              aria-label={`${component} ${pct}%`}
            />
          </Flex>
        );
      })}
    </Flex>
  );
}

function ResetAction({ code }: { code: string }) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const reset = useResetSimAsset();
  const onError = useApiError();
  return (
    <Popconfirm
      title={t('sim.fleet.resetTitle', { code })}
      description={t('sim.fleet.resetDescription')}
      okText={t('sim.fleet.reset')}
      cancelText={t('common.cancel')}
      onConfirm={() =>
        reset.mutateAsync(code).then(
          (res) =>
            void message.success(
              t('sim.fleet.resetDone', { code: res.asset, components: res.reset_components.join(', ') || '—' }),
            ),
          onError,
        )
      }
    >
      <Button size="small" icon={<UndoOutlined />} loading={reset.isPending}>
        {t('sim.fleet.reset')}
      </Button>
    </Popconfirm>
  );
}

export function FleetDamageTable({ assets }: { assets: SimAsset[] }) {
  const { t } = useTranslation();

  const columns: TableColumnsType<SimAsset> = [
    {
      title: t('sim.fleet.asset'),
      dataIndex: 'code',
      fixed: 'left',
      sorter: (a, b) => a.code.localeCompare(b.code),
      defaultSortOrder: 'ascend',
    },
    { title: t('sim.fleet.type'), dataIndex: 'asset_type', render: (type: string) => t(`assetType.${type}`, type) },
    { title: t('sim.fleet.line'), dataIndex: 'line_code' },
    {
      title: t('sim.fleet.state'),
      dataIndex: 'state',
      render: (state: string) => <StatusTag status={toAssetStatus(state)} compact />,
    },
    {
      title: t('sim.fleet.load'),
      dataIndex: 'load_pct',
      align: 'right',
      render: (v: number) => `${formatNumber(v)} %`,
    },
    { title: t('sim.fleet.damage'), key: 'damage', render: (_, row) => <DamageBars damage={row.damage} /> },
    {
      title: t('sim.fleet.trueRul'),
      dataIndex: 'true_rul_h',
      align: 'right',
      sorter: (a, b) => (a.true_rul_h ?? Infinity) - (b.true_rul_h ?? Infinity),
      render: (v: number | null) => (v === null ? '—' : `${formatNumber(v, 1)} h`),
    },
    {
      title: t('sim.fleet.modes'),
      key: 'modes',
      render: (_, row) =>
        row.active_modes.length ? (
          <Flex wrap gap={4}>
            {row.active_modes.map((m) => (
              <Tag key={`${m.failure_mode}-${m.started_at}`} color={m.mode === 'sudden' ? 'red' : 'orange'}>
                {m.failure_mode} · {t(`sim.mode.${m.mode}`)} · {formatNumber(m.severity, 2)}
              </Tag>
            ))}
          </Flex>
        ) : (
          '—'
        ),
    },
    {
      title: t('sim.fleet.sensorFaults'),
      key: 'faults',
      render: (_, row) =>
        row.sensor_faults.length ? (
          <Flex wrap gap={4}>
            {row.sensor_faults.map((f) => (
              <Tag key={`${f.metric}-${f.kind}`} color="purple">
                {f.metric} · {f.kind}
              </Tag>
            ))}
          </Flex>
        ) : (
          '—'
        ),
    },
    { title: t('sim.fleet.actions'), key: 'actions', fixed: 'right', render: (_, row) => <ResetAction code={row.code} /> },
  ];

  if (assets.length === 0) return <EmptyState description={t('sim.fleet.empty')} />;
  return (
    <Table<SimAsset>
      rowKey="code"
      size="small"
      columns={columns}
      dataSource={assets}
      pagination={false}
      scroll={{ x: 'max-content' }}
    />
  );
}
