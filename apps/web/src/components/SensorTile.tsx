import { Badge, theme } from 'antd';
import type { CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';

import type { TelemetryLatestValue } from '../api/types';
import { formatNumber } from '../lib/format';
import { STATUS_PALETTE } from '../lib/status';

interface SensorTileProps {
  sensor: TelemetryLatestValue;
  /** Sparkline data points (last ~10 min). */
  sparkline?: number[];
  /** Optional threshold lines. */
  warnHigh?: number | null;
  alarmHigh?: number | null;
}

const QUALITY_GOOD = 192;

/**
 * Compact sensor tile: name, value+unit, 10-min sparkline, quality dot.
 */
export function SensorTile({ sensor, sparkline, warnHigh, alarmHigh }: SensorTileProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const isGood = sensor.quality >= QUALITY_GOOD;
  const qualityLabel = t(isGood ? 'sensor.qualityGood' : 'sensor.qualityBad');

  const containerStyle: CSSProperties = {
    background: token.colorBgContainer,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadiusLG,
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    minWidth: 160,
    position: 'relative',
  };

  const nameStyle: CSSProperties = {
    fontSize: 12,
    color: token.colorTextSecondary,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  };

  const valueStyle: CSSProperties = {
    fontSize: 20,
    fontWeight: 700,
    color: token.colorText,
    lineHeight: 1.2,
  };

  const unitStyle: CSSProperties = {
    fontSize: 12,
    color: token.colorTextSecondary,
    marginLeft: 3,
    fontWeight: 400,
  };

  return (
    <div style={containerStyle}>
      {/* Quality indicator */}
      <Badge
        status={isGood ? 'success' : 'error'}
        title={qualityLabel}
        aria-label={qualityLabel}
        style={{ position: 'absolute', top: 8, right: 8 }}
      />

      <div style={nameStyle} title={sensor.metric_name}>
        {sensor.name}
      </div>

      <div>
        <span style={valueStyle} className="tabular">
          {sensor.value != null ? formatNumber(sensor.value, sensor.unit === '°C' ? 1 : 2) : '—'}
        </span>
        <span style={unitStyle}>{sensor.unit}</span>
      </div>

      {/* Sparkline */}
      {sparkline && sparkline.length > 1 && (
        <MiniSparkline
          data={sparkline}
          height={28}
          color={token.colorPrimary}
          warnHigh={warnHigh}
          alarmHigh={alarmHigh}
        />
      )}
    </div>
  );
}

function MiniSparkline({
  data,
  height = 28,
  color,
  warnHigh,
  alarmHigh,
}: {
  data: number[];
  height?: number;
  color: string;
  warnHigh?: number | null;
  alarmHigh?: number | null;
}) {
  const width = 140;
  const padding = 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((v, i) => {
      const x = padding + (i / (data.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((v - min) / range) * (height - 2 * padding);
      return `${x},${y}`;
    })
    .join(' ');

  const thresholdY = (val: number) =>
    height - padding - ((val - min) / range) * (height - 2 * padding);

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {/* Warn threshold line */}
      {warnHigh != null && warnHigh >= min && warnHigh <= max && (
        <line x1={0} y1={thresholdY(warnHigh)} x2={width} y2={thresholdY(warnHigh)} stroke={STATUS_PALETTE.warning.color} strokeWidth={1} strokeDasharray="3,3" opacity={0.6} />
      )}
      {/* Alarm threshold line */}
      {alarmHigh != null && alarmHigh >= min && alarmHigh <= max && (
        <line x1={0} y1={thresholdY(alarmHigh)} x2={width} y2={thresholdY(alarmHigh)} stroke={STATUS_PALETTE.critical.color} strokeWidth={1} strokeDasharray="3,3" opacity={0.6} />
      )}
      <polyline fill="none" stroke={color} strokeWidth={1.5} points={points} />
    </svg>
  );
}
