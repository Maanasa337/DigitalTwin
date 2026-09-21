import { screen } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as simApi from '../../api/simulation';
import type { SimStatus } from '../../api/types';
import { renderWithProviders } from '../../test/renderWithProviders';
import SimulationPage from './SimulationPage';

vi.mock('../../api/simulation');
vi.mock('../../api/assets');

const status: SimStatus = {
  sim_time: '2026-09-17T10:00:00Z',
  sim_elapsed_s: 3725,
  time_scale: 60,
  running: true,
  seed: 42,
  scenario: { code: 'demo_day', started_at: '2026-09-17T09:00:00Z' },
  assets: [
    {
      code: 'cnc-01',
      asset_type: 'cnc_mill',
      line_code: 'line-a',
      state: 'running',
      load_pct: 80,
      speed_pct: 100,
      damage: { spindle_bearing: 0.72 },
      active_modes: [{ failure_mode: 'bearing_wear', mode: 'gradual', severity: 0.5, started_at: '2026-09-17T09:30:00Z' }],
      sensor_faults: [],
      true_rul_h: 12.34,
      driver: 'wiener',
      failure_mode: 'bearing_wear',
    },
  ],
  log: [{ t: '2026-09-17T09:59:00Z', level: 'warning', message: 'Bearing wear accelerating', asset_code: 'cnc-01' }],
};

describe('SimulationPage', () => {
  beforeEach(() => {
    vi.mocked(simApi.getScenarios).mockResolvedValue([{ code: 'demo_day', name: 'Demo day', description: null }]);
  });

  it('renders the fleet damage table and live log', async () => {
    vi.mocked(simApi.getSimStatus).mockResolvedValue(status);
    renderWithProviders(<SimulationPage />);
    expect(await screen.findByText('Fleet damage')).toBeInTheDocument();
    expect(screen.getAllByText('cnc-01').length).toBeGreaterThan(0);
    expect(screen.getByText('Running', { selector: '.ant-tag[data-level="good"] span' })).toBeInTheDocument();
    expect(screen.getByText('72%')).toBeInTheDocument();
    expect(screen.getByText('12.3 h')).toBeInTheDocument();
    expect(screen.getByText('Bearing wear accelerating')).toBeInTheDocument();
    expect(screen.getByText('01:02:05')).toBeInTheDocument();
  });

  it('shows a retryable result when the simulator is unreachable', async () => {
    const config = { headers: new AxiosHeaders() };
    vi.mocked(simApi.getSimStatus).mockRejectedValue(
      new AxiosError('Service Unavailable', 'ERR_BAD_RESPONSE', config, null, {
        status: 503,
        statusText: '',
        headers: {},
        config,
        data: { title: 'Service Unavailable', status: 503, detail: 'Simulator did not respond' },
      }),
    );
    renderWithProviders(<SimulationPage />);
    expect(await screen.findByText('Simulator unreachable')).toBeInTheDocument();
    expect(screen.getByText('Simulator did not respond')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });
});
