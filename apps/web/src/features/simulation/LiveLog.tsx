import { CloseCircleFilled, InfoCircleFilled, WarningFilled } from '@ant-design/icons';
import { Card, Flex, Tag, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';

import type { LogLevel, SimLogEntry } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { formatDateTime, formatRelative } from '../../lib/format';
import { STATUS_PALETTE } from '../../lib/status';

// Info has no status colour of its own (§9.2); it takes the brand primary from the theme at render.
const LEVEL_ICON = {
  info: { Icon: InfoCircleFilled, color: null },
  warning: { Icon: WarningFilled, color: STATUS_PALETTE.warning.color },
  error: { Icon: CloseCircleFilled, color: STATUS_PALETTE.critical.color },
} as const satisfies Record<LogLevel, unknown>;

export function LiveLog({ entries }: { entries: SimLogEntry[] }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const newestFirst = [...entries].reverse().sort((a, b) => Date.parse(b.t) - Date.parse(a.t));

  return (
    <Card title={t('sim.log.title')} style={{ height: '100%' }} styles={{ body: { paddingBlock: 8 } }}>
      {newestFirst.length === 0 ? (
        <EmptyState description={t('sim.log.empty')} />
      ) : (
        <ol aria-label={t('sim.log.title')} style={{ listStyle: 'none', margin: 0, padding: 0, maxHeight: 480, overflowY: 'auto' }}>
          {newestFirst.map((entry, index) => {
            const { Icon, color: levelColor } = LEVEL_ICON[entry.level] ?? LEVEL_ICON.info;
            const color = levelColor ?? token.colorPrimary;
            return (
              <li key={`${entry.t}-${index}`} style={{ paddingBlock: 8 }}>
                <Flex gap={8} align="baseline">
                  <Icon aria-label={t(`sim.log.level.${entry.level}`)} style={{ color }} />
                  <Flex vertical flex={1} style={{ minWidth: 0 }}>
                    <span>
                      {entry.asset_code && <Tag style={{ marginInlineEnd: 6 }}>{entry.asset_code}</Tag>}
                      {entry.message}
                    </span>
                  </Flex>
                  <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }} title={formatDateTime(entry.t)}>
                    {formatRelative(entry.t)}
                  </Typography.Text>
                </Flex>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
