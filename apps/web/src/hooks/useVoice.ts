import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  cancelAction,
  confirmAction,
  endSession,
  fetchIntents,
  fetchSession,
  fetchSessions,
  fetchSuiteAccuracy,
  seedSuite,
  sendUtterance,
  type UtteranceBody,
} from '../api/voice';

export function useSendUtterance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UtteranceBody) => sendUtterance(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['voice-sessions'] });
    },
  });
}

/** Confirming or cancelling can create a work order, an alarm action or a report. */
function useActionMutation<T>(fn: (vars: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ['voice-sessions', 'work-orders', 'alarms', 'reports']) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useConfirmAction() {
  return useActionMutation(({ id, pin }: { id: string; pin?: string }) => confirmAction(id, pin));
}

export function useCancelAction() {
  return useActionMutation((id: string) => cancelAction(id));
}

export function useVoiceSessions(limit = 20) {
  return useQuery({ queryKey: ['voice-sessions', limit], queryFn: () => fetchSessions(limit) });
}

export function useVoiceSession(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['voice-session', sessionId],
    queryFn: () => fetchSession(sessionId!),
    enabled: Boolean(sessionId),
  });
}

export function useEndSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => endSession(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['voice-sessions'] });
    },
  });
}

export function useIntents() {
  return useQuery({
    queryKey: ['voice-intents'],
    queryFn: fetchIntents,
    // The command grammar is compiled into the API image; it cannot change while a tab is open.
    staleTime: Infinity,
  });
}

export function useSuiteAccuracy(enabled = true) {
  return useQuery({ queryKey: ['voice-suite-accuracy'], queryFn: fetchSuiteAccuracy, enabled });
}

export function useSeedSuite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: seedSuite,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['voice-suite-accuracy'] });
    },
  });
}
