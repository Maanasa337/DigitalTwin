import {
  ExperimentOutlined,
  InfoCircleOutlined,
  MutedOutlined,
  SoundOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Divider, Flex, Popover, Skeleton, Tag, Tooltip, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '../../components/EmptyState';
import { useSensors } from '../../hooks/useAssets';
import { useSpeechSynthesis } from '../../hooks/useSpeech';
import { useCounterfactuals, useExplanation, useNarration } from '../../hooks/useXai';
import { AttributionWaterfall } from './AttributionWaterfall';
import { CounterfactualTable } from './CounterfactualTable';
import { FeedbackButtons } from './FeedbackButtons';
import { ReasonCardPanel } from './ReasonCardPanel';

interface ExplanationCardProps {
  explanationId?: string;
  /** The explained asset; its sensors feed the "suspect sensor" feedback option. */
  assetId?: string;
  /** Overrides the sensors loaded for `assetId`. */
  sensors?: { id: string; name: string }[];
  /** Overrides the browser's speech synthesis for the read-aloud button. */
  onSpeak?: (text: string) => void;
}

/**
 * The M6 explanation panel: narration, attribution waterfall, glass-box second opinion,
 * reason card, counterfactual and feedback. The narration can be read aloud in the app language.
 */
export function ExplanationCard({ explanationId, assetId, sensors, onSpeak }: ExplanationCardProps) {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const lang = i18n.language === 'hi' ? 'hi' : 'en';

  const { data: explanation, isLoading, isError } = useExplanation(explanationId);
  const { data: narration } = useNarration(explanationId, 'why', lang);
  const { data: counterfactuals } = useCounterfactuals(explanationId);
  const assetSensors = useSensors(sensors ? undefined : assetId);
  const speech = useSpeechSynthesis();

  if (!explanationId) {
    return (
      <Card size="small">
        <EmptyState
          icon={<ExperimentOutlined />}
          description={t('explain.none')}
        />
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card size="small">
        <Skeleton active paragraph={{ rows: 6 }} />
      </Card>
    );
  }

  if (isError || !explanation) {
    return (
      <Card size="small">
        <EmptyState
          icon={<ExperimentOutlined />}
          description={t('explain.failed')}
        />
      </Card>
    );
  }

  const agreement = explanation.agreement;
  const auditFailed = narration?.audit && !narration.audit.passed;
  const speaking = speech.speaking === explanation.id;
  const canSpeak = Boolean(onSpeak) || speech.supported;

  return (
    <Card
      size="small"
      title={
        <Flex align="center" gap={8} wrap>
          <span>{t('explain.title')}</span>
          <Tag style={{ marginInlineEnd: 0 }}>{explanation.method.replace(/_/g, ' ')}</Tag>
          {explanation.compute_ms != null && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {explanation.compute_ms} ms
            </Typography.Text>
          )}
        </Flex>
      }
      extra={
        narration && canSpeak ? (
          <Tooltip title={t(speaking ? 'explain.stopSpeaking' : 'explain.speak')}>
            <Button
              type="text"
              size="small"
              icon={speaking ? <MutedOutlined /> : <SoundOutlined />}
              aria-label={t(speaking ? 'explain.stopSpeaking' : 'explain.speak')}
              aria-pressed={speaking}
              onClick={() => {
                if (onSpeak) onSpeak(narration.final_text);
                else if (speaking) speech.stop();
                else speech.speak(narration.final_text, explanation.id);
              }}
              style={{ color: token.colorPrimary }}
            />
          </Tooltip>
        ) : null
      }
    >
      <Flex vertical gap={14}>
        {narration && (
          <Flex gap={8} align="start">
            <Typography.Paragraph style={{ margin: 0, fontSize: 14 }}>
              {narration.final_text}
            </Typography.Paragraph>
            {auditFailed && (
              <Tooltip
                title={t('explain.auditFallback')}
              >
                <InfoCircleOutlined style={{ color: token.colorWarning, marginTop: 4 }} />
              </Tooltip>
            )}
          </Flex>
        )}

        {agreement?.disagreement && (
          <Alert
            type="warning"
            showIcon
            icon={<WarningOutlined />}
            message={t('explain.disagreement')}
            description={t('explain.disagreementDetail')}
          />
        )}

        <div>
          <Flex justify="space-between" align="center" style={{ marginBottom: 8 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12, textTransform: 'uppercase' }}>
              {t('explain.drivers')}
            </Typography.Text>
            {agreement && (
              <Popover
                title={t('explain.secondOpinion')}
                content={
                  <Flex vertical gap={4} style={{ maxWidth: 280 }}>
                    <Typography.Text style={{ fontSize: 12 }}>
                      Production model: {agreement.shap_top3.join(', ')}
                    </Typography.Text>
                    <Typography.Text style={{ fontSize: 12 }}>
                      Glass-box (EBM): {agreement.ebm_top3.join(', ')}
                    </Typography.Text>
                  </Flex>
                }
              >
                <Tag
                  color={agreement.disagreement ? 'warning' : 'success'}
                  style={{ marginInlineEnd: 0, cursor: 'help' }}
                >
                  agreement {(agreement.shap_vs_ebm_top3_jaccard * 100).toFixed(0)}%
                </Tag>
              </Popover>
            )}
          </Flex>
          <AttributionWaterfall attributions={explanation.attributions} />
        </div>

        {explanation.reason_card && (
          <>
            <Divider style={{ margin: 0 }} />
            <ReasonCardPanel card={explanation.reason_card} />
          </>
        )}

        {counterfactuals && counterfactuals.length > 0 && (
          <>
            <Divider style={{ margin: 0 }} />
            <div>
              <Typography.Text
                type="secondary"
                style={{ fontSize: 12, textTransform: 'uppercase', display: 'block', marginBottom: 8 }}
              >
                {t('explain.counterfactual')}
              </Typography.Text>
              <CounterfactualTable counterfactuals={counterfactuals} />
            </div>
          </>
        )}

        <Divider style={{ margin: 0 }} />
        <Flex justify="space-between" align="center" wrap gap={8}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('explain.feedbackPrompt')}
          </Typography.Text>
          <FeedbackButtons explanationId={explanation.id} sensors={sensors ?? assetSensors.data} />
        </Flex>
      </Flex>
    </Card>
  );
}
