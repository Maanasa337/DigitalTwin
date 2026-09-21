import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';

import type { AssetStatus } from '../api/types';
import { assetStatusLevel, healthLevel, STATUS_PALETTE, statusTextColor, withAlpha, type StatusLevel } from '../lib/status';
import { useUiStore } from '../store/uiStore';

type StatusTagProps = ({ status: AssetStatus; health?: never } | { health: number | null; status?: never }) & {
  compact?: boolean;
};

export function StatusTag(props: StatusTagProps) {
  const { t } = useTranslation();
  const mode = useUiStore((s) => s.themeMode);

  let level: StatusLevel;
  let label: string;
  if (props.status !== undefined) {
    level = assetStatusLevel(props.status);
    label = t(`status.asset.${props.status}`);
  } else {
    level = healthLevel(props.health);
    label =
      props.health === null ? t('status.noData') : `${Math.round(props.health)} · ${t(`status.level.${level}`)}`;
  }
  const { color, Icon } = STATUS_PALETTE[level];

  return (
    <Tag
      bordered={false}
      icon={<Icon aria-hidden />}
      data-level={level}
      className="tabular"
      style={{
        background: withAlpha(color, 0.16),
        color: statusTextColor(level, mode),
        borderRadius: 999,
        marginInlineEnd: 0,
        fontSize: props.compact ? 12 : 14,
        lineHeight: props.compact ? '20px' : '24px',
        paddingInline: props.compact ? 6 : 10,
      }}
    >
      {label}
    </Tag>
  );
}
