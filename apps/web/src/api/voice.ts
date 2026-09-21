import { http } from '../lib/axios';
import type {
  IntentHelp,
  SuiteAccuracy,
  TurnResponse,
  VoiceAction,
  VoiceSession,
  VoiceSessionDetail,
} from './types';

export interface UtteranceBody {
  text: string;
  session_id?: string;
  lang?: 'en' | 'hi';
  channel?: 'voice' | 'chat';
  transcript_confidence?: number;
  stt_ms?: number;
  snr_db?: number;
}

/** Typed chat. The speech client posts the same body to /voice/turns with its STT metadata. */
export async function sendUtterance(body: UtteranceBody): Promise<TurnResponse> {
  const { data } = await http.post<TurnResponse>('/chat', body);
  return data;
}

export async function confirmAction(actionId: string, pin?: string): Promise<VoiceAction> {
  const { data } = await http.post<VoiceAction>(`/voice/actions/${actionId}/confirm`, { pin });
  return data;
}

export async function cancelAction(actionId: string): Promise<VoiceAction> {
  const { data } = await http.post<VoiceAction>(`/voice/actions/${actionId}/cancel`, {});
  return data;
}

export async function fetchSessions(limit = 20): Promise<VoiceSession[]> {
  const { data } = await http.get<VoiceSession[]>('/voice/sessions', { params: { limit } });
  return data;
}

export async function fetchSession(sessionId: string): Promise<VoiceSessionDetail> {
  const { data } = await http.get<VoiceSessionDetail>(`/voice/sessions/${sessionId}`);
  return data;
}

export async function endSession(sessionId: string): Promise<VoiceSession> {
  const { data } = await http.post<VoiceSession>(`/voice/sessions/${sessionId}/end`, {});
  return data;
}

export async function fetchIntents(): Promise<IntentHelp[]> {
  const { data } = await http.get<IntentHelp[]>('/voice/intents');
  return data;
}

export async function fetchSuiteAccuracy(): Promise<SuiteAccuracy[]> {
  const { data } = await http.get<SuiteAccuracy[]>('/voice/suite-accuracy');
  return data;
}

export async function seedSuite(): Promise<{ seeded: number }> {
  const { data } = await http.post<{ seeded: number }>('/voice/suite', {});
  return data;
}
