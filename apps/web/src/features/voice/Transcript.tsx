import { Button, Flex, Space, Tag, Typography, theme } from 'antd';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { EmptyState } from '../../components/EmptyState';
import type { Exchange } from '../../store/voiceStore';
import { TierBadge } from './TierBadge';

interface TranscriptProps {
  exchanges: Exchange[];
  onSuggestion?: (label: string) => void;
}

/** The visible record of the conversation. Every spoken answer is also readable here (FR-VN-08). */
export function Transcript({ exchanges, onSuggestion }: TranscriptProps) {
  const { t } = useTranslation();
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' });
  }, [exchanges.length]);

  if (exchanges.length === 0) {
    return <EmptyState description={t('voice.emptyTranscript')} />;
  }

  return (
    <Flex vertical gap={12} role="log" aria-live="polite" aria-label={t('voice.transcript')}>
      {exchanges.map((exchange) => (
        <Bubble key={exchange.id} exchange={exchange} onSuggestion={onSuggestion} />
      ))}
      <div ref={bottom} />
    </Flex>
  );
}

function Bubble({ exchange, onSuggestion }: { exchange: Exchange; onSuggestion?: (label: string) => void }) {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const mine = exchange.role === 'user';
  const citations = Object.entries(exchange.citations ?? {});

  return (
    <Flex vertical gap={4} align={mine ? 'flex-end' : 'flex-start'}>
      <div
        style={{
          maxWidth: '88%',
          padding: '8px 12px',
          borderRadius: 10,
          background: mine ? token.colorPrimaryBg : token.colorBgElevated,
          border: `1px solid ${token.colorBorder}`,
        }}
      >
        <Typography.Text>{exchange.text}</Typography.Text>
      </div>

      {!mine && (exchange.tier || exchange.router) && (
        <Space size={4} wrap>
          {exchange.tier && <TierBadge tier={exchange.tier} />}
          {exchange.intent && <Tag>{exchange.intent.replace(/_/g, ' ')}</Tag>}
          {exchange.router && (
            <Tag color={exchange.router === 'rules' ? 'green' : 'purple'}>
              {t(`voice.router.${exchange.router}`, { defaultValue: exchange.router })}
            </Tag>
          )}
          {exchange.hypothetical && <Tag color="blue">{t('voice.hypothetical')}</Tag>}
        </Space>
      )}

      {citations.length > 0 && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('voice.citations')}:{' '}
          {citations.map(([key, value]) => `${key.replace(/_/g, ' ')} ${String(value)}`).join(' · ')}
        </Typography.Text>
      )}

      {exchange.suggestions && exchange.suggestions.length > 0 && (
        <Space size={4} wrap>
          {exchange.suggestions.map((suggestion) => (
            <Button key={suggestion.value} size="small" onClick={() => onSuggestion?.(suggestion.label)}>
              {suggestion.label}
            </Button>
          ))}
        </Space>
      )}
    </Flex>
  );
}
