import { Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';

import type { FidelityLevel } from '../../api/types';

export function FidelityBadge({ level, compact = false }: { level: FidelityLevel; compact?: boolean }) {
  const { t } = useTranslation();
  const full = `L${level} ${t(`twin.fidelity.${level}`)}`;
  return (
    <Tooltip title={compact ? full : t('twin.fidelity.tooltip')}>
      <Tag
        color="blue"
        bordered={false}
        aria-label={full}
        style={{ borderRadius: 999, marginInlineEnd: 0, fontSize: compact ? 12 : 14 }}
      >
        {compact ? `L${level}` : full}
      </Tag>
    </Tooltip>
  );
}
