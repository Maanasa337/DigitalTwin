import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  closeWorkOrder,
  createWorkOrder,
  fetchActiveSchedule,
  fetchSchedule,
  fetchTechnicians,
  fetchWorkOrder,
  fetchWorkOrderRisk,
  fetchWorkOrders,
  optimiseSchedule,
  patchScheduleItem,
  updateWorkOrder,
  type WorkOrderCreateBody,
  type WorkOrderFilters,
} from '../api/maintenance';
import type { ObjectiveWeights } from '../api/types';

export function useWorkOrders(filters?: WorkOrderFilters) {
  return useQuery({
    queryKey: ['work-orders', filters],
    queryFn: () => fetchWorkOrders(filters),
  });
}

export function useWorkOrder(id: string | undefined) {
  return useQuery({
    queryKey: ['work-order', id],
    queryFn: () => fetchWorkOrder(id!),
    enabled: Boolean(id),
  });
}

export function useWorkOrderRisk(id: string | undefined) {
  return useQuery({
    queryKey: ['work-order-risk', id],
    queryFn: () => fetchWorkOrderRisk(id!),
    enabled: Boolean(id),
  });
}

export function useTechnicians() {
  return useQuery({
    queryKey: ['technicians'],
    queryFn: () => fetchTechnicians({ size: 200 }),
    staleTime: 5 * 60_000,
  });
}

/** Any write to an order can change the schedule it sits in, so both caches are invalidated. */
function useOrderMutation<TVariables, TData>(fn: (vars: TVariables) => Promise<TData>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['work-orders'] });
      void queryClient.invalidateQueries({ queryKey: ['work-order'] });
      void queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });
}

export function useCreateWorkOrder() {
  return useOrderMutation((body: WorkOrderCreateBody) => createWorkOrder(body));
}

export function useUpdateWorkOrder() {
  return useOrderMutation(
    ({ id, ...body }: { id: string } & Parameters<typeof updateWorkOrder>[1]) =>
      updateWorkOrder(id, body),
  );
}

export function useCloseWorkOrder() {
  return useOrderMutation(
    ({ id, ...body }: { id: string; outcome: string; prediction_was_correct?: boolean }) =>
      closeWorkOrder(id, body),
  );
}

export function useActiveSchedule() {
  return useQuery({
    queryKey: ['schedule', 'active'],
    queryFn: fetchActiveSchedule,
  });
}

export function useSchedule(id: string | undefined) {
  return useQuery({
    queryKey: ['schedule', id],
    queryFn: () => fetchSchedule(id!),
    enabled: Boolean(id),
  });
}

export function useOptimiseSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      horizon_start: string;
      horizon_end: string;
      weights?: ObjectiveWeights;
      asset_ids?: string[];
    }) => optimiseSchedule({ activate: true, ...body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['schedule'] });
      void queryClient.invalidateQueries({ queryKey: ['work-orders'] });
    },
  });
}

export function usePatchScheduleItem(scheduleId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      itemId,
      ...body
    }: {
      itemId: string;
      starts_at?: string;
      ends_at?: string;
      technician_id?: string;
    }) => patchScheduleItem(scheduleId!, itemId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['schedule'] });
    },
  });
}
