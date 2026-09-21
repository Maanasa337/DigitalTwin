import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { LiveSocket, type WsStatus } from '../lib/ws';
import { useAuth } from './authContext';
import { WsContext, type WsContextValue } from './wsContext';

export function WsProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const [status, setStatus] = useState<WsStatus>('connecting');
  const [lastHeartbeat, setLastHeartbeat] = useState<number | null>(null);
  const [socket] = useState(
    () => new LiveSocket({ getToken: token, onStatus: setStatus, onHeartbeat: setLastHeartbeat }),
  );

  useEffect(() => {
    socket.start();
    return () => socket.stop();
  }, [socket]);

  const subscribe = useCallback<WsContextValue['subscribe']>(
    (topics, handler) => socket.subscribe(topics, handler),
    [socket],
  );
  const value = useMemo(() => ({ status, lastHeartbeat, subscribe }), [status, lastHeartbeat, subscribe]);

  return <WsContext.Provider value={value}>{children}</WsContext.Provider>;
}
