import { App, Form, InputNumber, Modal, Select } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { TreeAsset, TwinCommand, TwinCommandName } from '../../api/types';
import { ConfirmReadback } from '../../components/ConfirmReadback';
import { useTwinCommand } from '../../hooks/useTwin';
import { problemMessage, problemStatus } from '../../lib/problem';

interface FormValues {
  command: TwinCommandName;
  load_pct?: number;
  speed_pct?: number;
  component_code?: string | null;
}

function toCommand(values: FormValues): TwinCommand {
  switch (values.command) {
    case 'set_load':
      return { command: 'set_load', params: { load_pct: values.load_pct ?? 0 } };
    case 'set_speed':
      return { command: 'set_speed', params: { speed_pct: values.speed_pct ?? 100 } };
    case 'maintenance_reset':
      return { command: 'maintenance_reset', params: { component_code: values.component_code ?? null } };
  }
}

const ERROR_KEYS: Record<number, string> = {
  403: 'twin.command.t3Disabled',
  423: 'twin.command.pinIncorrect',
  504: 'twin.command.noAck',
};

interface CommandModalProps {
  asset: TreeAsset;
  open: boolean;
  onClose: () => void;
}

export function CommandModal({ asset, open, onClose }: CommandModalProps) {
  const { t } = useTranslation();
  const { notification } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const commandType = Form.useWatch('command', form);
  const [pending, setPending] = useState<TwinCommand | null>(null);
  const send = useTwinCommand(asset.code);

  const readback = (command: TwinCommand): string => {
    switch (command.command) {
      case 'set_load':
        return t('twin.command.readback.set_load', { code: asset.code, value: command.params.load_pct });
      case 'set_speed':
        return t('twin.command.readback.set_speed', { code: asset.code, value: command.params.speed_pct });
      case 'maintenance_reset':
        return t('twin.command.readback.maintenance_reset', {
          code: asset.code,
          component: command.params.component_code ?? t('twin.command.allComponents'),
        });
    }
  };

  const confirm = (pin: string | undefined) => {
    if (!pending) return;
    send.mutate(
      { ...pending, pin: pin ?? '' },
      {
        onSuccess: (result) => {
          setPending(null);
          if (result.status === 'accepted') {
            notification.success({
              message: t('twin.command.accepted'),
              description: t('twin.command.commandId', { id: result.command_id }),
            });
            form.resetFields();
            onClose();
          } else {
            notification.warning({
              message: t('twin.command.rejected'),
              description: result.error ?? undefined,
            });
          }
        },
        onError: (err) => {
          setPending(null);
          const key = ERROR_KEYS[problemStatus(err) ?? 0];
          notification.error({
            message: key ? t(key) : t('twin.command.failed'),
            description: problemMessage(err, t('errors.generic')),
          });
        },
      },
    );
  };

  const componentOptions = asset.components.map((c) => ({ value: c.code, label: `${c.name} (${c.code})` }));

  return (
    <>
      <Modal
        open={open}
        title={t('twin.command.title', { code: asset.code })}
        okText={t('twin.command.review')}
        cancelText={t('common.cancel')}
        onOk={() => form.submit()}
        onCancel={onClose}
        destroyOnHidden
      >
        <Form<FormValues>
          form={form}
          layout="vertical"
          initialValues={{ command: 'set_load', load_pct: 80, speed_pct: 100 }}
          onFinish={(values) => setPending(toCommand(values))}
        >
          <Form.Item name="command" label={t('twin.command.command')} rules={[{ required: true }]}>
            <Select<TwinCommandName>
              options={(['set_load', 'set_speed', 'maintenance_reset'] as const).map((value) => ({
                value,
                label: t(`twin.command.names.${value}`),
              }))}
            />
          </Form.Item>
          {commandType === 'set_load' && (
            <Form.Item name="load_pct" label={t('twin.command.loadPct')} rules={[{ required: true }]}>
              <InputNumber min={0} max={110} step={5} addonAfter="%" style={{ width: '100%' }} />
            </Form.Item>
          )}
          {commandType === 'set_speed' && (
            <Form.Item name="speed_pct" label={t('twin.command.speedPct')} rules={[{ required: true }]}>
              <InputNumber min={50} max={120} step={5} addonAfter="%" style={{ width: '100%' }} />
            </Form.Item>
          )}
          {commandType === 'maintenance_reset' && (
            <Form.Item name="component_code" label={t('twin.command.component')}>
              <Select allowClear placeholder={t('twin.command.allComponents')} options={componentOptions} />
            </Form.Item>
          )}
        </Form>
      </Modal>
      <ConfirmReadback
        open={pending !== null}
        text={pending ? readback(pending) : ''}
        requirePin
        loading={send.isPending}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
