import { CheckOutlined } from '@ant-design/icons';
import {
  App,
  Button,
  Checkbox,
  Descriptions,
  Divider,
  Drawer,
  Flex,
  Form,
  Input,
  Modal,
  Skeleton,
  Statistic,
  Tag,
  Typography,
} from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useApiError } from '../../hooks/useApiError';
import { useCloseWorkOrder, useWorkOrder, useWorkOrderRisk } from '../../hooks/useMaintenance';
import { formatDateTime } from '../../lib/format';
import { ExplanationCard } from '../explain/ExplanationCard';
import { PriorityTag, RiskTag, StatusTagWo, TYPE_COLORS, VIA_LABELS, workOrderNumber } from './workOrderMeta';

interface WorkOrderDrawerProps {
  workOrderId: string | null;
  onClose: () => void;
}

/**
 * Work order detail: metadata, risk trade-off, the explanation that raised it, and closure.
 */
export function WorkOrderDrawer({ workOrderId, onClose }: WorkOrderDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const [closing, setClosing] = useState(false);
  const [form] = Form.useForm<{ outcome: string; prediction_was_correct?: boolean }>();

  const { data: order, isLoading } = useWorkOrder(workOrderId ?? undefined);
  const { data: risk } = useWorkOrderRisk(workOrderId ?? undefined);
  const close = useCloseWorkOrder();

  const canClose = order && order.status !== 'closed' && order.status !== 'cancelled';

  const submitClose = () => {
    void form.validateFields().then((values) => {
      close.mutate(
        { id: order!.id, ...values },
        {
          onSuccess: () => {
            setClosing(false);
            form.resetFields();
            void message.success(t('maintenance.closed', 'Work order closed and damage reset'));
          },
          onError,
        },
      );
    });
  };

  return (
    <Drawer
      open={Boolean(workOrderId)}
      onClose={onClose}
      width={620}
      title={order ? `${workOrderNumber(order.number)} · ${order.title}` : t('common.loading', 'Loading')}
      extra={
        canClose ? (
          <Button type="primary" icon={<CheckOutlined />} onClick={() => setClosing(true)}>
            {t('maintenance.close', 'Close order')}
          </Button>
        ) : null
      }
    >
      {isLoading || !order ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : (
        <Flex vertical gap={16}>
          <Flex wrap gap={8}>
            <StatusTagWo status={order.status} />
            <Tag color={TYPE_COLORS[order.type]} style={{ marginInlineEnd: 0 }}>
              {order.type}
            </Tag>
            <PriorityTag priority={order.priority} />
            <Tag style={{ marginInlineEnd: 0 }}>{VIA_LABELS[order.created_via]}</Tag>
          </Flex>

          {order.description && (
            <Typography.Paragraph style={{ margin: 0 }}>{order.description}</Typography.Paragraph>
          )}

          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label={t('maintenance.asset', 'Asset')}>
              {order.asset_code ?? order.asset_id}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.technician', 'Technician')}>
              {order.technician_name ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.plannedStart', 'Planned start')}>
              {formatDateTime(order.planned_start)}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.plannedEnd', 'Planned end')}>
              {formatDateTime(order.planned_end)}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.duration', 'Est. duration')}>
              {order.est_duration_min ? `${order.est_duration_min} min` : '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.risk', 'Risk before slot')}>
              <RiskTag risk={order.risk_before_slot} />
            </Descriptions.Item>
            {order.outcome && (
              <Descriptions.Item label={t('maintenance.outcome', 'Outcome')} span={2}>
                {order.outcome}
              </Descriptions.Item>
            )}
          </Descriptions>

          {risk && risk.planned_start && (
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12, textTransform: 'uppercase' }}>
                {t('maintenance.riskTradeoff', 'Moving this slot')}
              </Typography.Text>
              <Flex gap={24} wrap style={{ marginTop: 8 }}>
                <Statistic
                  title={`${risk.shift_hours}h earlier`}
                  value={risk.risk_earlier * 100}
                  precision={1}
                  suffix="%"
                  valueStyle={{ fontSize: 18 }}
                />
                <Statistic
                  title={t('maintenance.asPlanned', 'As planned')}
                  value={risk.risk * 100}
                  precision={1}
                  suffix="%"
                  valueStyle={{ fontSize: 18, fontWeight: 600 }}
                />
                <Statistic
                  title={`${risk.shift_hours}h later`}
                  value={risk.risk_later * 100}
                  precision={1}
                  suffix="%"
                  valueStyle={{ fontSize: 18 }}
                />
              </Flex>
              {risk.rul_point != null && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('maintenance.rulBasis', 'Based on remaining life')} {risk.rul_point.toFixed(0)}
                  {risk.rul_low != null && risk.rul_high != null
                    ? ` (${risk.rul_low.toFixed(0)}–${risk.rul_high.toFixed(0)})`
                    : ''}
                </Typography.Text>
              )}
            </div>
          )}

          {order.tasks.length > 0 && (
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12, textTransform: 'uppercase' }}>
                {t('maintenance.tasks', 'Tasks')}
              </Typography.Text>
              <Flex vertical gap={4} style={{ marginTop: 8 }}>
                {order.tasks.map((task) => (
                  <Checkbox key={task.id} checked={task.done} disabled>
                    {task.sequence}. {task.description}
                  </Checkbox>
                ))}
              </Flex>
            </div>
          )}

          {order.explanation_id && (
            <>
              <Divider style={{ margin: 0 }} />
              <ExplanationCard explanationId={order.explanation_id} />
            </>
          )}
        </Flex>
      )}

      <Modal
        title={t('maintenance.closeTitle', 'Close work order')}
        open={closing}
        onCancel={() => setClosing(false)}
        onOk={submitClose}
        confirmLoading={close.isPending}
        okText={t('maintenance.close', 'Close order')}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          {t(
            'maintenance.closeHint',
            'Closing publishes a maintenance reset to the machine, so its simulated damage is cleared.',
          )}
        </Typography.Paragraph>
        <Form form={form} layout="vertical">
          <Form.Item
            name="outcome"
            label={t('maintenance.outcome', 'Outcome')}
            rules={[{ required: true, message: t('maintenance.outcomeRequired', 'Describe what you found') }]}
          >
            <Input.TextArea rows={3} placeholder="Replaced bearing, vibration back to 2.1 mm/s" />
          </Form.Item>
          <Form.Item name="prediction_was_correct" valuePropName="checked">
            <Checkbox>{t('maintenance.predictionCorrect', 'The prediction was correct')}</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
}
