import { useQuery } from '@tanstack/react-query';

import { fetchGrafanaHealth } from '../api/grafana';

/** Checked before the iframe renders, so a stopped Grafana shows a hint rather than a proxy error page. */
export function useGrafanaHealth() {
  return useQuery({
    queryKey: ['grafana', 'health'],
    queryFn: fetchGrafanaHealth,
    retry: false,
    staleTime: 30_000,
  });
}
