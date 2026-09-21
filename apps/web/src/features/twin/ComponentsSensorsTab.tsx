import { Table, type TableColumnsType } from 'antd';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { Component, Sensor } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { useComponents, useSensors } from '../../hooks/useAssets';
import { formatNumber } from '../../lib/format';
import { QueryView } from './QueryView';

interface Row extends Sensor {
  component: Component | undefined;
}

function range(low: number | null, high: number | null): string {
  if (low === null && high === null) return '—';
  return `${formatNumber(low, 2)} – ${formatNumber(high, 2)}`;
}

function SensorsTable({ components, sensors }: { components: Component[]; sensors: Sensor[] }) {
  const { t } = useTranslation();
  const rows = useMemo<Row[]>(() => {
    const byId = new Map(components.map((c) => [c.id, c]));
    return sensors.map((sensor) => ({
      ...sensor,
      component: sensor.component_id ? byId.get(sensor.component_id) : undefined,
    }));
  }, [components, sensors]);

  const columns: TableColumnsType<Row> = [
    {
      title: t('twin.sensors.component'),
      key: 'component',
      render: (_, row) => (row.component ? `${row.component.name} (${row.component.code})` : '—'),
      sorter: (a, b) => (a.component?.code ?? '').localeCompare(b.component?.code ?? ''),
      defaultSortOrder: 'ascend',
    },
    { title: t('twin.sensors.metric'), dataIndex: 'metric_name' },
    { title: t('twin.sensors.name'), dataIndex: 'name' },
    { title: t('twin.sensors.unit'), dataIndex: 'unit' },
    { title: t('twin.sensors.kind'), dataIndex: 'kind' },
    { title: t('twin.sensors.warn'), key: 'warn', align: 'right', render: (_, r) => range(r.warn_low, r.warn_high) },
    { title: t('twin.sensors.alarm'), key: 'alarm', align: 'right', render: (_, r) => range(r.alarm_low, r.alarm_high) },
  ];

  if (rows.length === 0) return <EmptyState description={t('twin.sensors.empty')} />;
  return <Table rowKey="id" size="small" columns={columns} dataSource={rows} pagination={false} scroll={{ x: 'max-content' }} />;
}

export function ComponentsSensorsTab({ assetId }: { assetId: string }) {
  const components = useComponents(assetId);
  const sensors = useSensors(assetId);
  return (
    <QueryView query={components}>
      {(componentList) => (
        <QueryView query={sensors}>
          {(sensorList) => <SensorsTable components={componentList} sensors={sensorList} />}
        </QueryView>
      )}
    </QueryView>
  );
}
