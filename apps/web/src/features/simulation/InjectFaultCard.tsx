import { ThunderboltOutlined } from '@ant-design/icons';
import { App, Button, Card, Form, InputNumber, Radio, Select, Slider } from 'antd';
import { useTranslation } from 'react-i18next';

import { SENSOR_FAULTS, type FaultMode, type FaultRequest, type SimAsset } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useAssetIdByCode, useFailureModes, useSensors } from '../../hooks/useAssets';
import { useInjectFault } from '../../hooks/useSimulation';

interface FormValues {
  asset?: string;
  failure_mode?: string;
  metric?: string;
  mode: FaultMode;
  severity: number;
  duration_s?: number | null;
}

const INITIAL: FormValues = { mode: 'gradual', severity: 0.5 };

function isSensorFault(code: string | undefined): boolean {
  return (SENSOR_FAULTS as readonly string[]).includes(code ?? '');
}

export function InjectFaultCard({ assets }: { assets: SimAsset[] }) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const assetCode = Form.useWatch('asset', form);
  const failureMode = Form.useWatch('failure_mode', form);
  const selected = assets.find((a) => a.code === assetCode);
  const sensorFault = isSensorFault(failureMode);

  const modes = useFailureModes(selected?.asset_type);
  const assetId = useAssetIdByCode(sensorFault ? assetCode : undefined);
  const sensors = useSensors(assetId.data);
  const inject = useInjectFault();
  const onError = useApiError();

  const submit = (values: FormValues) => {
    if (!values.asset || !values.failure_mode) return;
    const body: FaultRequest = {
      asset: values.asset,
      failure_mode: values.failure_mode,
      mode: values.mode,
      severity: values.severity,
      metric: isSensorFault(values.failure_mode) ? values.metric : null,
      duration_s: values.duration_s ?? null,
    };
    inject.mutate(body, {
      onSuccess: (res) => {
        const key = res.accepted ? 'sim.fault.accepted' : 'sim.fault.notAccepted';
        void message[res.accepted ? 'success' : 'warning'](t(key, { mode: res.failure_mode, code: res.asset }));
      },
      onError,
    });
  };

  const onValuesChange = (changed: Partial<FormValues>) => {
    if ('asset' in changed) form.setFieldsValue({ failure_mode: undefined, metric: undefined });
    if ('failure_mode' in changed) form.setFieldsValue({ metric: undefined });
  };

  return (
    <Card title={t('sim.fault.title')} style={{ height: '100%' }}>
      <Form<FormValues> form={form} layout="vertical" initialValues={INITIAL} onFinish={submit} onValuesChange={onValuesChange}>
        <Form.Item name="asset" label={t('sim.fault.asset')} rules={[{ required: true }]}>
          <Select<string>
            showSearch
            optionFilterProp="label"
            options={assets.map((a) => ({ value: a.code, label: `${a.code} · ${t(`assetType.${a.asset_type}`, a.asset_type)}` }))}
          />
        </Form.Item>
        <Form.Item name="failure_mode" label={t('sim.fault.failureMode')} rules={[{ required: true }]}>
          <Select<string>
            disabled={!selected}
            loading={modes.isFetching}
            status={modes.isError ? 'error' : undefined}
            options={[
              {
                label: t('sim.fault.physicalModes'),
                options: (modes.data ?? []).map((m) => ({ value: m.code, label: `${m.name} (${m.code})` })),
              },
              {
                label: t('sim.fault.sensorFaults'),
                options: SENSOR_FAULTS.map((code) => ({ value: code, label: t(`sim.sensorFault.${code}`) })),
              },
            ]}
          />
        </Form.Item>
        {sensorFault && (
          <Form.Item name="metric" label={t('sim.fault.metric')} rules={[{ required: true }]}>
            <Select<string>
              showSearch
              loading={assetId.isFetching || sensors.isFetching}
              status={assetId.isError || sensors.isError ? 'error' : undefined}
              notFoundContent={assetId.data === null ? t('sim.fault.assetNotRegistered') : undefined}
              options={sensors.data?.map((s) => ({ value: s.metric_name, label: `${s.metric_name} (${s.unit})` }))}
            />
          </Form.Item>
        )}
        <Form.Item name="mode" label={t('sim.fault.mode')}>
          <Radio.Group
            optionType="button"
            options={(['gradual', 'sudden'] as const).map((mode) => ({ value: mode, label: t(`sim.mode.${mode}`) }))}
          />
        </Form.Item>
        <Form.Item name="severity" label={t('sim.fault.severity')}>
          <Slider min={0} max={1} step={0.05} marks={{ 0: '0', 0.5: '0.5', 1: '1' }} />
        </Form.Item>
        <Form.Item name="duration_s" label={t('sim.fault.duration')}>
          <InputNumber min={1} step={60} addonAfter="s" placeholder={t('common.optional')} style={{ width: '100%' }} />
        </Form.Item>
        <Button type="primary" danger htmlType="submit" icon={<ThunderboltOutlined />} loading={inject.isPending}>
          {t('sim.fault.submit')}
        </Button>
      </Form>
    </Card>
  );
}
