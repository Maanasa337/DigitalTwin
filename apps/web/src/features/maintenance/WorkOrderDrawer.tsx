import {
  CheckCircleFilled,
  CheckOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  StopOutlined,
} from '@ant-design/icons';
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
  Popconfirm,
  Skeleton,
  Space,
  Statistic,
  Tag,
  Typography,
  theme,
} from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { WorkOrderStatus } from '../../api/types';
import { useAuth } from '../../app/authContext';
import { useApiError } from '../../hooks/useApiError';
import {
  useCloseWorkOrder,
  useUpdateWorkOrder,
  useWorkOrder,
  useWorkOrderRisk,
} from '../../hooks/useMaintenance';
import { formatDateTime } from '../../lib/format';
import { ExplanationCard } from '../explain/ExplanationCard';
import { PriorityTag, RiskTag, StatusTagWo, TYPE_COLORS, VIA_LABELS, workOrderNumber } from './workOrderMeta';

interface WorkOrderDrawerProps {
  workOrderId: string | null;
  onClose: () => void;
}

/**
 * Work order detail: metadata, risk trade-off, the explanation that raised it, and its lifecycle
 * (start, cancel, close).
 *
 * Tasks are shown read-only: the API stores them with the order but exposes no endpoint to tick one
 * off, so a checkbox here would promise a write that cannot happen.
 */
export function WorkOrderDrawer({ workOrderId, onClose }: WorkOrderDrawerProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const onError = useApiError();
  const { hasRole } = useAuth();
  const [closing, setClosing] = useState(false);
  const [form] = Form.useForm<{ outcome: string; prediction_was_correct?: boolean }>();

  const { data: order, isLoading } = useWorkOrder(workOrderId ?? undefined);
  const { data: risk } = useWorkOrderRisk(workOrderId ?? undefined);
  const close = useCloseWorkOrder();
  const update = useUpdateWorkOrder();

  // Mirrors the API's `planner` guard on PATCH and /close; terminal orders reject both.
  const canAct =
    hasRole('technician', 'manager', 'engineer', 'admin') &&
    order !== undefined &&
    order.status !== 'closed' &&
    order.status !== 'cancelled';
  const canStart = canAct && (order.status === 'open' || order.status === 'scheduled');

  const setStatus = (status: WorkOrderStatus, done: string) => {
    update.mutate(
      { id: order!.id, status },
      {
        onSuccess: () => void message.success(done),
        onError,
      },
    );
  };

  const submitClose = () => {
    void form.validateFields().then((values) => {
      close.mutate(
        { id: order!.id, ...values },
        {
          onSuccess: () => {
            setClosing(false);
            form.resetFields();
            void message.success(t('maintenance.closed'));
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
      title={order ? `${workOrderNumber(order.number)} · ${order.title}` : t('common.loading')}
      extra={
        canAct ? (
          <Space>
            <Popconfirm
              title={t('maintenance.cancelOrder')}
              description={t('maintenance.cancelConfirm')}
              okText={t('maintenance.cancelOrder')}
              okButtonProps={{ danger: true }}
              cancelText={t('common.back')}
              onConfirm={() => setStatus('cancelled', t('maintenance.cancelled'))}
            >
              <Button danger icon={<StopOutlined />} loading={update.isPending && update.variables?.status === 'cancelled'}>
                {t('maintenance.cancelOrder')}
              </Button>
            </Popconfirm>
            {canStart && (
              <Button
                icon={<PlayCircleOutlined />}
                loading={update.isPending && update.variables?.status === 'in_progress'}
                onClick={() => setStatus('in_progress', t('maintenance.started'))}
              >
                {t('maintenance.start')}
              </Button>
            )}
            <Button type="primary" icon={<CheckOutlined />} onClick={() => setClosing(true)}>
              {t('maintenance.close')}
            </Button>
          </Space>
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
            <Descriptions.Item label={t('maintenance.asset')}>
              {order.asset_code ?? order.asset_id}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.technician')}>
              {order.technician_name ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.plannedStart')}>
              {formatDateTime(order.planned_start)}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.plannedEnd')}>
              {formatDateTime(order.planned_end)}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.duration')}>
              {order.est_duration_min ? `${order.est_duration_min} min` : '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t('maintenance.risk')}>
              <RiskTag risk={order.risk_before_slot} />
            </Descriptions.Item>
            {order.outcome && (
              <Descriptions.Item label={t('maintenance.outcome')} span={2}>
                {order.outcome}
              </Descriptions.Item>
            )}
          </Descriptions>

          {risk && risk.planned_start && (
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 12, textTransform: 'uppercase' }}>
                {t('maintenance.riskTradeoff')}
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
                  title={t('maintenance.asPlanned')}
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
                  {t('maintenance.rulBasis')} {risk.rul_point.toFixed(0)}
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
                {t('maintenance.tasks')}
              </Typography.Text>
              <Flex vertical gap={6} style={{ marginTop: 8 }}>
                {order.tasks.map((task) => (
                  <Flex key={task.id} gap={8} align="baseline">
                    {task.done ? (
                      <CheckCircleFilled aria-label={t('maintenance.taskDone')} style={{ color: token.colorSuccess }} />
                    ) : (
                      <ClockCircleOutlined aria-label={t('maintenance.taskPending')} style={{ color: token.colorTextTertiary }} />
                    )}
                    <Typography.Text type={task.done ? 'secondary' : undefined}>
                      {task.sequence}. {task.description}
                    </Typography.Text>
                  </Flex>
                ))}
              </Flex>
            </div>
          )}

          {order.explanation_id && (
            <>
              <Divider style={{ margin: 0 }} />
              <ExplanationCard explanationId={order.explanation_id} assetId={order.asset_id} />
            </>
          )}
        </Flex>
      )}

      <Modal
        title={t('maintenance.closeTitle')}
        open={closing}
        onCancel={() => setClosing(false)}
        onOk={submitClose}
        confirmLoading={close.isPending}
        okText={t('maintenance.close')}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
          {t('maintenance.closeHint')}
        </Typography.Paragraph>
        <Form form={form} layout="vertical">
          <Form.Item
            name="outcome"
            label={t('maintenance.outcome')}
            rules={[{ required: true, message: t('maintenance.outcomeRequired') }]}
          >
            <Input.TextArea rows={3} placeholder="Replaced bearing, vibration back to 2.1 mm/s" />
          </Form.Item>
          <Form.Item name="prediction_was_correct" valuePropName="checked">
            <Checkbox>{t('maintenance.predictionCorrect')}</Checkbox>
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
}
