import { ExportOutlined } from '@ant-design/icons';
import { Alert, Button, Descriptions, Form, InputNumber, Modal, Select, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ExportRequest } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useExportDataset, useScenarios } from '../../hooks/useSimulation';
import { formatNumber } from '../../lib/format';

export function ExportModal() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<ExportRequest>();
  const scenarios = useScenarios();
  const exportDataset = useExportDataset();
  const onError = useApiError();
  const result = exportDataset.data;

  const close = () => {
    setOpen(false);
    exportDataset.reset();
  };

  return (
    <>
      <Button icon={<ExportOutlined />} onClick={() => setOpen(true)}>
        {t('sim.export.button')}
      </Button>
      <Modal
        open={open}
        title={t('sim.export.title')}
        okText={result ? t('common.close') : t('sim.export.submit')}
        cancelText={t('common.cancel')}
        cancelButtonProps={{ style: result ? { display: 'none' } : undefined }}
        confirmLoading={exportDataset.isPending}
        onOk={() => (result ? close() : form.submit())}
        onCancel={close}
        maskClosable={!exportDataset.isPending}
        destroyOnHidden
      >
        {result ? (
          <Descriptions
            column={1}
            size="small"
            bordered
            items={[
              { key: 'path', label: t('sim.export.path'), children: <Typography.Text copyable code>{result.path}</Typography.Text> },
              { key: 'rows', label: t('sim.export.rows'), children: formatNumber(result.rows) },
              { key: 'columns', label: t('sim.export.columns'), children: result.columns.join(', ') },
            ]}
          />
        ) : (
          <Form<ExportRequest>
            form={form}
            layout="vertical"
            disabled={exportDataset.isPending}
            initialValues={{ hours: 24, sample_period_s: 60, scenario_code: null, seed: null }}
            onFinish={(values) => exportDataset.mutate(values, { onError })}
          >
            {exportDataset.isPending && <Alert type="info" showIcon message={t('sim.export.running')} style={{ marginBottom: 16 }} />}
            <Form.Item name="scenario_code" label={t('sim.export.scenario')}>
              <Select<string>
                allowClear
                placeholder={t('sim.export.currentScenario')}
                loading={scenarios.isPending}
                options={scenarios.data?.map((s) => ({ value: s.code, label: `${s.name} (${s.code})` }))}
              />
            </Form.Item>
            <Form.Item
              name="hours"
              label={t('sim.export.hours')}
              rules={[{ required: true }, { type: 'number', min: 0.01, max: 168, message: t('sim.export.hoursRange') }]}
            >
              <InputNumber min={0.01} max={168} step={1} addonAfter="h" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="sample_period_s"
              label={t('sim.export.samplePeriod')}
              rules={[{ required: true }, { type: 'number', min: 0.01, message: t('sim.export.samplePeriodRange') }]}
            >
              <InputNumber min={0.01} step={1} addonAfter="s" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="seed" label={t('sim.export.seed')}>
              <InputNumber min={0} precision={0} style={{ width: '100%' }} placeholder={t('common.optional')} />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </>
  );
}
