import { useQuery } from '@tanstack/react-query';

import { fetchAlarms, fetchAlarmRules, fetchTelemetry, fetchTelemetryLatest } from '../api/telemetry';
import type { AlarmSeverity, AlarmStatus } from '../api/types';

export function useTelemetry(asset: string, from: string, to: string, sensors?: string, agg?: string) {
  return useQuery({
    queryKey: ['telemetry', asset, from, to, sensors, agg],
    queryFn: () => fetchTelemetry(asset, from, to, sensors, agg),
    enabled: Boolean(asset && from && to),
    refetchInterval: 10_000,
  });
}

export function useTelemetryLatest(asset: string) {
  return useQuery({
    queryKey: ['telemetry-latest', asset],
    queryFn: () => fetchTelemetryLatest(asset),
    enabled: Boolean(asset),
    refetchInterval: 5_000,
  });
}

export function useAlarms(params: {
  page?: number;
  size?: number;
  severity?: AlarmSeverity;
  status?: AlarmStatus;
  asset_id?: string;
}) {
  return useQuery({
    queryKey: ['alarms', params],
    queryFn: () => fetchAlarms(params),
    refetchInterval: 10_000,
  });
}

export function useAlarmRules(page = 1, size = 50) {
  return useQuery({
    queryKey: ['alarm-rules', page, size],
    queryFn: () => fetchAlarmRules({ page, size }),
  });
}
