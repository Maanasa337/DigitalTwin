import { Card, Col, Empty, Flex, List, Row, Segmented, Space, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { IntentHelp, VoiceSession } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { useIntents, useVoiceSession, useVoiceSessions } from '../../hooks/useVoice';
import { formatDateTime } from '../../lib/format';
import { useUiStore } from '../../store/uiStore';
import { ChatPanel } from './ChatPanel';
import { TierBadge } from './TierBadge';
import { Transcript } from './Transcript';

/** `/voice`: the full console, the session history and the command cheat sheet (§M9 UI). */
export default function VoicePage() {
  const { t } = useTranslation();
  const language = useUiStore((s) => s.language);
  const setLanguage = useUiStore((s) => s.setLanguage);
  const [selected, setSelected] = useState<string>();

  const sessions = useVoiceSessions();
  const session = useVoiceSession(selected);
  const intents = useIntents();

  return (
    <>
      <PageHeader
        title={t('voice.pageTitle')}
        subtitle={t('voice.pageSubtitle')}
        actions={
          <Segmented
            value={language}
            onChange={(value) => setLanguage(value as 'en' | 'hi')}
            options={[
              { label: 'English', value: 'en' },
              { label: 'हिन्दी', value: 'hi' },
            ]}
            aria-label={t('topbar.language')}
          />
        }
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title={t('voice.title')} styles={{ body: { height: 480 } }}>
            <ChatPanel />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title={t('voice.commands')} styles={{ body: { maxHeight: 480, overflowY: 'auto' } }}>
            <CommandList intents={intents.data ?? []} lang={language} loading={intents.isLoading} />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title={t('voice.sessions')} loading={sessions.isLoading}>
            <SessionList
              sessions={sessions.data ?? []}
              selected={selected}
              onSelect={setSelected}
            />
          </Card>
        </Col>

        <Col xs={24} lg={14}>
          <Card title={t('voice.sessionTranscript')} loading={session.isLoading}>
            {session.data ? (
              <Transcript
                exchanges={session.data.turns.flatMap((turn) => [
                  ...(turn.transcript
                    ? [{ id: `${turn.id}-u`, role: 'user' as const, text: turn.transcript, at: 0 }]
                    : []),
                  ...(turn.response_text
                    ? [
                        {
                          id: `${turn.id}-a`,
                          role: 'assistant' as const,
                          text: turn.response_text,
                          at: 0,
                          intent: turn.intent ?? undefined,
                          tier: turn.tier ?? undefined,
                          router: turn.router ?? undefined,
                          citations: turn.citations ?? undefined,
                        },
                      ]
                    : []),
                ])}
              />
            ) : (
              <Empty description={t('voice.selectSession')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </>
  );
}

function CommandList({
  intents,
  lang,
  loading,
}: {
  intents: IntentHelp[];
  lang: string;
  loading: boolean;
}) {
  const { t } = useTranslation();
  return (
    <List
      loading={loading}
      dataSource={intents}
      locale={{ emptyText: t('common.noData') }}
      renderItem={(intent) => (
        <List.Item>
          <List.Item.Meta
            title={
              <Space size={6} wrap>
                <Typography.Text strong>{intent.intent.replace(/_/g, ' ')}</Typography.Text>
                <TierBadge tier={intent.tier} />
              </Space>
            }
            description={
              <Flex vertical gap={2}>
                <Typography.Text type="secondary">{intent.summary}</Typography.Text>
                <Typography.Text italic>“{intent.examples[lang] ?? intent.examples.en}”</Typography.Text>
              </Flex>
            }
          />
        </List.Item>
      )}
    />
  );
}

function SessionList({
  sessions,
  selected,
  onSelect,
}: {
  sessions: VoiceSession[];
  selected: string | undefined;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <Table<VoiceSession>
      size="small"
      rowKey="id"
      dataSource={sessions}
      pagination={{ pageSize: 8, hideOnSinglePage: true }}
      locale={{ emptyText: t('voice.noSessions') }}
      onRow={(row) => ({ onClick: () => onSelect(row.id), style: { cursor: 'pointer' } })}
      rowClassName={(row) => (row.id === selected ? 'ant-table-row-selected' : '')}
      columns={[
        {
          title: t('voice.startedAt'),
          dataIndex: 'started_at',
          render: (value: string) => formatDateTime(value),
        },
        {
          title: t('voice.channel'),
          dataIndex: 'channel',
          render: (value: string) => <Tag>{t(`voice.channelName.${value}`, { defaultValue: value })}</Tag>,
        },
        { title: t('voice.language'), dataIndex: 'lang', width: 90 },
      ]}
    />
  );
}
