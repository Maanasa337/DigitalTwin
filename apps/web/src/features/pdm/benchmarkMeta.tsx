import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';

import type { BenchmarkRun, BenchmarkStatus, BenchmarkTarget } from '../../api/types';

const STATUS_META: Record<BenchmarkStatus, { color: string; Icon: typeof CheckCircleOutlined }> = {
  running: { color: 'processing', Icon: LoadingOutlined },
  done: { color: 'success', Icon: CheckCircleOutlined },
  failed: { color: 'error', Icon: CloseCircleOutlined },
};

/** Icon plus label, never colour alone (§9.1). */
export function BenchmarkStatusTag({ status }: { status: BenchmarkStatus }) {
  const { t } = useTranslation();
  const { color, Icon } = STATUS_META[status];
  return (
    <Tag color={color} icon={<Icon aria-hidden />} style={{ marginInlineEnd: 0 }}>
      {t(`benchmarks.status.${status}`)}
    </Tag>
  );
}

export type Verdict = 'pass' | 'fail' | 'none';

export function verdict(value: number, target: BenchmarkTarget | undefined): Verdict {
  if (!target) return 'none';
  return (target.op === 'le' ? value <= target.value : value >= target.value) ? 'pass' : 'fail';
}

const VERDICT_META: Record<Verdict, { color: string; Icon: typeof CheckCircleOutlined }> = {
  pass: { color: 'success', Icon: CheckCircleOutlined },
  fail: { color: 'error', Icon: CloseCircleOutlined },
  none: { color: 'default', Icon: MinusCircleOutlined },
};

export function VerdictTag({ value }: { value: Verdict }) {
  const { t } = useTranslation();
  const { color, Icon } = VERDICT_META[value];
  return (
    <Tag color={color} icon={<Icon aria-hidden />} style={{ marginInlineEnd: 0 }}>
      {t(`benchmarks.verdict.${value}`)}
    </Tag>
  );
}

export interface ResultRow {
  key: string;
  dataset: string;
  metric: string;
  value: number;
  target?: BenchmarkTarget;
  verdict: Verdict;
}

/** `{dataset: {metric: value}}` → one row per metric, in dataset then metric order. */
export function resultRows(run: BenchmarkRun): ResultRow[] {
  return Object.entries(run.results ?? {}).flatMap(([dataset, metrics]) =>
    Object.entries(metrics).map(([metric, value]) => {
      const target = run.targets?.[dataset]?.[metric];
      return { key: `${dataset}:${metric}`, dataset, metric, value, target, verdict: verdict(value, target) };
    }),
  );
}
