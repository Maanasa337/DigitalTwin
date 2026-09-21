import { create } from 'zustand';

import type { TurnResponse, VoiceAction, VoiceSuggestion } from '../api/types';

export type AssistantState = 'idle' | 'thinking' | 'awaiting-confirmation';

export interface Exchange {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  at: number;
  intent?: string;
  tier?: string;
  router?: string;
  confidence?: number;
  hypothetical?: boolean;
  citations?: Record<string, unknown>;
  suggestions?: VoiceSuggestion[];
}

interface VoiceState {
  open: boolean;
  sessionId: string | null;
  state: AssistantState;
  exchanges: Exchange[];
  /** The one read-back waiting for the operator; the confirm modal is driven by its presence. */
  pendingAction: VoiceAction | null;
  /** Set by a navigate_dashboard turn; the console consumes it and pushes the router. */
  pendingNavigation: string | null;

  setOpen: (open: boolean) => void;
  setState: (state: AssistantState) => void;
  say: (role: Exchange['role'], text: string, extra?: Partial<Exchange>) => void;
  applyTurn: (turn: TurnResponse) => void;
  clearPendingAction: () => void;
  consumeNavigation: () => string | null;
  reset: () => void;
}

let sequence = 0;
const nextId = () => `x${++sequence}`;

export const useVoiceStore = create<VoiceState>((set, get) => ({
  open: false,
  sessionId: null,
  state: 'idle',
  exchanges: [],
  pendingAction: null,
  pendingNavigation: null,

  setOpen: (open) => set({ open }),
  setState: (state) => set({ state }),

  say: (role, text, extra) =>
    set((s) => ({ exchanges: [...s.exchanges, { id: nextId(), role, text, at: Date.now(), ...extra }] })),

  applyTurn: (turn) =>
    set((s) => ({
      sessionId: turn.session_id,
      state: turn.action && turn.action.status === 'pending' ? 'awaiting-confirmation' : 'idle',
      pendingAction: turn.action && turn.action.status === 'pending' ? turn.action : null,
      pendingNavigation: turn.navigate?.path ?? s.pendingNavigation,
      exchanges: [
        ...s.exchanges,
        {
          id: nextId(),
          role: 'assistant',
          text: turn.text,
          at: Date.now(),
          intent: turn.intent,
          tier: turn.tier,
          router: turn.router,
          confidence: turn.confidence,
          hypothetical: turn.hypothetical,
          citations: turn.citations,
          suggestions: turn.suggestions,
        },
      ],
    })),

  clearPendingAction: () => set({ pendingAction: null, state: 'idle' }),

  consumeNavigation: () => {
    const path = get().pendingNavigation;
    if (path) set({ pendingNavigation: null });
    return path;
  },

  reset: () => set({ sessionId: null, exchanges: [], pendingAction: null, state: 'idle' }),
}));
