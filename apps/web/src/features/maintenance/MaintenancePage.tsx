import { DownloadOutlined, PlusOutlined, ScheduleOutlined } from '@ant-design/icons';
import { App, Button, Card, Flex, Segmented, Select, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { exportWorkOrders } from '../../api/maintenance';
import type { WorkOrder, WorkOrderStatus, WorkOrderType } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { useApiError } from '../../hooks/useApiError';
import { useTechnicians, useWorkOrders } from '../../hooks/useMaintenance';
import { downloadBlob } from '../../lib/download';
import { formatDateTime } from '../../lib/format';
import { CreateWorkOrderModal } from './CreateWorkOrderModal';
import { WorkOrderDrawer } from './WorkOrderDrawer';
import { PriorityTag, RiskTag, StatusTagWo, TYPE_COLORS, VIA_LABELS, workOrderNumber } from './workOrderMeta';

const PAGE_SIZE = 20;

/** Work order list with filters, detail drawer, creation and export (FR-MS-01, FR-MS-06). */
export default function MaintenancePage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const onError = useApiError();

  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<WorkOrderStatus | undefined>();
  const [type, setType] = useState<WorkOrderType | undefined>();
  const [technicianId, setTechnicianId] = useState<string | undefined>();
  const [scope, setScope] = useState<'open' | 'all'>('open');
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const { data, isLoading } = useWorkOrders({
    page,
    size: PAGE_SIZE,
    status,
    type,
    technician_id: technicianId,
    open_only: scope === 'open' && !status,
  });
  const { data: technicians } = useTechnicians();
  const technicianNames = new Map((technicians?.items ?? []).map((tech) => [tech.id, tech.name]));

  const handleExport = async (format: 'csv' | 'json' | 'b2mml') => {
    try {
      const blob = await exportWorkOrders(format, { status });
      downloadBlob(blob, `work-orders.${format === 'b2mml' ? 'xml' : format}`);
      void message.success(t('maintenance.exported', 'Export downloaded'));
    } catch (err) {
      onError(err);
    }
  };

  const columns: ColumnsType<WorkOrder> = [
    {
      title: t('maintenance.number', 'Number'),
      dataIndex: 'number',
      width: 120,
      render: (v: number) => <span style={{ fontVariantNumeric: 'tabular-nums' }}>{workOrderNumber(v)}</span>,
    },
    {
      title: t('maintenance.titleField', 'Title'),
      dataIndex: 'title',
      ellipsis: true,
      render: (v: string, r) => (
        <Flex vertical gap={2}>
          <span style={{ fontWeight: 500 }}>{v}</span>
          <Tag style={{ marginInlineEnd: 0, width: 'fit-content' }} bordered={false}>
            {VIA_LABELS[r.created_via]}
          </Tag>
        </Flex>
      ),
    },
    {
      title: t('maintenance.type', 'Type'),
      dataIndex: 'type',
      width: 110,
      render: (v: WorkOrderType) => (
        <Tag color={TYPE_COLORS[v]} style={{ marginInlineEnd: 0 }}>
          {v}
        </Tag>
      ),
    },
    {
      title: t('maintenance.priority', 'Priority'),
      dataIndex: 'priority',
      width: 90,
      render: (v: number) => <PriorityTag priority={v} />,
    },
    {
      title: t('common.status', 'Status'),
      dataIndex: 'status',
      width: 120,
      render: (v: WorkOrderStatus) => <StatusTagWo status={v} />,
    },
    {
      title: t('maintenance.plannedStart', 'Planned'),
      dataIndex: 'planned_start',
      width: 170,
      render: (v: string | null) => formatDateTime(v),
    },
    {
      title: t('maintenance.technician', 'Technician'),
      dataIndex: 'technician_id',
      width: 150,
      render: (v: string | null) => (v ? (technicianNames.get(v) ?? '—') : '—'),
    },
    {
      title: t('maintenance.risk', 'Risk'),
      dataIndex: 'risk_before_slot',
      width: 100,
      align: 'right',
      render: (v: number | null) => <RiskTag risk={v} />,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title={t('maintenance.title', 'Maintenance')}
        subtitle={t('maintenance.subtitle', 'Work orders across the plant, with the risk of deferring each one.')}
        actions={
          <>
            <Select
              value="csv"
              style={{ width: 150 }}
              onChange={(v) => void handleExport(v as 'csv' | 'json' | 'b2mml')}
              suffixIcon={<DownloadOutlined />}
              options={[
                { value: 'csv', label: t('maintenance.exportCsv', 'Export CSV') },
                { value: 'json', label: t('maintenance.exportJson', 'Export JSON') },
                { value: 'b2mml', label: t('maintenance.exportB2mml', 'Export B2MML') },
              ]}
            />
            <Button icon={<ScheduleOutlined />} onClick={() => navigate('/maintenance/schedule')}>
              {t('maintenance.schedule', 'Schedule')}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
              {t('maintenance.newOrder', 'New work order')}
            </Button>
          </>
        }
      />

      <Card size="small">
        <Flex wrap gap={12} style={{ marginBottom: 12 }}>
          <Segmented
            value={scope}
            onChange={(v) => {
              setScope(v as 'open' | 'all');
              setPage(1);
            }}
            options={[
              { value: 'open', label: t('maintenance.openOnly', 'Open') },
              { value: 'all', label: t('common.all', 'All') },
            ]}
          />
          <Select
            allowClear
            style={{ minWidth: 150 }}
            placeholder={t('common.status', 'Status')}
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
            options={(['open', 'scheduled', 'in_progress', 'closed', 'cancelled'] as const).map((s) => ({
              value: s,
              label: s.replace(/_/g, ' '),
            }))}
          />
          <Select
            allowClear
            style={{ minWidth: 150 }}
            placeholder={t('maintenance.type', 'Type')}
            value={type}
            onChange={(v) => {
              setType(v);
              setPage(1);
            }}
            options={(['corrective', 'preventive', 'predictive'] as const).map((v) => ({
              value: v,
              label: v,
            }))}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ minWidth: 190 }}
            placeholder={t('maintenance.technician', 'Technician')}
            value={technicianId}
            onChange={(v) => {
              setTechnicianId(v);
              setPage(1);
            }}
            options={(technicians?.items ?? []).map((tech) => ({ value: tech.id, label: tech.name }))}
          />
        </Flex>

        <Table<WorkOrder>
          rowKey="id"
          size="small"
          loading={isLoading}
          columns={columns}
          dataSource={data?.items ?? []}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total: data?.total ?? 0,
            showSizeChanger: false,
            onChange: setPage,
          }}
          onRow={(record) => ({
            onClick: () => setSelected(record.id),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      <WorkOrderDrawer workOrderId={selected} onClose={() => setSelected(null)} />
      <CreateWorkOrderModal open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
