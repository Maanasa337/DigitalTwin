import { useQuery } from '@tanstack/react-query';

import { getMe } from '../api/core';

export function useMe() {
  return useQuery({ queryKey: ['core', 'me'], queryFn: getMe, staleTime: 5 * 60_000 });
}
