import { DatePicker, Form, Modal, Select } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AnalyticsScope, ReportFormat, ReportType } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useCreateReport } from '../../hooks/useReports';
import { ScopePicker } from '../analytics/ScopePicker';
import { ASSET_SCOPED_TYPES, REPORT_TYPES } from './reportMeta';

interface FormValues {
  type: ReportType;
  format: ReportFormat;
  period: [Dayjs, Dayjs] | null;
}

const FORMATS: ReportFormat[] = ['pdf', 'docx', 'md'];

export function GenerateReportModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const onError = useApiError();
  const [form] = Form.useForm<FormValues>();
  const create = useCreateReport();

  // The scope lives outside the form. `ScopePicker` defaults itself through an effect that depends
  // on its `onChange`, so the callback has to be stable — routing it through `setFieldsValue` makes
  // every render a new function and the pair spins.
  const [scope, setScope] = useState<AnalyticsScope>('plant');
  const [scopeId, setScopeId] = useState<string>();
  const onScopeChange = useCallback((nextScope: AnalyticsScope, nextId: string | undefined) => {
    setScope(nextScope);
    setScopeId(nextId);
  }, []);

  const type = Form.useWatch('type', form) ?? 'weekly_maintenance';
  const needsAsset = ASSET_SCOPED_TYPES.includes(type);
  const effectiveScope: AnalyticsScope = needsAsset ? 'asset' : scope;

  const submit = () => {
    form
      .validateFields()
      .then((values) => {
        if (needsAsset && !scopeId) {
          void onError(new Error(t('reports.assetRequired')));
          return;
        }
        create.mutate(
          {
            type: values.type,
            scope: effectiveScope,
            scope_id: scopeId ?? null,
            period_start: values.period?.[0]?.toISOString() ?? null,
            period_end: values.period?.[1]?.toISOString() ?? null,
            format: values.format,
          },
          {
            onSuccess: () => {
              form.resetFields();
              onClose();
            },
            onError,
          },
        );
      })
      .catch(() => undefined);
  };

  return (
    <Modal
      open={open}
      title={t('reports.generate')}
      okText={t('reports.generate')}
      onOk={submit}
      confirmLoading={create.isPending}
      onCancel={onClose}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          type: 'weekly_maintenance',
          format: 'pdf',
          period: [dayjs().subtract(7, 'day'), dayjs()],
        }}
      >
        <Form.Item name="type" label={t('reports.type')} rules={[{ required: true }]}>
          <Select
            options={REPORT_TYPES.map((value) => ({ value, label: t(`reports.typeName.${value}`) }))}
          />
        </Form.Item>

        <Form.Item label={needsAsset ? t('reports.asset') : t('reports.scope')} required={needsAsset}>
          <ScopePicker scope={effectiveScope} scopeId={scopeId} onChange={onScopeChange} />
        </Form.Item>

        <Form.Item name="period" label={t('reports.period')}>
          <DatePicker.RangePicker showTime style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          name="format"
          label={t('reports.format')}
          extra={t('reports.formatHint')}
          rules={[{ required: true }]}
        >
          <Select options={FORMATS.map((value) => ({ value, label: value.toUpperCase() }))} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
