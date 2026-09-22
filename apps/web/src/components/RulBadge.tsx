import { Tag, Tooltip, theme } from 'antd';
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';

import { STATUS_PALETTE } from '../lib/status';

interface RulBadgeProps {
  point: number | null | undefined;
  low?: number | null;
  high?: number | null;
  unit?: string;
  coverage?: number | null;
  horizon?: number;
}

/**
 * RUL badge: "38 cycles" bold + "(29–47, 90%)" secondary with urgency colour.
 */
export function RulBadge({ point, low, high, unit = 'cycles', coverage, horizon = 100 }: RulBadgeProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const unitLabel = t(`rul.unit.${unit}`, { defaultValue: unit });

  if (point == null) {
    return (
      <Tag style={{ color: token.colorTextTertiary, borderColor: token.colorBorderSecondary }}>
        {t('rul.none')}
      </Tag>
    );
  }

  // Urgency by fraction of horizon remaining
  const urgency = Math.max(0, Math.min(1, point / horizon));
  const level = urgency >= 0.6 ? 'good' : urgency >= 0.3 ? 'warning' : urgency >= 0.15 ? 'serious' : 'critical';
  const color = STATUS_PALETTE[level].color;

  const mainStyle: CSSProperties = {
    fontWeight: 700,
    fontSize: 14,
    color,
  };

  const subStyle: CSSProperties = {
    fontSize: 11,
    color: token.colorTextSecondary,
    marginLeft: 4,
  };

  const intervalText =
    low != null && high != null
      ? `(${Math.round(low)}–${Math.round(high)}${coverage ? `, ${Math.round(coverage * 100)}%` : ''})`
      : '';

  return (
    <Tooltip title={t('rul.tooltip', { value: point.toFixed(1), unit: unitLabel })}>
      <span className="tabular">
        <span style={mainStyle}>{Math.round(point)}</span>
        <span style={{ ...mainStyle, fontSize: 11, fontWeight: 400, marginLeft: 2 }}>{unitLabel}</span>
        {intervalText && <span style={subStyle}>{intervalText}</span>}
      </span>
    </Tooltip>
  );
}
