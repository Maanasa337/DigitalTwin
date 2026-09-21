import { QueryClient } from '@tanstack/react-query';

import { problemStatus } from './problem';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        const status = problemStatus(error);
        if (status !== undefined && status < 500) return false;
        return failureCount < 1;
      },
    },
    mutations: { retry: false },
  },
});
