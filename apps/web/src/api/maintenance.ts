import { http } from '../lib/axios';
import type {
  ObjectiveWeights,
  Page,
  Schedule,
  ScheduleConflict,
  ScheduleItem,
  Technician,
  TechnicianAvailability,
  WorkOrder,
  WorkOrderDetail,
  WorkOrderRisk,
  WorkOrderStatus,
  WorkOrderType,
} from './types';

// ── Technicians ──────────────────────────────────────────────────────

export async function fetchTechnicians(params?: { page?: number; size?: number }): Promise<Page<Technician>> {
  const { data } = await http.get<Page<Technician>>('/technicians', { params });
  return data;
}

export async function createTechnician(body: {
  code: string;
  name: string;
  skills?: string[];
  hourly_cost?: number;
}): Promise<Technician> {
  const { data } = await http.post<Technician>('/technicians', body);
  return data;
}

export async function fetchAvailability(
  technicianId: string,
  from: string,
  to: string,
): Promise<TechnicianAvailability[]> {
  const { data } = await http.get<TechnicianAvailability[]>(
    `/technicians/${technicianId}/availability`,
    { params: { from, to } },
  );
  return data;
}

// ── Work orders ──────────────────────────────────────────────────────

export interface WorkOrderFilters {
  page?: number;
  size?: number;
  asset_id?: string;
  status?: WorkOrderStatus;
  type?: WorkOrderType;
  technician_id?: string;
  open_only?: boolean;
}

export async function fetchWorkOrders(params?: WorkOrderFilters): Promise<Page<WorkOrder>> {
  const { data } = await http.get<Page<WorkOrder>>('/work-orders', { params });
  return data;
}

export async function fetchWorkOrder(id: string): Promise<WorkOrderDetail> {
  const { data } = await http.get<WorkOrderDetail>(`/work-orders/${id}`);
  return data;
}

export interface WorkOrderCreateBody {
  asset_id: string;
  component_id?: string;
  type?: WorkOrderType;
  priority?: number;
  title: string;
  description?: string;
  failure_mode_id?: string;
  explanation_id?: string;
  planned_start?: string;
  planned_end?: string;
  technician_id?: string;
  est_duration_min?: number;
  est_cost?: number;
  tasks?: { sequence: number; description: string }[];
}

export async function createWorkOrder(body: WorkOrderCreateBody): Promise<WorkOrder> {
  const { data } = await http.post<WorkOrder>('/work-orders', body);
  return data;
}

export async function updateWorkOrder(
  id: string,
  body: Partial<{
    priority: number;
    title: string;
    description: string;
    status: WorkOrderStatus;
    planned_start: string;
    planned_end: string;
    technician_id: string;
    est_duration_min: number;
    est_cost: number;
  }>,
): Promise<WorkOrder> {
  const { data } = await http.patch<WorkOrder>(`/work-orders/${id}`, body);
  return data;
}

export async function closeWorkOrder(
  id: string,
  body: { outcome: string; prediction_was_correct?: boolean; reset_damage?: boolean },
): Promise<WorkOrder> {
  const { data } = await http.post<WorkOrder>(`/work-orders/${id}/close`, body);
  return data;
}

export async function fetchWorkOrderRisk(id: string): Promise<WorkOrderRisk> {
  const { data } = await http.get<WorkOrderRisk>(`/work-orders/${id}/risk`);
  return data;
}

export async function exportWorkOrders(
  format: 'csv' | 'json' | 'b2mml',
  params?: { asset_id?: string; status?: WorkOrderStatus },
): Promise<Blob> {
  const { data } = await http.get('/work-orders/export', {
    params: { format, ...params },
    responseType: 'blob',
  });
  return data as Blob;
}

// ── Schedules ────────────────────────────────────────────────────────

export async function optimiseSchedule(body: {
  horizon_start: string;
  horizon_end: string;
  weights?: ObjectiveWeights;
  asset_ids?: string[];
  activate?: boolean;
}): Promise<Schedule> {
  const { data } = await http.post<Schedule>('/schedules/optimise', body);
  return data;
}

export async function fetchActiveSchedule(): Promise<Schedule | null> {
  const { data } = await http.get<Schedule | null>('/schedules/active');
  return data;
}

export async function fetchSchedule(id: string): Promise<Schedule> {
  const { data } = await http.get<Schedule>(`/schedules/${id}`);
  return data;
}

export async function patchScheduleItem(
  scheduleId: string,
  itemId: string,
  body: { starts_at?: string; ends_at?: string; technician_id?: string },
): Promise<{ item: ScheduleItem; conflicts: ScheduleConflict[] }> {
  const { data } = await http.patch(`/schedules/${scheduleId}/items/${itemId}`, body);
  return data;
}
