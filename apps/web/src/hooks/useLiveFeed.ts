import { useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { ASSET_STATUSES, type AssetStatus, type LiveMetric } from '../api/types';
import { useWsSubscription } from '../app/wsContext';
import type { WsMessage } from '../lib/ws';
import { useLiveTwinStore } from '../store/liveTwinStore';

const num = (value: unknown): number | null | undefined =>
  value === null ? null : typeof value === 'number' ? value : undefined;

const isStatus = (value: unknown): value is AssetStatus =>
  typeof value === 'string' && (ASSET_STATUSES as readonly string[]).includes(value);

/**
 * Feeds `liveTwinStore` from `/ws/live`: telemetry and predictions on `asset:{code}` (§6.2) and new
 * alarms on `alarms`. Alarm payloads carry the asset id, hence the id → code map.
 */
export function useLiveAssetFeed(assets: { id: string; code: string }[]): void {
  const queryClient = useQueryClient();
  const codes = assets.map((a) => a.code).join(',');
  const topics = useMemo(() => [...(codes ? codes.split(',').map((c) => `asset:${c}`) : []), 'alarms'], [codes]);
  const codeById = new Map(assets.map((a) => [a.id, a.code]));

  useWsSubscription(topics, (message: WsMessage) => {
    const store = useLiveTwinStore.getState();
    const asset = typeof message.asset === 'string' ? message.asset : undefined;
    if (message.type === 'telemetry' && asset) {
      const metrics = (message.metrics ?? {}) as Record<string, LiveMetric>;
      store.updateTelemetry(asset, metrics);
      const state = Object.entries(metrics).find(([name]) => name === 'state' || name.endsWith('.state'))?.[1]?.v;
      if (isStatus(state)) store.updateStatus(asset, state);
    } else if (message.type === 'prediction' && asset) {
      store.updatePrediction(asset, {
        health_index: num(message.health_index),
        rul_point: num(message.rul_point),
        rul_low: num(message.rul_low),
        rul_high: num(message.rul_high),
        confidence: typeof message.confidence === 'string' ? message.confidence : undefined,
      });
    } else if (message.type === 'alarm') {
      const code = typeof message.asset_id === 'string' ? codeById.get(message.asset_id) : undefined;
      if (code && message.status === 'active') store.incrementAlarmCount(code);
      void queryClient.invalidateQueries({ queryKey: ['alarms'] });
    }
  });
}
