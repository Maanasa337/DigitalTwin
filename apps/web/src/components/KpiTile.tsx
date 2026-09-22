import { ArrowDownOutlined, ArrowUpOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { Tooltip, theme } from 'antd';
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';

import { formatNumber } from '../lib/format';
import { statusTextColor } from '../lib/status';
import { useUiStore } from '../store/uiStore';

interface KpiTileProps {
  title: string;
  value: number | null | undefined;
  unit?: string;
  digits?: number;
  delta?: number | null;
  deltaLabel?: string;
  formula?: string;
}

/**
 * KPI tile: title, large value, optional delta arrow, formula tooltip.
 */
export function KpiTile({ title, value, unit, digits = 0, delta, deltaLabel, formula }: KpiTileProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const mode = useUiStore((s) => s.themeMode);

  const containerStyle: CSSProperties = {
    background: token.colorBgContainer,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadiusLG,
    padding: '14px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    minWidth: 140,
  };

  const titleStyle: CSSProperties = {
    fontSize: 12,
    color: token.colorTextSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    fontWeight: 500,
  };

  const valueStyle: CSSProperties = {
    fontSize: 28,
    fontWeight: 700,
    color: token.colorText,
    lineHeight: 1.1,
  };

  const content = (
    <div style={containerStyle}>
      <div style={{ ...titleStyle, display: 'flex', alignItems: 'center', gap: 4 }}>
        {title}
        {formula && <InfoCircleOutlined aria-label={t('kpi.formula')} style={{ fontSize: 11 }} />}
      </div>
      <div>
        <span style={valueStyle} className="tabular">
          {value != null ? formatNumber(value, digits) : '—'}
        </span>
        {unit && (
          <span style={{ fontSize: 14, color: token.colorTextSecondary, marginLeft: 4 }}>
            {unit}
          </span>
        )}
      </div>
      {delta != null && (
        <div
          className="tabular"
          style={{
            fontSize: 12,
            color: statusTextColor(delta >= 0 ? 'good' : 'critical', mode),
            display: 'flex',
            alignItems: 'center',
            gap: 2,
          }}
        >
          {delta >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
          <span>{Math.abs(delta).toFixed(1)}%</span>
          {deltaLabel && <span style={{ color: token.colorTextTertiary, marginLeft: 4 }}>{deltaLabel}</span>}
        </div>
      )}
    </div>
  );

  return formula ? <Tooltip title={formula}>{content}</Tooltip> : content;
}
