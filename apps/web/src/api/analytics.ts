import { http } from '../lib/axios';
import type {
  AnalyticsPeriod,
  AnalyticsScope,
  DowntimePareto,
  EnergyAnomaly,
  EnergyBaseline,
  EnergySummary,
  KpiDefinition,
  KpiSeries,
  OeeResult,
  ProductionPlan,
  Reliability,
} from './types';

export interface ScopeWindow {
  scope: AnalyticsScope;
  id: string;
  from: string;
  to: string;
}

export async function fetchKpiDefinitions(): Promise<KpiDefinition[]> {
  const { data } = await http.get<KpiDefinition[]>('/kpis/definitions');
  return data;
}

export async function fetchKpis(
  window: ScopeWindow & { period?: AnalyticsPeriod; codes?: string },
): Promise<KpiSeries[]> {
  const { data } = await http.get<KpiSeries[]>('/kpis', { params: window });
  return data;
}

export async function fetchOee(
  window: ScopeWindow & { period?: AnalyticsPeriod },
): Promise<OeeResult> {
  const { data } = await http.get<OeeResult>('/oee', { params: window });
  return data;
}

export async function fetchReliability(window: ScopeWindow): Promise<Reliability> {
  const { data } = await http.get<Reliability>('/reliability', { params: window });
  return data;
}

export async function fetchDowntimePareto(window: ScopeWindow): Promise<DowntimePareto> {
  const { data } = await http.get<DowntimePareto>('/downtime/pareto', { params: window });
  return data;
}

export async function fetchProductionPlan(window: ScopeWindow): Promise<ProductionPlan> {
  const { data } = await http.get<ProductionPlan>('/production/plan', { params: window });
  return data;
}

export async function fetchEnergySummary(window: ScopeWindow): Promise<EnergySummary> {
  const { data } = await http.get<EnergySummary>('/energy/summary', { params: window });
  return data;
}

export async function fetchEnergyAnomalies(window: ScopeWindow): Promise<EnergyAnomaly[]> {
  const { data } = await http.get<EnergyAnomaly[]>('/energy/anomalies', { params: window });
  return data;
}

export async function createEnergyBaseline(body: {
  scope: AnalyticsScope;
  scope_id: string;
  period_start: string;
  period_end: string;
}): Promise<EnergyBaseline> {
  const { data } = await http.post<EnergyBaseline>('/energy/baselines', body);
  return data;
}
