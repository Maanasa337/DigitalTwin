import { SendOutlined } from '@ant-design/icons';
import { Alert, Button, Flex, Input, Space, Spin } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ConfirmReadback } from '../../components/ConfirmReadback';
import { useApiError } from '../../hooks/useApiError';
import { useCancelAction, useConfirmAction, useSendUtterance } from '../../hooks/useVoice';
import { useUiStore } from '../../store/uiStore';
import { useVoiceStore } from '../../store/voiceStore';
import { Transcript } from './Transcript';

/**
 * Typed parity for every voice command (FR-NL-04): the same router, the same tiers and the same
 * read-back protocol, driven from a text box instead of a microphone.
 *
 * The read-back is a modal rather than an inline button because the operator must not be able to
 * keep typing past a pending T2 action — the confirmation is the point of the tier.
 */
export function ChatPanel({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const onError = useApiError();
  const language = useUiStore((s) => s.language);

  const { exchanges, sessionId, state, pendingAction } = useVoiceStore();
  const { say, applyTurn, setState, clearPendingAction, consumeNavigation } = useVoiceStore();

  const [text, setText] = useState('');
  const send = useSendUtterance();
  const confirm = useConfirmAction();
  const cancel = useCancelAction();

  // A navigate_dashboard turn changes the view; the store holds the path until a mounted panel
  // can push it, so the command works whether it came from the drawer or the /voice page.
  useEffect(() => {
    const path = consumeNavigation();
    if (path && path !== 'back') navigate(path);
    else if (path === 'back') navigate(-1);
  }, [consumeNavigation, navigate, exchanges.length]);

  const submit = useCallback(
    (utterance: string) => {
      const trimmed = utterance.trim();
      if (!trimmed || send.isPending) return;
      say('user', trimmed);
      setText('');
      setState('thinking');
      send.mutate(
        { text: trimmed, session_id: sessionId ?? undefined, lang: language, channel: 'chat' },
        {
          onSuccess: applyTurn,
          onError: (error) => {
            setState('idle');
            onError(error);
          },
        },
      );
    },
    [applyTurn, language, onError, say, send, sessionId, setState],
  );

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

      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPressEnter={() => submit(text)}
          placeholder={t('voice.placeholder')}
          aria-label={t('voice.placeholder')}
          maxLength={500}
          disabled={state === 'awaiting-confirmation'}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          loading={send.isPending}
          disabled={!text.trim() || state === 'awaiting-confirmation'}
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
