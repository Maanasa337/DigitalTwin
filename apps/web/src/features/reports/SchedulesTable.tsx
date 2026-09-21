import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Card, Form, Input, Popconfirm, Select, Space, Switch, Table, Tag } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ReportFormat, ReportSchedule, ReportType } from '../../api/types';
import { useAuth } from '../../app/authContext';
import { useApiError } from '../../hooks/useApiError';
import { useCreateSchedule, useDeleteSchedule, useReportSchedules, useUpdateSchedule } from '../../hooks/useReports';
import { formatDateTime } from '../../lib/format';
import { REPORT_TYPES } from './reportMeta';

const CRON = /^(\S+\s+){4}\S+$/;

export function SchedulesTable() {
  const { t } = useTranslation();
  const onError = useApiError();
  const { hasRole } = useAuth();
  const canEdit = hasRole('engineer', 'admin');

  const schedules = useReportSchedules();
  const create = useCreateSchedule();
  const update = useUpdateSchedule();
  const remove = useDeleteSchedule();
  const [adding, setAdding] = useState(false);
  const [form] = Form.useForm();

  const submit = () => {
    form
      .validateFields()
      .then((values) =>
        create.mutate(
          {
            type: values.type as ReportType,
            format: values.format as ReportFormat,
            cron: values.cron,
            recipients: values.recipients ? String(values.recipients).split(/[,\s]+/).filter(Boolean) : [],
          },
          {
            onSuccess: () => {
              form.resetFields();
              setAdding(false);
            },
            onError,
          },
        ),
      )
      .catch(() => undefined);
  };

  return (
    <Card
      title={t('reports.schedules')}
      extra={
        canEdit && (
          <Button
            size="small"
            icon={<PlusOutlined />}
            // The icon contributes its own label, so the name is set explicitly.
            aria-label={t('reports.addSchedule')}
            onClick={() => setAdding((v) => !v)}
          >
            {t('reports.addSchedule')}
          </Button>
        )
      }
    >
      {adding && (
        <Form form={form} layout="inline" style={{ marginBottom: 16, rowGap: 8 }} initialValues={{ format: 'pdf' }}>
          <Form.Item name="type" rules={[{ required: true }]}>
            <Select
              style={{ minWidth: 200 }}
              placeholder={t('reports.type')}
              options={REPORT_TYPES.map((value) => ({ value, label: t(`reports.typeName.${value}`) }))}
            />
          </Form.Item>
          <Form.Item name="format" rules={[{ required: true }]}>
            <Select
              style={{ width: 100 }}
              options={(['pdf', 'docx', 'md'] as const).map((value) => ({ value, label: value.toUpperCase() }))}
            />
          </Form.Item>
          <Form.Item
            name="cron"
            rules={[{ required: true, pattern: CRON, message: t('reports.cronInvalid') }]}
            tooltip={t('reports.cronHint')}
          >
            <Input placeholder="0 6 * * 1" style={{ width: 140 }} />
          </Form.Item>
          <Form.Item name="recipients">
            <Input placeholder={t('reports.recipients')} style={{ width: 220 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" onClick={submit} loading={create.isPending}>
              {t('common.save')}
            </Button>
          </Form.Item>
        </Form>
      )}

      <Table<ReportSchedule>
        size="small"
        rowKey="id"
        loading={schedules.isLoading}
        dataSource={schedules.data?.items ?? []}
        pagination={false}
        locale={{ emptyText: t('reports.noSchedules') }}
        columns={[
          {
            title: t('reports.type'),
            dataIndex: 'type',
            render: (value: ReportType) => t(`reports.typeName.${value}`),
          },
          {
            title: t('reports.cron'),
            dataIndex: 'cron',
            render: (value: string) => <Tag className="tabular">{value}</Tag>,
          },
          {
            title: t('reports.format'),
            dataIndex: 'format',
            render: (value: string) => value.toUpperCase(),
          },
          {
            title: t('reports.recipients'),
            dataIndex: 'recipients',
            render: (values: string[]) => (values.length ? values.join(', ') : '—'),
          },
          {
            title: t('reports.lastRun'),
            dataIndex: 'last_run_at',
            render: (value: string | null) => formatDateTime(value),
          },
          {
            title: t('reports.enabled'),
            dataIndex: 'enabled',
            width: 150,
            render: (enabled: boolean, row) => (
              <Space>
                <Switch
                  size="small"
                  checked={enabled}
                  disabled={!canEdit || update.isPending}
                  aria-label={t('reports.enabled')}
                  onChange={(checked) => update.mutate({ id: row.id, enabled: checked }, { onError })}
                />
                {canEdit && (
                  <Popconfirm
                    title={t('reports.deleteSchedule')}
                    onConfirm={() => remove.mutate(row.id, { onError })}
                  >
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label={t('common.delete')} />
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
