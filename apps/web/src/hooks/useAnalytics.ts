import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createEnergyBaseline,
  fetchDowntimePareto,
  fetchEnergyAnomalies,
  fetchEnergySummary,
  fetchKpiDefinitions,
  fetchKpis,
  fetchOee,
  fetchProductionPlan,
  fetchReliability,
  type ScopeWindow,
} from '../api/analytics';
import type { AnalyticsPeriod, AnalyticsScope } from '../api/types';

/** Analytics aggregates are rolled up hourly; refetching faster than that only burns queries. */
const ANALYTICS_STALE_MS = 60_000;

function enabled(window: Partial<ScopeWindow>): boolean {
  return Boolean(window.id && window.from && window.to);
}

export function useKpiDefinitions() {
  return useQuery({
    queryKey: ['kpi-definitions'],
    queryFn: fetchKpiDefinitions,
    staleTime: Infinity,
  });
}

export function useKpis(window: Partial<ScopeWindow> & { period?: AnalyticsPeriod; codes?: string }) {
  return useQuery({
    queryKey: ['kpis', window],
    queryFn: () => fetchKpis(window as ScopeWindow & { period?: AnalyticsPeriod }),
    enabled: enabled(window),
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useOee(window: Partial<ScopeWindow> & { period?: AnalyticsPeriod }) {
  return useQuery({
    queryKey: ['oee', window],
    queryFn: () => fetchOee(window as ScopeWindow),
    enabled: enabled(window),
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useReliability(window: Partial<ScopeWindow>) {
  return useQuery({
    queryKey: ['reliability', window],
    queryFn: () => fetchReliability(window as ScopeWindow),
    enabled: enabled(window),
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useDowntimePareto(window: Partial<ScopeWindow>) {
  return useQuery({
    queryKey: ['downtime-pareto', window],
    queryFn: () => fetchDowntimePareto(window as ScopeWindow),
    enabled: enabled(window),
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useProductionPlan(window: Partial<ScopeWindow>) {
  return useQuery({
    queryKey: ['production-plan', window],
    queryFn: () => fetchProductionPlan(window as ScopeWindow),
    enabled: enabled(window),
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useEnergySummary(window: Partial<ScopeWindow>) {
  return useQuery({
    queryKey: ['energy-summary', window],
    queryFn: () => fetchEnergySummary(window as ScopeWindow),
    enabled: enabled(window),
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useEnergyAnomalies(window: Partial<ScopeWindow>) {
  return useQuery({
    queryKey: ['energy-anomalies', window],
    queryFn: () => fetchEnergyAnomalies(window as ScopeWindow),
    enabled: enabled(window),
    staleTime: ANALYTICS_STALE_MS,
  });
}

export function useCreateEnergyBaseline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      scope: AnalyticsScope;
      scope_id: string;
      period_start: string;
      period_end: string;
    }) => createEnergyBaseline(body),
    onSuccess: () => {
      // A new baseline changes what counts as an anomaly and what the intensity line compares to.
      void queryClient.invalidateQueries({ queryKey: ['energy-anomalies'] });
      void queryClient.invalidateQueries({ queryKey: ['energy-summary'] });
    },
  });
}
