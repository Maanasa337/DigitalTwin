import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { App, Button, DatePicker, Flex, Form, Input, InputNumber, Modal, Select } from 'antd';
import type { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';

import type { WorkOrderType } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useAssets } from '../../hooks/useAssets';
import { useCreateWorkOrder, useTechnicians } from '../../hooks/useMaintenance';

interface FormValues {
  asset_id: string;
  type: WorkOrderType;
  priority: number;
  title: string;
  description?: string;
  technician_id?: string;
  planned: [Dayjs, Dayjs] | null;
  est_duration_min?: number;
  tasks?: { description: string }[];
}

interface CreateWorkOrderModalProps {
  open: boolean;
  onClose: () => void;
}

export function CreateWorkOrderModal({ open, onClose }: CreateWorkOrderModalProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const [form] = Form.useForm<FormValues>();

  const { data: assets } = useAssets({ size: 200 });
  const { data: technicians } = useTechnicians();
  const create = useCreateWorkOrder();

  const submit = () => {
    void form.validateFields().then((values) => {
      const [start, end] = values.planned ?? [];
      create.mutate(
        {
          asset_id: values.asset_id,
          type: values.type,
          priority: values.priority,
          title: values.title,
          description: values.description,
          technician_id: values.technician_id,
          planned_start: start?.toISOString(),
          planned_end: end?.toISOString(),
          est_duration_min: values.est_duration_min,
          // Sequence is positional: the order the planner typed the steps is the order to do them.
          tasks: (values.tasks ?? [])
            .filter((task) => task?.description)
            .map((task, index) => ({ sequence: index + 1, description: task.description })),
        },
        {
          onSuccess: (order) => {
            form.resetFields();
            onClose();
            void message.success(
              t('maintenance.created', { number: order.number }),
            );
          },
          onError,
        },
      );
    });
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={submit}
      confirmLoading={create.isPending}
      title={t('maintenance.newOrder')}
      okText={t('common.create')}
      width={620}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ type: 'corrective', priority: 3 }}
        style={{ marginTop: 12 }}
      >
        <Form.Item
          name="asset_id"
          label={t('maintenance.asset')}
          rules={[{ required: true, message: t('maintenance.assetRequired') }]}
        >
          <Select
            showSearch
            optionFilterProp="label"
            placeholder={t('maintenance.pickAsset')}
            options={(assets?.items ?? []).map((a) => ({
              value: a.id,
              label: `${a.code} — ${a.name}`,
            }))}
          />
        </Form.Item>

        <Form.Item
          name="title"
          label={t('maintenance.titleField')}
          rules={[{ required: true, max: 200 }]}
        >
          <Input placeholder="Replace spindle bearing" />
        </Form.Item>

        <Flex gap={12}>
          <Form.Item name="type" label={t('maintenance.type')} style={{ flex: 1 }}>
            <Select
              options={[
                { value: 'corrective', label: t('maintenance.corrective') },
                { value: 'preventive', label: t('maintenance.preventive') },
                { value: 'predictive', label: t('maintenance.predictive') },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="priority"
            label={t('maintenance.priority')}
            style={{ flex: 1 }}
            extra={t('maintenance.priorityHint')}
          >
            <InputNumber min={1} max={5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="est_duration_min"
            label={t('maintenance.duration')}
            style={{ flex: 1 }}
          >
            <InputNumber min={1} max={10080} addonAfter="min" style={{ width: '100%' }} />
          </Form.Item>
        </Flex>

        <Form.Item name="technician_id" label={t('maintenance.technician')}>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('maintenance.unassigned')}
            options={(technicians?.items ?? []).map((tech) => ({
              value: tech.id,
              label: `${tech.name} (${tech.skills.join(', ') || 'no skills listed'})`,
            }))}
          />
        </Form.Item>

        <Form.Item name="planned" label={t('maintenance.plannedWindow')}>
          <DatePicker.RangePicker showTime style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item name="description" label={t('maintenance.description')}>
          <Input.TextArea rows={2} maxLength={4000} />
        </Form.Item>

        <Form.List name="tasks">
          {(fields, { add, remove }) => (
            <Flex vertical gap={8}>
              {fields.map((field) => (
                <Flex key={field.key} gap={8} align="baseline">
                  <Form.Item
                    {...field}
                    name={[field.name, 'description']}
                    style={{ flex: 1, marginBottom: 0 }}
                    rules={[{ max: 500 }]}
                  >
                    <Input placeholder={`Step ${field.name + 1}`} />
                  </Form.Item>
                  <MinusCircleOutlined onClick={() => remove(field.name)} />
                </Flex>
              ))}
              <Button type="dashed" onClick={() => add()} icon={<PlusOutlined />} block>
                {t('maintenance.addTask')}
              </Button>
            </Flex>
          )}
        </Form.List>
      </Form>
    </Modal>
  );
}
