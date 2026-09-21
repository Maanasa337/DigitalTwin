import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  exportDataset,
  getScenarios,
  getSimStatus,
  injectFault,
  resetSimAsset,
  setTimeScale,
  startScenario,
} from '../api/simulation';
import type { ExportRequest, FaultRequest, SimStatus } from '../api/types';

const STATUS_KEY = ['simulation', 'status'] as const;

export function useSimStatus() {
  return useQuery({ queryKey: STATUS_KEY, queryFn: getSimStatus, refetchInterval: 2_000, staleTime: 0 });
}

export function useScenarios() {
  return useQuery({ queryKey: ['simulation', 'scenarios'], queryFn: getScenarios, staleTime: 5 * 60_000 });
}

function useRefreshStatus() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: STATUS_KEY });
}

export function useStartScenario() {
  const onSettled = useRefreshStatus();
  return useMutation({ mutationFn: (code: string) => startScenario(code), onSettled });
}

export function useInjectFault() {
  const onSettled = useRefreshStatus();
  return useMutation({ mutationFn: (body: FaultRequest) => injectFault(body), onSettled });
}

export function useSetTimeScale() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (factor: number) => setTimeScale(factor),
    onSuccess: ({ time_scale }) =>
      queryClient.setQueryData<SimStatus>(STATUS_KEY, (prev) => prev && { ...prev, time_scale }),
  });
}

export function useResetSimAsset() {
  const onSettled = useRefreshStatus();
  return useMutation({ mutationFn: (asset: string) => resetSimAsset(asset), onSettled });
}

export function useExportDataset() {
  return useMutation({ mutationFn: (body: ExportRequest) => exportDataset(body) });
}
