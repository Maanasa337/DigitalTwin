import { http } from '../lib/axios';
import type {
  ExportRequest,
  ExportResult,
  FaultAccepted,
  FaultRequest,
  ResetResult,
  Scenario,
  ScenarioStarted,
  SimStatus,
} from './types';

export async function getScenarios(): Promise<Scenario[]> {
  const { data } = await http.get<Scenario[]>('/simulation/scenarios');
  return data;
}

export async function getSimStatus(): Promise<SimStatus> {
  const { data } = await http.get<SimStatus>('/simulation/status');
  return data;
}

export async function startScenario(scenarioCode: string): Promise<ScenarioStarted> {
  const { data } = await http.post<ScenarioStarted>('/simulation/scenario', { scenario_code: scenarioCode });
  return data;
}

export async function injectFault(body: FaultRequest): Promise<FaultAccepted> {
  const { data } = await http.post<FaultAccepted>('/simulation/faults', body);
  return data;
}

export async function setTimeScale(factor: number): Promise<{ time_scale: number }> {
  const { data } = await http.post<{ time_scale: number }>('/simulation/time-scale', { factor });
  return data;
}

export async function resetSimAsset(asset: string, componentCode: string | null = null): Promise<ResetResult> {
  const { data } = await http.post<ResetResult>(`/simulation/reset/${encodeURIComponent(asset)}`, {
    component_code: componentCode,
  });
  return data;
}

export async function exportDataset(body: ExportRequest): Promise<ExportResult> {
  const { data } = await http.post<ExportResult>('/simulation/export', body);
  return data;
}
