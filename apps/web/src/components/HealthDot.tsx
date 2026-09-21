import { Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';

import { healthLevel, STATUS_PALETTE, statusTextColor } from '../lib/status';
import { useUiStore } from '../store/uiStore';

export function HealthDot({ health }: { health: number | null }) {
  const { t } = useTranslation();
  const mode = useUiStore((s) => s.themeMode);
  const level = healthLevel(health);
  const { color, Icon } = STATUS_PALETTE[level];
  const label =
    health === null
      ? t('health.label', { value: t('status.noData') })
      : t('health.label', { value: `${Math.round(health)} · ${t(`status.level.${level}`)}` });

  return (
    <Tooltip title={label}>
      <span role="img" aria-label={label} className="tabular" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
        <Icon aria-hidden style={{ color, fontSize: 12 }} />
        <span aria-hidden style={{ fontSize: 12, color: statusTextColor(level, mode), minWidth: 18 }}>
          {health === null ? '—' : Math.round(health)}
        </span>
      </span>
    </Tooltip>
  );
}
