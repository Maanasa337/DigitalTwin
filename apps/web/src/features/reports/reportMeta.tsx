import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';

import type { ReportStatus, ReportType } from '../../api/types';

export const REPORT_TYPES: ReportType[] = [
  'machine_health',
  'weekly_maintenance',
  'energy',
  'benchmark',
  'incident',
];

/** Types that describe one machine; the generate modal makes the scope picker required for these. */
export const ASSET_SCOPED_TYPES: ReportType[] = ['machine_health', 'incident'];

const STATUS_META: Record<ReportStatus, { color: string; Icon: typeof CheckCircleOutlined }> = {
  queued: { color: 'default', Icon: ClockCircleOutlined },
  running: { color: 'processing', Icon: LoadingOutlined },
  done: { color: 'success', Icon: CheckCircleOutlined },
  failed: { color: 'error', Icon: CloseCircleOutlined },
};

/** Icon plus label, never colour alone (§9.1). */
export function ReportStatusTag({ status }: { status: ReportStatus }) {
  const { t } = useTranslation();
  const { color, Icon } = STATUS_META[status];
  return (
    <Tag color={color} icon={<Icon aria-hidden />} style={{ marginInlineEnd: 0 }}>
      {t(`reports.status.${status}`)}
    </Tag>
  );
}
