import { http } from '../lib/axios';
import type { Page, Report, ReportFormat, ReportSchedule, ReportStatus, ReportType } from './types';

export interface ReportFilters {
  page?: number;
  size?: number;
  type?: ReportType;
  status?: ReportStatus;
}

export interface ReportCreateBody {
  type: ReportType;
  scope?: string | null;
  scope_id?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  format?: ReportFormat;
}

export async function fetchReports(params?: ReportFilters): Promise<Page<Report>> {
  const { data } = await http.get<Page<Report>>('/reports', { params });
  return data;
}

export async function fetchReport(id: string): Promise<Report> {
  const { data } = await http.get<Report>(`/reports/${id}`);
  return data;
}

export async function createReport(body: ReportCreateBody): Promise<Report> {
  const { data } = await http.post<Report>('/reports', body);
  return data;
}

/** The file is fetched as a blob so the preview drawer and the download share one request path. */
export async function fetchReportFile(id: string, download = false): Promise<Blob> {
  const { data } = await http.get<Blob>(`/reports/${id}/file`, {
    params: { download },
    responseType: 'blob',
  });
  return data;
}

// ── Schedules ────────────────────────────────────────────────────────

export async function fetchSchedules(params?: { page?: number; size?: number }): Promise<Page<ReportSchedule>> {
  const { data } = await http.get<Page<ReportSchedule>>('/report-schedules', { params });
  return data;
}

export async function createSchedule(body: {
  type: ReportType;
  scope?: string | null;
  scope_id?: string | null;
  format: ReportFormat;
  cron: string;
  recipients?: string[];
}): Promise<ReportSchedule> {
  const { data } = await http.post<ReportSchedule>('/report-schedules', body);
  return data;
}

export async function updateSchedule(
  id: string,
  body: { cron?: string; recipients?: string[]; enabled?: boolean; format?: ReportFormat },
): Promise<ReportSchedule> {
  const { data } = await http.patch<ReportSchedule>(`/report-schedules/${id}`, body);
  return data;
}

export async function deleteSchedule(id: string): Promise<void> {
  await http.delete(`/report-schedules/${id}`);
}
