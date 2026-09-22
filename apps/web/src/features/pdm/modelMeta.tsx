import { CheckCircleOutlined, ExperimentOutlined, InboxOutlined } from '@ant-design/icons';
import { Tag } from 'antd';
import { useTranslation } from 'react-i18next';

import type { ModelStage } from '../../api/types';

const STAGE_META: Record<ModelStage, { color: string; Icon: typeof CheckCircleOutlined }> = {
  candidate: { color: 'processing', Icon: ExperimentOutlined },
  production: { color: 'success', Icon: CheckCircleOutlined },
  archived: { color: 'default', Icon: InboxOutlined },
};

/** Icon plus label, never colour alone (§9.1). */
export function ModelStageTag({ stage }: { stage: ModelStage }) {
  const { t } = useTranslation();
  const { color, Icon } = STAGE_META[stage];
  return (
    <Tag color={color} icon={<Icon aria-hidden />} style={{ marginInlineEnd: 0 }}>
      {t(`models.stageName.${stage}`)}
    </Tag>
  );
}
