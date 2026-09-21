import { ThunderboltOutlined } from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Flex,
  Popover,
  Slider,
  Tag,
  Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ObjectiveWeights, ScheduleItem } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { useApiError } from '../../hooks/useApiError';
import {
  useActiveSchedule,
  useOptimiseSchedule,
  usePatchScheduleItem,
  useTechnicians,
  useWorkOrders,
} from '../../hooks/useMaintenance';
import { GanttChart, type GanttRow } from './GanttChart';
import { WorkOrderDrawer } from './WorkOrderDrawer';
import { workOrderNumber } from './workOrderMeta';

const DEFAULT_WEIGHTS: ObjectiveWeights = { downtime_cost: 1, failure_risk: 1, energy_cost: 1 };

/** Schedule optimisation and the Gantt (FR-MS-02, FR-MS-03, FR-EN-05). */
export default function SchedulePage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();

  const [horizon, setHorizon] = useState<[Dayjs, Dayjs]>([dayjs(), dayjs().add(7, 'day')]);
  const [weights, setWeights] = useState<ObjectiveWeights>(DEFAULT_WEIGHTS);
  const [selectedOrder, setSelectedOrder] = useState<string | null>(null);

  const { data: schedule, isLoading } = useActiveSchedule();
  const { data: technicians } = useTechnicians();
  const { data: orders } = useWorkOrders({ size: 200 });
  const optimise = useOptimiseSchedule();
  const patchItem = usePatchScheduleItem(schedule?.id);

  const orderLabels = useMemo(() => {
    const map = new Map<string, string>();
    for (const order of orders?.items ?? []) {
      map.set(order.id, `${workOrderNumber(order.number)} ${order.title}`);
    }
    return map;
  }, [orders]);

  const rows: GanttRow[] = useMemo(() => {
    const assigned = (technicians?.items ?? []).map((tech) => ({ id: tech.id, label: tech.name }));
    return [...assigned, { id: 'unassigned', label: t('maintenance.unassignedRow', 'Unassigned') }];
  }, [technicians, t]);

  const runOptimise = () => {
    optimise.mutate(
      {
        horizon_start: horizon[0].toISOString(),
        horizon_end: horizon[1].toISOString(),
        weights,
      },
      {
        onSuccess: (result) => {
          void message.success(
            t('maintenance.optimised', '{{n}} orders scheduled in {{ms}} ms ({{status}})', {
              n: result.items.length,
              ms: result.solve_ms ?? 0,
              status: result.solver_status ?? 'unknown',
            }),
          );
        },
        onError,
      },
    );
  };

  const moveItem = (item: ScheduleItem, technicianId: string) => {
    patchItem.mutate(
      { itemId: item.id, technician_id: technicianId },
      {
        onSuccess: (result) => {
          if (result.conflicts.length > 0) {
            void message.warning(
              t('maintenance.conflictWarning', '{{n}} conflict(s) introduced by this change', {
                n: result.conflicts.length,
              }),
            );
          }
        },
        onError,
      },
    );
  };

  const weightsPopover = (
    <Flex vertical gap={4} style={{ width: 260 }}>
      {(Object.keys(DEFAULT_WEIGHTS) as (keyof ObjectiveWeights)[]).map((key) => (
        <div key={key}>
          <Typography.Text style={{ fontSize: 12 }}>
            {t(`maintenance.weight.${key}`, key.replace(/_/g, ' '))}: {weights[key].toFixed(1)}
          </Typography.Text>
          <Slider
            min={0}
            max={5}
            step={0.5}
            value={weights[key]}
            onChange={(v) => setWeights((prev) => ({ ...prev, [key]: v }))}
          />
        </div>
      ))}
      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
        {t(
          'maintenance.weightHint',
          'Raise failure risk to pull urgent work earlier; raise energy cost to push it into cheap tariff windows.',
        )}
      </Typography.Text>
    </Flex>
  );

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title={t('maintenance.scheduleTitle', 'Maintenance schedule')}
        subtitle={t(
          'maintenance.scheduleSubtitle',
          'CP-SAT places each open order against technician availability, failure risk and the energy tariff.',
        )}
        tags={
          schedule?.solver_status ? (
            <Tag color={schedule.solver_status === 'OPTIMAL' ? 'green' : 'blue'}>
              {schedule.solver_status} · {schedule.solve_ms} ms
            </Tag>
          ) : null
        }
        actions={
          <>
            <DatePicker.RangePicker
              showTime
              value={horizon}
              onChange={(v) => v && v[0] && v[1] && setHorizon([v[0], v[1]])}
            />
            <Popover content={weightsPopover} title={t('maintenance.weights', 'Objective weights')} trigger="click">
              <Button>{t('maintenance.tuneWeights', 'Weights')}</Button>
            </Popover>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={optimise.isPending}
              onClick={runOptimise}
            >
              {t('maintenance.optimise', 'Optimise')}
            </Button>
          </>
        }
      />

      <Flex vertical gap={16}>
        {schedule && schedule.unscheduled.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message={t('maintenance.unscheduled', '{{n}} order(s) could not be placed', {
              n: schedule.unscheduled.length,
            })}
            description={t(
              'maintenance.unscheduledDetail',
              'No available technician has the required skills, or the order is longer than the horizon.',
            )}
          />
        )}

        {schedule && schedule.conflicts.length > 0 && (
          <Alert
            type="error"
            showIcon
            message={t('maintenance.conflicts', '{{n}} conflict(s) in the current plan', {
              n: schedule.conflicts.length,
            })}
            description={
              <Flex vertical gap={2}>
                {schedule.conflicts.map((conflict, index) => (
                  <Typography.Text key={index} style={{ fontSize: 13 }}>
                    {conflict.kind === 'line'
                      ? t('maintenance.conflictLine', 'Two orders share a line at the same time')
                      : t('maintenance.conflictTech', 'A technician is double-booked')}
                    : {conflict.orders.map((id) => orderLabels.get(id) ?? id).join(' · ')}
                  </Typography.Text>
                ))}
              </Flex>
            }
          />
        )}

        <Card size="small" loading={isLoading}>
          {schedule && schedule.items.length > 0 ? (
            <>
              <GanttChart
                items={schedule.items}
                rows={rows}
                horizonStart={schedule.horizon_start}
                horizonEnd={schedule.horizon_end}
                labelFor={(item) => orderLabels.get(item.work_order_id) ?? item.work_order_id}
                onSelect={(item) => setSelectedOrder(item.work_order_id)}
              />
              <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }} style={{ marginTop: 12 }}>
                <Descriptions.Item label={t('maintenance.scheduled', 'Scheduled')}>
                  {schedule.items.length}
                </Descriptions.Item>
                <Descriptions.Item label={t('maintenance.objectiveValue', 'Objective')}>
                  {schedule.objective_value?.toFixed(2) ?? '—'}
                </Descriptions.Item>
                <Descriptions.Item label={t('maintenance.adjusted', 'Hand-adjusted')}>
                  {schedule.items.filter((i) => i.manually_adjusted).length}
                </Descriptions.Item>
                <Descriptions.Item label={t('maintenance.horizon', 'Horizon')}>
                  {dayjs(schedule.horizon_start).format('DD MMM')} –{' '}
                  {dayjs(schedule.horizon_end).format('DD MMM')}
                </Descriptions.Item>
              </Descriptions>
            </>
          ) : (
            <Empty
              description={t(
                'maintenance.noSchedule',
                'No active schedule. Set a horizon and run the optimiser.',
              )}
            />
          )}
        </Card>

        {schedule && schedule.items.length > 0 && (
          <Card size="small" title={t('maintenance.reassign', 'Reassign')}>
            <Typography.Paragraph type="secondary" style={{ fontSize: 13 }}>
              {t(
                'maintenance.reassignHint',
                'Moving an order to another technician re-scores its risk and reports any conflict it creates.',
              )}
            </Typography.Paragraph>
            <Flex wrap gap={8}>
              {schedule.items.map((item) => (
                <Popover
                  key={item.id}
                  trigger="click"
                  title={orderLabels.get(item.work_order_id)}
                  content={
                    <Flex vertical gap={4} style={{ maxWidth: 220 }}>
                      {(technicians?.items ?? []).map((tech) => (
                        <Button
                          key={tech.id}
                          size="small"
                          type={item.technician_id === tech.id ? 'primary' : 'default'}
                          loading={patchItem.isPending}
                          onClick={() => moveItem(item, tech.id)}
                        >
                          {tech.name}
                        </Button>
                      ))}
                    </Flex>
                  }
                >
                  <Tag
                    color={item.manually_adjusted ? 'gold' : 'default'}
                    style={{ cursor: 'pointer', marginInlineEnd: 0 }}
                  >
                    {orderLabels.get(item.work_order_id) ?? item.work_order_id}
                  </Tag>
                </Popover>
              ))}
            </Flex>
          </Card>
        )}
      </Flex>

      <WorkOrderDrawer workOrderId={selectedOrder} onClose={() => setSelectedOrder(null)} />
    </div>
  );
}
