import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getTwin, getTwinTree, sendTwinCommand } from '../api/twin';
import type { TwinCommandRequest } from '../api/types';

export function useTwinTree() {
  return useQuery({ queryKey: ['twin', 'tree'], queryFn: getTwinTree });
}

export function useTwin(code: string) {
  return useQuery({
    queryKey: ['twin', 'twin', code],
    queryFn: () => getTwin(code),
    refetchInterval: 5_000,
    staleTime: 0,
  });
}

export function useTwinCommand(code: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TwinCommandRequest) => sendTwinCommand(code, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['twin'] }),
  });
}
