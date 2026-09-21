import { createContext, useContext, useEffect, useRef } from 'react';

import type { WsHandler, WsStatus } from '../lib/ws';

export interface WsContextValue {
  status: WsStatus;
  lastHeartbeat: number | null;
  subscribe: (topics: string[], handler: WsHandler) => () => void;
}

export const WsContext = createContext<WsContextValue | null>(null);

function useWsContext(): WsContextValue {
  const value = useContext(WsContext);
  if (!value) throw new Error('WS hooks must be used inside WsProvider');
  return value;
}

export function useWsStatus(): Pick<WsContextValue, 'status' | 'lastHeartbeat'> {
  const { status, lastHeartbeat } = useWsContext();
  return { status, lastHeartbeat };
}

export function useWsSubscription(topics: string[], handler: WsHandler): void {
  const { subscribe } = useWsContext();
  const handlerRef = useRef(handler);
  const topicKey = topics.join('\n');

  useEffect(() => {
    handlerRef.current = handler;
  });

  useEffect(() => {
    if (!topicKey) return;
    return subscribe(topicKey.split('\n'), (message) => handlerRef.current(message));
  }, [subscribe, topicKey]);
}
