import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons';
import { Button, Card, Col, Drawer, Row, Select, Space, Table, Tag, theme, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useMemo, useState } from 'react';

import type { Alarm, AlarmSeverity, AlarmStatus } from '../../api/types';
import { ackAlarm, bulkAckAlarms, shelveAlarm } from '../../api/telemetry';
import { useAlarms } from '../../hooks/useTelemetry';
import { formatDateTime, formatRelative } from '../../lib/format';

const { Text } = Typography;

const SEVERITY_COLORS: Record<AlarmSeverity, string> = {
  info: '#1890ff',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
};

const STATUS_ICONS: Record<AlarmStatus, React.ReactNode> = {
  active: <AlertOutlined style={{ color: '#d03b3b' }} />,
  acknowledged: <CheckCircleOutlined style={{ color: '#0ca30c' }} />,
  shelved: <PauseCircleOutlined style={{ color: '#898781' }} />,
  cleared: <ClockCircleOutlined style={{ color: '#898781' }} />,
};

/**
 * Alarms page — severity summary tiles, filterable table, row drawer for actions.
 */
export default function AlarmsPage() {
  const { token } = theme.useToken();
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState<AlarmSeverity | undefined>();
  const [status, setStatus] = useState<AlarmStatus | undefined>();
  const [selected, setSelected] = useState<string[]>([]);
  const [drawerAlarm, setDrawerAlarm] = useState<Alarm | null>(null);

  const { data, isLoading, refetch } = useAlarms({ page, size: 50, severity, status });

  const severityCounts = useMemo(() => {
    const counts: Record<AlarmSeverity, number> = { info: 0, warning: 0, serious: 0, critical: 0 };
    // Note: these are just the current page counts; for full counts, use a separate endpoint
    (data?.items ?? []).forEach((a) => counts[a.severity]++);
    return counts;
  }, [data?.items]);

  const handleBulkAck = async () => {
    if (selected.length > 0) {
      await bulkAckAlarms(selected);
      setSelected([]);
      refetch();
    }
  };

  const handleAck = async (id: string) => {
    await ackAlarm(id);
    setDrawerAlarm(null);
    refetch();
  };

  const handleShelve = async (id: string) => {
    await shelveAlarm(id);
    setDrawerAlarm(null);
    refetch();
  };

  const columns: ColumnsType<Alarm> = [
    {
      title: 'Time',
      dataIndex: 'raised_at',
      width: 170,
      render: (v: string) => <Text style={{ fontSize: 12 }}>{formatDateTime(v)}</Text>,
    },
    {
      title: 'Severity',
      dataIndex: 'severity',
      width: 100,
      render: (v: AlarmSeverity) => (
        <Tag color={SEVERITY_COLORS[v]} style={{ fontWeight: 600, textTransform: 'uppercase', fontSize: 11 }}>
          {v}
        </Tag>
      ),
    },
    {
      title: 'Title',
      dataIndex: 'title',
      ellipsis: true,
    },
    {
      title: 'Value / Threshold',
      width: 150,
      render: (_, r) =>
        r.value != null ? (
          <Text style={{ fontSize: 12 }}>
            {r.value.toFixed(2)} / {r.threshold?.toFixed(2) ?? '—'}
          </Text>
        ) : (
          '—'
        ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      width: 120,
      render: (v: AlarmStatus) => (
        <Space size={4}>
          {STATUS_ICONS[v]}
          <span style={{ fontSize: 12, textTransform: 'capitalize' }}>{v}</span>
        </Space>
      ),
    },
    {
      title: 'Age',
      dataIndex: 'raised_at',
      width: 100,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{formatRelative(v)}</Text>,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* Severity summary tiles */}
      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        {(['critical', 'serious', 'warning', 'info'] as const).map((sev) => (
          <Col key={sev} xs={12} sm={6}>
            <Card
              size="small"
              style={{
                borderLeft: `3px solid ${SEVERITY_COLORS[sev]}`,
                borderRadius: token.borderRadiusLG,
                cursor: 'pointer',
              }}
              onClick={() => setSeverity(severity === sev ? undefined : sev)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={{ textTransform: 'uppercase', fontSize: 12, fontWeight: 600 }}>{sev}</Text>
                <Text style={{ fontSize: 24, fontWeight: 700, color: SEVERITY_COLORS[sev] }}>
                  {severityCounts[sev]}
                </Text>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* Toolbar */}
      <Space style={{ marginBottom: 12 }}>
        <Select
          placeholder="Status"
          allowClear
          value={status}
          onChange={setStatus}
          style={{ width: 140 }}
          options={[
            { label: 'Active', value: 'active' },
            { label: 'Acknowledged', value: 'acknowledged' },
            { label: 'Shelved', value: 'shelved' },
            { label: 'Cleared', value: 'cleared' },
          ]}
        />
        {selected.length > 0 && (
          <Button type="primary" size="small" onClick={handleBulkAck}>
            Ack {selected.length} selected
          </Button>
        )}
      </Space>

      {/* Table */}
      <Table<Alarm>
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        pagination={{
          current: page,
          pageSize: 50,
          total: data?.total,
          onChange: setPage,
          showSizeChanger: false,
        }}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as string[]),
        }}
        onRow={(record) => ({
          onClick: () => setDrawerAlarm(record),
          style: { cursor: 'pointer' },
        })}
        size="small"
      />

      {/* Detail drawer */}
      <Drawer
        title={drawerAlarm?.title ?? 'Alarm'}
        open={Boolean(drawerAlarm)}
        onClose={() => setDrawerAlarm(null)}
        width={400}
      >
        {drawerAlarm && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <div>
              <Text type="secondary">Message</Text>
              <div>{drawerAlarm.message}</div>
            </div>
            <div>
              <Text type="secondary">Raised at</Text>
              <div>{formatDateTime(drawerAlarm.raised_at)}</div>
            </div>
            <div>
              <Text type="secondary">Status</Text>
              <div>
                <Space>
                  {STATUS_ICONS[drawerAlarm.status]}
                  <span style={{ textTransform: 'capitalize' }}>{drawerAlarm.status}</span>
                </Space>
              </div>
            </div>
            <Space>
              {drawerAlarm.status === 'active' && (
                <Button type="primary" size="small" onClick={() => handleAck(drawerAlarm.id)}>
                  Acknowledge
                </Button>
              )}
              {(drawerAlarm.status === 'active' || drawerAlarm.status === 'acknowledged') && (
                <Button size="small" onClick={() => handleShelve(drawerAlarm.id)}>
                  Shelve 4h
                </Button>
              )}
            </Space>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
