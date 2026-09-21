import { Tag } from 'antd';

import type { CreatedVia, WorkOrderStatus, WorkOrderType } from '../../api/types';

export const STATUS_COLORS: Record<WorkOrderStatus, string> = {
  open: 'blue',
  scheduled: 'cyan',
  in_progress: 'gold',
  closed: 'green',
  cancelled: 'default',
};

export const TYPE_COLORS: Record<WorkOrderType, string> = {
  corrective: 'red',
  preventive: 'blue',
  predictive: 'purple',
};

/** 1 is most urgent, so the colour ramp runs the other way to a normal severity scale. */
export const PRIORITY_COLORS: Record<number, string> = {
  1: 'red',
  2: 'volcano',
  3: 'orange',
  4: 'default',
  5: 'default',
};

export const VIA_LABELS: Record<CreatedVia, string> = {
  ui: 'Manual',
  voice: 'Voice',
  chat: 'Chat',
  auto: 'Auto (predicted)',
};

export function workOrderNumber(n: number): string {
  return `WO-${String(n).padStart(6, '0')}`;
}

export function StatusTagWo({ status }: { status: WorkOrderStatus }) {
  return (
    <Tag color={STATUS_COLORS[status]} style={{ marginInlineEnd: 0 }}>
      {status.replace(/_/g, ' ')}
    </Tag>
  );
}

export function PriorityTag({ priority }: { priority: number }) {
  return (
    <Tag color={PRIORITY_COLORS[priority] ?? 'default'} style={{ marginInlineEnd: 0 }}>
      P{priority}
    </Tag>
  );
}

/** Risk reads as a probability, so it is shown as a percentage with a severity colour. */
export function RiskTag({ risk }: { risk: number | null }) {
  if (risk == null) return <span>—</span>;
  const pct = risk * 100;
  const color = pct >= 50 ? 'red' : pct >= 20 ? 'orange' : 'default';
  return (
    <Tag color={color} style={{ marginInlineEnd: 0 }}>
      {pct.toFixed(1)}%
    </Tag>
  );
}
