import { useQueries, useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

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

/**
 * Fleet-wide alarm count per severity under the same status filter. Each is a `size=1` page read
 * only for its `total`, so the tiles stay correct however many alarms sit beyond the table's page.
 */
export function useAlarmSeverityCounts(
  severities: AlarmSeverity[],
  status?: AlarmStatus,
): Partial<Record<AlarmSeverity, number>> {
  return useQueries({
    queries: severities.map((severity) => ({
      queryKey: ['alarms', { size: 1, severity, status }],
      queryFn: () => fetchAlarms({ size: 1, severity, status }),
      refetchInterval: 10_000,
    })),
    combine: (results) =>
      Object.fromEntries(
        results.flatMap((r, i) => (r.data ? [[severities[i], r.data.total]] : [])),
      ) as Partial<Record<AlarmSeverity, number>>,
  });
}

export function useAlarmRules(page = 1, size = 50) {
  return useQuery({
    queryKey: ['alarm-rules', page, size],
    queryFn: () => fetchAlarmRules({ page, size }),
  });
}

/** Active alarms per asset id: the baseline the live `alarms` topic then increments. */
export function useActiveAlarmCounts(): Record<string, number> {
  const { data } = useAlarms({ status: 'active', size: 200 });
  return useMemo(() => {
    const counts: Record<string, number> = {};
    for (const alarm of data?.items ?? []) counts[alarm.asset_id] = (counts[alarm.asset_id] ?? 0) + 1;
    return counts;
  }, [data]);
}
