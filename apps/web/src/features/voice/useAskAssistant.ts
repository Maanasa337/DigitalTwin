import { useCallback } from 'react';

import type { TurnResponse } from '../../api/types';
import type { UtteranceBody } from '../../api/voice';
import { useApiError } from '../../hooks/useApiError';
import { useSendUtterance } from '../../hooks/useVoice';
import { useUiStore } from '../../store/uiStore';
import { useVoiceStore } from '../../store/voiceStore';

interface AskOptions {
  channel?: UtteranceBody['channel'];
  transcriptConfidence?: number;
  onAnswer?: (turn: TurnResponse) => void;
}

/**
 * The one way an utterance reaches the router, whether it was typed, spoken or a suggestion chip:
 * it lands in the shared transcript and continues the shared session. Returns false when the
 * assistant is busy (thinking, or waiting on a read-back) and the utterance was not sent.
 */
export function useAskAssistant() {
  const onError = useApiError();
  const language = useUiStore((s) => s.language);
  const sessionId = useVoiceStore((s) => s.sessionId);
  const { say, applyTurn, setState } = useVoiceStore();
  const send = useSendUtterance();

  const ask = useCallback(
    (utterance: string, { channel = 'chat', transcriptConfidence, onAnswer }: AskOptions = {}) => {
      const trimmed = utterance.trim();
      // Read the store rather than this mutation: the drawer and the page each hold their own.
      if (!trimmed || send.isPending || useVoiceStore.getState().state !== 'idle') return false;
      say('user', trimmed);
      setState('thinking');
      send.mutate(
        { text: trimmed, session_id: sessionId ?? undefined, lang: language, channel, transcript_confidence: transcriptConfidence },
        {
          onSuccess: (turn) => {
            applyTurn(turn);
            onAnswer?.(turn);
          },
          onError: (error) => {
            setState('idle');
            onError(error);
          },
        },
      );
      return true;
    },
    [applyTurn, language, onError, say, send, sessionId, setState],
  );

  return { ask, isPending: send.isPending };
}
