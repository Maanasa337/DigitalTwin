import { Descriptions, Flex, Table, Typography, type TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';

import type { TelemetryValue, Twin } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { StatusTag } from '../../components/StatusTag';
import { useNow } from '../../hooks/useNow';
import { useTwin } from '../../hooks/useTwin';
import { ageSeconds, formatNumber } from '../../lib/format';
import { QueryView } from './QueryView';

interface TelemetryRow extends TelemetryValue {
  metric: string;
}

function formatValue(value: TelemetryValue['v']): string {
  if (typeof value === 'number') return formatNumber(value, Number.isInteger(value) ? 0 : 3);
  return value === null ? '—' : String(value);
}

function LiveTwinView({ twin }: { twin: Twin }) {
  const { t } = useTranslation();
  const now = useNow(1_000);
  const rows = Object.entries(twin.features.telemetry?.properties ?? {})
    .map(([metric, value]) => ({ metric, ...value }))
    .sort((a, b) => a.metric.localeCompare(b.metric));

  const columns: TableColumnsType<TelemetryRow> = [
    { title: t('twin.live.metric'), dataIndex: 'metric' },
    { title: t('twin.live.value'), key: 'v', align: 'right', render: (_, row) => formatValue(row.v) },
    { title: t('twin.live.unit'), dataIndex: 'u', render: (u: string | null) => u ?? '' },
    {
      title: t('twin.live.age'),
      key: 't',
      align: 'right',
      render: (_, row) => t('twin.live.ageValue', { count: ageSeconds(row.t, now) }),
    },
  ];

  return (
    <Flex vertical gap={16}>
      <Descriptions
        size="small"
        column={{ xs: 1, sm: 2, lg: 4 }}
        items={[
          { key: 'thing', label: t('twin.live.thing'), children: <Typography.Text code>{twin.thing_id}</Typography.Text> },
          { key: 'revision', label: t('twin.live.revision'), children: twin.revision },
          { key: 'status', label: t('twin.live.status'), children: <StatusTag status={twin.status} compact /> },
          { key: 'health', label: t('twin.live.health'), children: <StatusTag health={twin.health} compact /> },
        ]}
      />
      {rows.length === 0 ? (
        <EmptyState description={t('twin.live.empty')} />
      ) : (
        <Table rowKey="metric" size="small" columns={columns} dataSource={rows} pagination={false} />
      )}
    </Flex>
  );
}

export function LiveTwinTab({ code }: { code: string }) {
  const twin = useTwin(code);
  return <QueryView query={twin}>{(data) => <LiveTwinView twin={data} />}</QueryView>;
}
