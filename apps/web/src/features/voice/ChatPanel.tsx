import { AudioOutlined, SendOutlined, SoundOutlined } from '@ant-design/icons';
import { Alert, Button, Flex, Input, Space, Spin, Tooltip, Typography } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ConfirmReadback } from '../../components/ConfirmReadback';
import { useApiError } from '../../hooks/useApiError';
import { useSpeechRecognition, useSpeechSynthesis } from '../../hooks/useSpeech';
import { useCancelAction, useConfirmAction } from '../../hooks/useVoice';
import { useVoiceStore } from '../../store/voiceStore';
import { Transcript } from './Transcript';
import { useAskAssistant } from './useAskAssistant';

/**
 * Every voice command, typed or spoken (FR-NL-04): the same router, the same tiers and the same
 * read-back protocol. The microphone is push-to-talk through the browser's speech recognition; its
 * final transcript goes down exactly the path typed text does, and a spoken question gets a spoken
 * answer.
 *
 * The read-back is a modal rather than an inline button because the operator must not be able to
 * keep typing past a pending T2 action — the confirmation is the point of the tier.
 */
export function ChatPanel({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const onError = useApiError();

  const { exchanges, state, pendingAction } = useVoiceStore();
  const { say, clearPendingAction, consumeNavigation } = useVoiceStore();

  const [text, setText] = useState('');
  const { ask, isPending } = useAskAssistant();
  const confirm = useConfirmAction();
  const cancel = useCancelAction();
  const speech = useSpeechSynthesis();

  // A navigate_dashboard turn changes the view; the store holds the path until a mounted panel
  // can push it, so the command works whether it came from the drawer or the /voice page.
  useEffect(() => {
    const path = consumeNavigation();
    if (path && path !== 'back') navigate(path);
    else if (path === 'back') navigate(-1);
  }, [consumeNavigation, navigate, exchanges.length]);

  const submit = useCallback(
    (utterance: string) => {
      if (ask(utterance)) setText('');
    },
    [ask],
  );

  const mic = useSpeechRecognition((transcript, confidence) => {
    ask(transcript, {
      channel: 'voice',
      transcriptConfidence: confidence || undefined,
      onAnswer: (turn) => speech.speak(turn.text),
    });
  });

  const talk = () => {
    if (mic.listening) {
      mic.stop();
      return;
    }
    // The operator is about to speak; the assistant should stop talking over them.
    speech.stop();
    mic.start();
  };

  const resolve = (mutation: typeof confirm | typeof cancel, vars: never) =>
    mutation.mutate(vars, {
      onSuccess: (action) => {
        const { status } = action as { status: string };
        clearPendingAction();
        say('assistant', t(`voice.outcome.${status}`, { defaultValue: status }), {
          tier: pendingAction?.tier,
        });
      },
      onError: (error) => {
        clearPendingAction();
        onError(error);
      },
    });

  return (
    <Flex vertical gap={12} style={{ height: '100%', minHeight: compact ? 320 : 420 }}>
      <div style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}>
        <Transcript exchanges={exchanges} onSuggestion={submit} />
        {state === 'thinking' && (
          <Flex justify="center" style={{ padding: 12 }}>
            <Spin size="small" aria-label={t('voice.thinking')} />
          </Flex>
        )}
      </div>

      {exchanges.length === 0 && (
        <Alert type="info" showIcon message={t('voice.hint')} style={{ marginBottom: 0 }} />
      )}

      {(mic.listening || mic.error || speech.speaking) && (
        <Flex align="center" gap={8} role="status" aria-live="polite">
          {mic.listening ? (
            <Typography.Text type="secondary">{t('voice.mic.listening')}</Typography.Text>
          ) : mic.error ? (
            <Typography.Text type="warning">{t(`voice.mic.error.${mic.error}`)}</Typography.Text>
          ) : (
            <>
              <SoundOutlined aria-hidden />
              <Typography.Text type="secondary">{t('voice.speaking')}</Typography.Text>
              <Button size="small" type="link" onClick={speech.stop} style={{ paddingInline: 0 }}>
                {t('voice.stopSpeaking')}
              </Button>
            </>
          )}
        </Flex>
      )}

      <Space.Compact style={{ width: '100%' }}>
        <Input
          // While listening the box shows the words as they are recognised; they submit on their own.
          value={mic.listening ? mic.interim : text}
          readOnly={mic.listening}
          onChange={(e) => setText(e.target.value)}
          onPressEnter={() => !mic.listening && submit(text)}
          placeholder={t(mic.listening ? 'voice.mic.listening' : 'voice.placeholder')}
          aria-label={t('voice.placeholder')}
          maxLength={500}
          disabled={state === 'awaiting-confirmation'}
        />
        <Tooltip
          title={
            mic.supported ? t(mic.listening ? 'voice.mic.stop' : 'voice.mic.start') : t('voice.mic.unsupported')
          }
        >
          <Button
            icon={<AudioOutlined />}
            type={mic.listening ? 'primary' : 'default'}
            danger={mic.listening}
            aria-pressed={mic.listening}
            aria-label={t(mic.listening ? 'voice.mic.stop' : 'voice.mic.start')}
            disabled={!mic.supported || (!mic.listening && state !== 'idle')}
            onClick={talk}
          />
        </Tooltip>
        <Button
          type="primary"
          icon={<SendOutlined />}
          loading={isPending}
          disabled={!text.trim() || mic.listening || state === 'awaiting-confirmation'}
          onClick={() => submit(text)}
        >
          {t('voice.send')}
        </Button>
      </Space.Compact>

      <ConfirmReadback
        open={Boolean(pendingAction)}
        text={pendingAction?.readback ?? ''}
        requirePin={pendingAction?.tier === 'T3'}
        loading={confirm.isPending || cancel.isPending}
        onConfirm={(pin) =>
          pendingAction && resolve(confirm, { id: pendingAction.id, pin } as never)
        }
        onCancel={() => pendingAction && resolve(cancel, pendingAction.id as never)}
      />
    </Flex>
  );
}
