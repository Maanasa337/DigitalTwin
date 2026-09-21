import { CheckCircleTwoTone, ToolOutlined } from '@ant-design/icons';
import { Descriptions, Flex, Progress, Tag, Typography, theme } from 'antd';

import type { ReasonCard } from '../../api/types';
import { formatNumber } from '../../lib/format';

/**
 * The maintenance-facing half of an explanation: symptom, corroborating evidence, cause, action.
 *
 * Evidence that matches the failure mode's signature is ticked; evidence that does not is still
 * shown, because a top driver the mode does not explain is exactly what an engineer should notice.
 */
export function ReasonCardPanel({ card }: { card: ReasonCard }) {
  const { token } = theme.useToken();
  const confidencePct = Math.round(card.confidence * 100);

  return (
    <Flex vertical gap={12}>
      <Flex justify="space-between" align="center" wrap gap={8}>
        <Flex gap={8} align="center">
          <Tag color="volcano" style={{ marginInlineEnd: 0 }}>
            {card.failure_mode}
          </Tag>
          <Typography.Text strong>{card.symptom}</Typography.Text>
        </Flex>
        <Flex gap={6} align="center" style={{ minWidth: 150 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Match
          </Typography.Text>
          <Progress
            percent={confidencePct}
            size="small"
            style={{ width: 96, marginBottom: 0 }}
            status={confidencePct >= 60 ? 'normal' : 'exception'}
          />
        </Flex>
      </Flex>

      <div>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Evidence
        </Typography.Text>
        <Flex vertical gap={4} style={{ marginTop: 4 }}>
          {card.evidence.map((e) => (
            <Flex key={e.feature} gap={8} align="center">
              {e.supports_mode ? (
                <CheckCircleTwoTone twoToneColor={token.colorSuccess} style={{ fontSize: 12 }} />
              ) : (
                <span
                  aria-hidden
                  style={{
                    display: 'inline-block',
                    width: 12,
                    height: 12,
                    border: `1px solid ${token.colorBorder}`,
                    borderRadius: '50%',
                  }}
                />
              )}
              <Typography.Text style={{ fontSize: 13 }}>
                {e.label} at {formatNumber(e.value, 2)}
                {e.unit ? ` ${e.unit}` : ''}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {(e.share * 100).toFixed(0)}%
              </Typography.Text>
            </Flex>
          ))}
        </Flex>
      </div>

      <Descriptions size="small" column={1} colon={false} labelStyle={{ width: 110 }}>
        <Descriptions.Item label="Likely cause">{card.likely_cause}</Descriptions.Item>
        <Descriptions.Item label="Action">
          <Flex gap={6} align="start">
            <ToolOutlined style={{ marginTop: 4, color: token.colorTextTertiary }} />
            <span>{card.action}</span>
          </Flex>
        </Descriptions.Item>
        {card.parts.length > 0 && (
          <Descriptions.Item label="Parts">
            <Flex wrap gap={4}>
              {card.parts.map((part) => (
                <Tag key={part} style={{ marginInlineEnd: 0 }}>
                  {part}
                </Tag>
              ))}
            </Flex>
          </Descriptions.Item>
        )}
        {card.est_duration_min != null && (
          <Descriptions.Item label="Est. duration">{card.est_duration_min} min</Descriptions.Item>
        )}
      </Descriptions>
    </Flex>
  );
}
