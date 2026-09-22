/**
 * Grafana is reached through the same-origin `/grafana` proxy (vite in dev, nginx in the image), not
 * through `/api/v1`, so these calls use `fetch` rather than the shared axios instance.
 */
export const GRAFANA_BASE = (import.meta.env.VITE_GRAFANA_URL ?? '/grafana').replace(/\/$/, '');

export interface GrafanaHealth {
  database: string;
  version?: string;
}

export async function fetchGrafanaHealth(): Promise<GrafanaHealth> {
  const res = await fetch(`${GRAFANA_BASE}/api/health`, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`Grafana health ${res.status}`);
  // Without a proxy route the SPA fallback answers 200 with index.html, which fails to parse here.
  return (await res.json()) as GrafanaHealth;
}

export function grafanaDashboardUrl(
  uid: string,
  slug: string,
  mode: 'dark' | 'light',
  vars: Record<string, string> = {},
): string {
  const query = Object.entries(vars)
    .map(([key, value]) => `var-${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .concat(['kiosk', `theme=${mode}`])
    .join('&');
  return `${GRAFANA_BASE}/d/${uid}/${slug}?${query}`;
}
