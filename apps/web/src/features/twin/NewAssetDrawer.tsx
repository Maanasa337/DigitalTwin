import { Button, DatePicker, Drawer, Flex, Form, Input, InputNumber, Select } from 'antd';
import type { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';

import type { Asset, AssetCreate, AssetType, FidelityLevel } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useCreateAsset } from '../../hooks/useAssets';
import { ASSET_CODE_PATTERN, AssetTypeSelect, LineSelect } from './fields';

interface FormValues {
  line_id: string;
  code: string;
  name: string;
  asset_type: AssetType;
  manufacturer?: string;
  model?: string;
  serial_no?: string;
  install_date?: Dayjs | null;
  fidelity_level: FidelityLevel;
  rated_power_kw?: number | null;
  ideal_cycle_time_s?: number | null;
}

function toBody(values: FormValues): AssetCreate {
  const text = (v: string | undefined) => v?.trim() || null;
  return {
    line_id: values.line_id,
    code: values.code,
    name: values.name.trim(),
    asset_type: values.asset_type,
    manufacturer: text(values.manufacturer),
    model: text(values.model),
    serial_no: text(values.serial_no),
    install_date: values.install_date ? values.install_date.format('YYYY-MM-DD') : null,
    fidelity_level: values.fidelity_level,
    rated_power_kw: values.rated_power_kw ?? null,
    ideal_cycle_time_s: values.ideal_cycle_time_s ?? null,
  };
}

interface NewAssetDrawerProps {
  open: boolean;
  onClose: () => void;
  onCreated: (asset: Asset) => void;
}

export function NewAssetDrawer({ open, onClose, onCreated }: NewAssetDrawerProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<FormValues>();
  const create = useCreateAsset();
  const onError = useApiError();

  const submit = (values: FormValues) =>
    create.mutate(toBody(values), {
      onSuccess: (asset) => {
        form.resetFields();
        onCreated(asset);
      },
      onError,
    });

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t('twin.actions.newAsset')}
      width={480}
      destroyOnHidden
      extra={
        <Flex gap={8}>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={create.isPending} onClick={() => form.submit()}>
            {t('common.create')}
          </Button>
        </Flex>
      }
    >
      <Form<FormValues> form={form} layout="vertical" onFinish={submit} initialValues={{ fidelity_level: 2 }}>
        <Form.Item name="line_id" label={t('twin.form.line')} rules={[{ required: true }]}>
          <LineSelect />
        </Form.Item>
        <Form.Item
          name="code"
          label={t('twin.form.code')}
          extra={t('twin.form.codeHelp')}
          rules={[{ required: true }, { pattern: ASSET_CODE_PATTERN, message: t('twin.form.codeInvalid') }]}
        >
          <Input autoComplete="off" />
        </Form.Item>
        <Form.Item name="name" label={t('twin.form.name')} rules={[{ required: true, whitespace: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="asset_type" label={t('twin.form.type')} rules={[{ required: true }]}>
          <AssetTypeSelect />
        </Form.Item>
        <Form.Item name="manufacturer" label={t('twin.form.manufacturer')}>
          <Input />
        </Form.Item>
        <Form.Item name="model" label={t('twin.form.model')}>
          <Input />
        </Form.Item>
        <Form.Item name="serial_no" label={t('twin.form.serial')}>
          <Input />
        </Form.Item>
        <Form.Item name="install_date" label={t('twin.form.installDate')}>
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="fidelity_level" label={t('twin.form.fidelity')} rules={[{ required: true }]}>
          <Select<FidelityLevel>
            options={([1, 2, 3, 4] as const).map((level) => ({
              value: level,
              label: `L${level} ${t(`twin.fidelity.${level}`)}`,
            }))}
          />
        </Form.Item>
        <Form.Item name="rated_power_kw" label={t('twin.form.ratedPower')}>
          <InputNumber min={0} step={0.1} addonAfter="kW" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="ideal_cycle_time_s" label={t('twin.form.idealCycle')}>
          <InputNumber min={0} step={0.1} addonAfter="s" style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
