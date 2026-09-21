import { http } from '../lib/axios';
import type {
  Alarm,
  AlarmRule,
  AlarmSeverity,
  AlarmStatus,
  Page,
  TelemetryLatestResponse,
  TelemetrySeries,
} from './types';

// ── Telemetry ────────────────────────────────────────────────────────

export async function fetchTelemetry(
  asset: string,
  from: string,
  to: string,
  sensors?: string,
  agg?: string,
): Promise<TelemetrySeries[]> {
  const params: Record<string, string> = { asset, from, to };
  if (sensors) params.sensors = sensors;
  if (agg) params.agg = agg;
  const { data } = await http.get<TelemetrySeries[]>('/telemetry', { params });
  return data;
}

export async function fetchTelemetryLatest(asset: string): Promise<TelemetryLatestResponse> {
  const { data } = await http.get<TelemetryLatestResponse>('/telemetry/latest', { params: { asset } });
  return data;
}

// ── Alarms ───────────────────────────────────────────────────────────

export async function fetchAlarms(params: {
  page?: number;
  size?: number;
  severity?: AlarmSeverity;
  status?: AlarmStatus;
  asset_id?: string;
}): Promise<Page<Alarm>> {
  const { data } = await http.get<Page<Alarm>>('/alarms', { params });
  return data;
}

export async function ackAlarm(alarmId: string): Promise<Alarm> {
  const { data } = await http.post<Alarm>(`/alarms/${alarmId}/ack`);
  return data;
}

export async function shelveAlarm(alarmId: string, hours = 4): Promise<Alarm> {
  const { data } = await http.post<Alarm>(`/alarms/${alarmId}/shelve`, { action: 'shelve', shelve_hours: hours });
  return data;
}

export async function commentAlarm(alarmId: string, note: string): Promise<Alarm> {
  const { data } = await http.post<Alarm>(`/alarms/${alarmId}/comment`, { action: 'comment', note });
  return data;
}

export async function bulkAckAlarms(alarmIds: string[]): Promise<{ acknowledged: number }> {
  const { data } = await http.post<{ acknowledged: number }>('/alarms/bulk-ack', alarmIds);
  return data;
}

// ── Alarm Rules ──────────────────────────────────────────────────────

export async function fetchAlarmRules(params?: { page?: number; size?: number }): Promise<Page<AlarmRule>> {
  const { data } = await http.get<Page<AlarmRule>>('/alarm-rules', { params });
  return data;
}
