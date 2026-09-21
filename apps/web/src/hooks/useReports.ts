import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createReport,
  createSchedule,
  deleteSchedule,
  fetchReport,
  fetchReportFile,
  fetchReports,
  fetchSchedules,
  updateSchedule,
  type ReportCreateBody,
  type ReportFilters,
} from '../api/reports';

/** Queued and running reports are finished by the worker, so the list polls while any is in flight. */
const IN_FLIGHT_POLL_MS = 4000;

export function useReports(filters?: ReportFilters) {
  return useQuery({
    queryKey: ['reports', filters],
    queryFn: () => fetchReports(filters),
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => r.status === 'queued' || r.status === 'running')
        ? IN_FLIGHT_POLL_MS
        : false,
  });
}

export function useReport(id: string | undefined) {
  return useQuery({
    queryKey: ['report', id],
    queryFn: () => fetchReport(id!),
    enabled: Boolean(id),
  });
}

export function useReportFile(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['report-file', id],
    queryFn: () => fetchReportFile(id!),
    enabled: Boolean(id) && enabled,
    staleTime: Infinity,
  });
}

export function useCreateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ReportCreateBody) => createReport(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['reports'] });
    },
  });
}

// ── Schedules ────────────────────────────────────────────────────────

export function useReportSchedules() {
  return useQuery({ queryKey: ['report-schedules'], queryFn: () => fetchSchedules({ size: 100 }) });
}

function useScheduleMutation<T>(fn: (vars: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['report-schedules'] });
    },
  });
}

export function useCreateSchedule() {
  return useScheduleMutation(createSchedule);
}

export function useUpdateSchedule() {
  return useScheduleMutation(({ id, ...body }: { id: string; enabled?: boolean; cron?: string }) =>
    updateSchedule(id, body),
  );
}

export function useDeleteSchedule() {
  return useScheduleMutation(deleteSchedule);
}
