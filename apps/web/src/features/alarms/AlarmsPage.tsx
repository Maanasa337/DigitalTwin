import {
  AlertOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  InfoCircleFilled,
  PauseCircleOutlined,
} from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { App, Button, Card, Col, Descriptions, Drawer, Flex, Row, Select, Space, Table, Tag, Typography, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ackAlarm, bulkAckAlarms, shelveAlarm } from '../../api/telemetry';
import type { Alarm, AlarmSeverity, AlarmStatus } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { useApiError } from '../../hooks/useApiError';
import { useAlarmSeverityCounts, useAlarms } from '../../hooks/useTelemetry';
import { formatDateTime, formatRelative } from '../../lib/format';
import { STATUS_PALETTE, statusTextColor, withAlpha, type StatusLevel } from '../../lib/status';
import { useUiStore } from '../../store/uiStore';

const SEVERITIES: AlarmSeverity[] = ['critical', 'serious', 'warning', 'info'];
const STATUSES: AlarmStatus[] = ['active', 'acknowledged', 'shelved', 'cleared'];

/** Alarm severities map onto the status palette; `info` has no status colour and uses the brand primary. */
const SEVERITY_LEVEL: Record<AlarmSeverity, StatusLevel | null> = {
  critical: 'critical',
  serious: 'serious',
  warning: 'warning',
  info: null,
};

function useSeverityStyle() {
  const { token } = theme.useToken();
  const mode = useUiStore((s) => s.themeMode);
  return (severity: AlarmSeverity) => {
    const level = SEVERITY_LEVEL[severity];
    if (!level) return { color: token.colorPrimary, text: token.colorPrimary, Icon: InfoCircleFilled };
    const { color, Icon } = STATUS_PALETTE[level];
    return { color, text: statusTextColor(level, mode), Icon };
  };
}

function SeverityTag({ severity }: { severity: AlarmSeverity }) {
  const { t } = useTranslation();
  const style = useSeverityStyle()(severity);
  return (
    <Tag
      bordered={false}
      icon={<style.Icon aria-hidden />}
      style={{ background: withAlpha(style.color, 0.16), color: style.text, marginInlineEnd: 0 }}
    >
      {t(`alarms.severity.${severity}`)}
    </Tag>
  );
}

function StatusLabel({ status }: { status: AlarmStatus }) {
  const { t } = useTranslation();
  const icons: Record<AlarmStatus, ReactNode> = {
    active: <AlertOutlined aria-hidden style={{ color: STATUS_PALETTE.critical.color }} />,
    acknowledged: <CheckCircleOutlined aria-hidden style={{ color: STATUS_PALETTE.good.color }} />,
    shelved: <PauseCircleOutlined aria-hidden style={{ color: STATUS_PALETTE.neutral.color }} />,
    cleared: <ClockCircleOutlined aria-hidden style={{ color: STATUS_PALETTE.neutral.color }} />,
  };
  return (
    <Space size={4}>
      {icons[status]}
      <span>{t(`alarms.status.${status}`)}</span>
    </Space>
  );
}

/**
 * Alarms page (§9.7 `/alarms`) — severity summary tiles, filterable table, row drawer for actions.
 */
export default function AlarmsPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const queryClient = useQueryClient();
  const severityStyle = useSeverityStyle();
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState<AlarmSeverity | undefined>();
  const [status, setStatus] = useState<AlarmStatus | undefined>();
  const [selected, setSelected] = useState<string[]>([]);
  const [drawerAlarm, setDrawerAlarm] = useState<Alarm | null>(null);

  const { data, isLoading } = useAlarms({ page, size: 50, severity, status });
  const severityCounts = useAlarmSeverityCounts(SEVERITIES, status);

  const act = async (action: () => Promise<unknown>, done: string) => {
    try {
      await action();
      void message.success(done);
      setDrawerAlarm(null);
      // Prefix match: refreshes the table and the severity tiles together.
      void queryClient.invalidateQueries({ queryKey: ['alarms'] });
    } catch (err) {
      onError(err);
    }
  };

  const handleBulkAck = () =>
    act(() => bulkAckAlarms(selected), t('alarms.acked', { count: selected.length })).then(() => setSelected([]));

  const columns: ColumnsType<Alarm> = [
    { title: t('alarms.time'), dataIndex: 'raised_at', width: 170, render: (v: string) => formatDateTime(v) },
    {
      title: t('alarms.severityLabel'),
      dataIndex: 'severity',
      width: 130,
      render: (v: AlarmSeverity) => <SeverityTag severity={v} />,
    },
    { title: t('alarms.title'), dataIndex: 'title', ellipsis: true },
    {
      title: t('alarms.valueThreshold'),
      width: 150,
      align: 'right',
      render: (_, r) => (r.value != null ? `${r.value.toFixed(2)} / ${r.threshold?.toFixed(2) ?? '—'}` : '—'),
    },
    {
      title: t('alarms.statusLabel'),
      dataIndex: 'status',
      width: 150,
      render: (v: AlarmStatus) => <StatusLabel status={v} />,
    },
    {
      title: t('alarms.age'),
      dataIndex: 'raised_at',
      key: 'age',
      width: 120,
      render: (v: string) => <Typography.Text type="secondary">{formatRelative(v)}</Typography.Text>,
    },
  ];

  return (
    <>
      <PageHeader
        title={t('alarms.pageTitle')}
        subtitle={t('alarms.subtitle')}
        actions={
          <>
            <Select
              placeholder={t('alarms.statusLabel')}
              aria-label={t('alarms.statusLabel')}
              allowClear
              value={status}
              onChange={(v) => {
                setStatus(v);
                setPage(1);
              }}
              style={{ width: 160 }}
              options={STATUSES.map((value) => ({ value, label: t(`alarms.status.${value}`) }))}
            />
            {selected.length > 0 && (
              <Button type="primary" onClick={() => void handleBulkAck()}>
                {t('alarms.ackSelected', { count: selected.length })}
              </Button>
            )}
          </>
        }
      />

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {SEVERITIES.map((sev) => {
          const style = severityStyle(sev);
          const pressed = severity === sev;
          return (
            <Col key={sev} xs={12} sm={6}>
              <Card
                size="small"
                hoverable
                role="button"
                tabIndex={0}
                aria-pressed={pressed}
                onClick={() => setSeverity(pressed ? undefined : sev)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSeverity(pressed ? undefined : sev);
                  }
                }}
                style={{
                  borderInlineStart: `3px solid ${style.color}`,
                  background: pressed ? withAlpha(style.color, 0.08) : undefined,
                }}
              >
                <Flex justify="space-between" align="center">
                  <Space size={6}>
                    <style.Icon aria-hidden style={{ color: style.color }} />
                    <Typography.Text strong>{t(`alarms.severity.${sev}`)}</Typography.Text>
                  </Space>
                  <Typography.Text className="tabular" style={{ fontSize: 24, fontWeight: 700, color: style.text }}>
                    {severityCounts[sev] ?? '—'}
                  </Typography.Text>
                </Flex>
              </Card>
            </Col>
          );
        })}
      </Row>

      <Table<Alarm>
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        locale={{ emptyText: t('alarms.empty') }}
        pagination={{ current: page, pageSize: 50, total: data?.total, onChange: setPage, showSizeChanger: false, hideOnSinglePage: true }}
        rowSelection={{ selectedRowKeys: selected, onChange: (keys) => setSelected(keys as string[]) }}
        onRow={(record) => ({ onClick: () => setDrawerAlarm(record), style: { cursor: 'pointer' } })}
        size="small"
      />

      <Drawer
        title={drawerAlarm?.title ?? t('alarms.alarm')}
        open={Boolean(drawerAlarm)}
        onClose={() => setDrawerAlarm(null)}
        width={420}
        extra={drawerAlarm && <SeverityTag severity={drawerAlarm.severity} />}
      >
        {drawerAlarm && (
          <Flex vertical gap={16}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('alarms.message')}>{drawerAlarm.message}</Descriptions.Item>
              <Descriptions.Item label={t('alarms.raisedAt')}>{formatDateTime(drawerAlarm.raised_at)}</Descriptions.Item>
              <Descriptions.Item label={t('alarms.valueThreshold')}>
                {drawerAlarm.value != null
                  ? `${drawerAlarm.value.toFixed(2)} / ${drawerAlarm.threshold?.toFixed(2) ?? '—'}`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('alarms.statusLabel')}>
                <StatusLabel status={drawerAlarm.status} />
              </Descriptions.Item>
            </Descriptions>
            <Space>
              {drawerAlarm.status === 'active' && (
                <Button type="primary" onClick={() => void act(() => ackAlarm(drawerAlarm.id), t('alarms.acked', { count: 1 }))}>
                  {t('alarms.acknowledge')}
                </Button>
              )}
              {(drawerAlarm.status === 'active' || drawerAlarm.status === 'acknowledged') && (
                <Button onClick={() => void act(() => shelveAlarm(drawerAlarm.id), t('alarms.shelved'))}>
                  {t('alarms.shelve')}
                </Button>
              )}
            </Space>
          </Flex>
        )}
      </Drawer>
    </>
  );
}
