/**
 * Zustand store for live WebSocket-driven twin state.
 *
 * Each asset's telemetry, prediction, alarm, and state updates are merged
 * into a single record. Components subscribe by selector to avoid re-render storms.
 */

import { create } from 'zustand';

import type { AssetStatus, LiveAsset, LiveMetric } from '../api/types';

interface LiveTwinState {
  assets: Record<string, LiveAsset>;

  /** Update telemetry metrics for an asset. */
  updateTelemetry: (code: string, metrics: Record<string, LiveMetric>) => void;

  /** Update prediction data for an asset. */
  updatePrediction: (
    code: string,
    data: {
      health_index?: number | null;
      rul_point?: number | null;
      rul_low?: number | null;
      rul_high?: number | null;
      confidence?: string | null;
    },
  ) => void;

  /** Update status for an asset. */
  updateStatus: (code: string, status: AssetStatus) => void;

  /** Increment alarm count for an asset. */
  incrementAlarmCount: (code: string) => void;
}

const EMPTY_ASSET = (code: string): LiveAsset => ({
  code,
  metrics: {},
  last_update: Date.now(),
});

export const useLiveTwinStore = create<LiveTwinState>()((set) => ({
  assets: {},

  updateTelemetry: (code, metrics) =>
    set((state) => {
      const existing = state.assets[code] ?? EMPTY_ASSET(code);
      return {
        assets: {
          ...state.assets,
          [code]: {
            ...existing,
            metrics: { ...existing.metrics, ...metrics },
            last_update: Date.now(),
          },
        },
      };
    }),

  updatePrediction: (code, data) =>
    set((state) => {
      const existing = state.assets[code] ?? EMPTY_ASSET(code);
      return {
        assets: {
          ...state.assets,
          [code]: {
            ...existing,
            ...(data.health_index !== undefined && { health: data.health_index }),
            ...(data.rul_point !== undefined && { rul_point: data.rul_point }),
            ...(data.rul_low !== undefined && { rul_low: data.rul_low }),
            ...(data.rul_high !== undefined && { rul_high: data.rul_high }),
            ...(data.confidence !== undefined && { confidence: data.confidence }),
            last_update: Date.now(),
          },
        },
      };
    }),

  updateStatus: (code, status) =>
    set((state) => {
      const existing = state.assets[code] ?? EMPTY_ASSET(code);
      return {
        assets: {
          ...state.assets,
          [code]: { ...existing, status, last_update: Date.now() },
        },
      };
    }),

  incrementAlarmCount: (code) =>
    set((state) => {
      const existing = state.assets[code] ?? EMPTY_ASSET(code);
      return {
        assets: {
          ...state.assets,
          [code]: {
            ...existing,
            alarm_count: (existing.alarm_count ?? 0) + 1,
            last_update: Date.now(),
          },
        },
      };
    }),
}));
