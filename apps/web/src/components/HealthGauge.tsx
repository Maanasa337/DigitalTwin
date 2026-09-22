import { Tooltip, theme } from 'antd';
import { type CSSProperties, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { healthLevel, STATUS_PALETTE } from '../lib/status';

interface HealthGaugeProps {
  health: number | null | undefined;
  size?: number;
  showLabel?: boolean;
  anomalyScore?: number | null;
}

/**
 * 72px ring gauge showing health 0–100 with colour by health band.
 * Shows tooltip with anomaly score if available.
 */
export function HealthGauge({ health, size = 72, showLabel = true, anomalyScore }: HealthGaugeProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const level = healthLevel(health);
  const color = STATUS_PALETTE[level].color;

  const strokeWidth = size * 0.12;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = health != null ? Math.max(0, Math.min(100, health)) / 100 : 0;
  const dashOffset = circumference * (1 - pct);

  const containerStyle: CSSProperties = {
    width: size,
    height: size,
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  };

  const labelStyle: CSSProperties = {
    position: 'absolute',
    textAlign: 'center',
    fontSize: size * 0.24,
    fontWeight: 700,
    color: color,
    lineHeight: 1,
  };

  const tooltipText = useMemo(() => {
    const parts: string[] = [];
    if (health != null) parts.push(t('health.label', { value: `${health.toFixed(0)} %` }));
    if (anomalyScore != null) parts.push(t('health.anomaly', { value: anomalyScore.toFixed(3) }));
    return parts.join(' · ') || t('status.noData');
  }, [health, anomalyScore, t]);

  return (
    <Tooltip title={tooltipText}>
      <div
        style={containerStyle}
        role="meter"
        aria-label={tooltipText}
        aria-valuenow={health ?? 0}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Background ring */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={token.colorBorderSecondary}
            strokeWidth={strokeWidth}
            opacity={0.3}
          />
          {/* Value arc */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.3s ease' }}
          />
        </svg>
        {showLabel && (
          <span style={labelStyle} className="tabular" aria-hidden>
            {health != null ? Math.round(health) : '—'}
          </span>
        )}
      </div>
    </Tooltip>
  );
}
