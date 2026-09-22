import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { BenchmarkRun, Page } from '../../api/types';
import { renderWithProviders } from '../../test/renderWithProviders';
import BenchmarksPage from './BenchmarksPage';
import { verdict } from './benchmarkMeta';

vi.mock('../../api/pdm', () => ({
  fetchBenchmarks: vi.fn(),
  fetchBenchmark: vi.fn(),
  runBenchmark: vi.fn(),
  fetchBenchmarkReport: vi.fn(),
}));

const api = await import('../../api/pdm');

function run(overrides: Partial<BenchmarkRun> = {}): BenchmarkRun {
  return {
    id: 'b1',
    started_at: '2026-09-21T06:00:00Z',
    finished_at: '2026-09-21T06:04:10Z',
    git_sha: 'abcdef1234567',
    seed: 42,
    datasets: ['FD001', 'AI4I'],
    results: { FD001: { rmse: 14.2, coverage_90: 0.91 }, AI4I: { auc: 0.97 } },
    report_uri: 'benchmarks/results/2026-09-21.md',
    status: 'done',
    error: null,
    targets: {
      FD001: { rmse: { op: 'le', value: 13 }, coverage_90: { op: 'ge', value: 0.88 } },
      AI4I: { auc: { op: 'ge', value: 0.95 } },
    },
    ...overrides,
  };
}

const SLOW = { timeout: 5000 };

const page = (items: BenchmarkRun[]): Page<BenchmarkRun> => ({ items, total: items.length, page: 1, size: 20 });

describe('verdict', () => {
  it('honours the direction of the target', () => {
    expect(verdict(12, { op: 'le', value: 13 })).toBe('pass');
    expect(verdict(14, { op: 'le', value: 13 })).toBe('fail');
    expect(verdict(0.9, { op: 'ge', value: 0.88 })).toBe('pass');
    expect(verdict(0.8, { op: 'ge', value: 0.88 })).toBe('fail');
    expect(verdict(1, undefined)).toBe('none');
  });
});

describe('BenchmarksPage', () => {
  beforeEach(() => {
    vi.mocked(api.fetchBenchmarks).mockReset().mockResolvedValue(page([run()]));
    vi.mocked(api.fetchBenchmark).mockReset().mockResolvedValue(run());
    vi.mocked(api.runBenchmark).mockReset().mockResolvedValue(run({ id: 'b2', status: 'running', results: null }));
    vi.mocked(api.fetchBenchmarkReport).mockReset().mockResolvedValue('# Benchmark\n\n| Metric | Value |\n|---|---|\n| rmse | 14.2 |');
  });

  it('lists runs and scores each metric against its target with icon and label', async () => {
    renderWithProviders(<BenchmarksPage />);
    expect(await screen.findByText('abcdef1', undefined, SLOW)).toBeInTheDocument();

    const rmse = (await screen.findByText('rmse', undefined, SLOW)).closest('tr') as HTMLElement;
    expect(within(rmse).getByText('Fail')).toBeInTheDocument();
    expect(within(rmse).getByText('≤ 13.000')).toBeInTheDocument();
    const auc = screen.getByText('auc').closest('tr') as HTMLElement;
    expect(within(auc).getByText('Pass').closest('.ant-tag')?.querySelector('.anticon')).not.toBeNull();
  });

  it('shows the empty state with a run action when there are no runs', async () => {
    vi.mocked(api.fetchBenchmarks).mockResolvedValue(page([]));
    renderWithProviders(<BenchmarksPage />);
    expect(await screen.findByText('No benchmark runs yet.', undefined, SLOW)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Run benchmark/ })).toHaveLength(2);
  });

  it('shows an error with retry when the list fails', async () => {
    vi.mocked(api.fetchBenchmarks).mockRejectedValue(new Error('boom'));
    renderWithProviders(<BenchmarksPage />);
    expect(await screen.findByText('Could not load data', undefined, SLOW)).toBeInTheDocument();
    vi.mocked(api.fetchBenchmarks).mockResolvedValue(page([run()]));
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('abcdef1', undefined, SLOW)).toBeInTheDocument();
  });

  it('starts a run with the chosen datasets', async () => {
    renderWithProviders(<BenchmarksPage />);
    await screen.findByText('abcdef1', undefined, SLOW);
    await userEvent.click(screen.getByRole('button', { name: /Run benchmark/ }));
    const dialog = await screen.findByRole('dialog', undefined, SLOW);
    await userEvent.click(within(dialog).getByRole('button', { name: /Run benchmark/ }));
    await waitFor(
      () => expect(api.runBenchmark).toHaveBeenCalledWith({ datasets: ['FD001'], seed: 42, quick: true }),
      SLOW,
    );
  });

  it('renders the Markdown report in the drawer without injecting HTML', async () => {
    renderWithProviders(<BenchmarksPage />);
    await screen.findByText('rmse', undefined, SLOW);
    await userEvent.click(screen.getByRole('button', { name: /Report/ }));
    expect(await screen.findByRole('heading', { name: 'Benchmark' }, SLOW)).toBeInTheDocument();
    expect(api.fetchBenchmarkReport).toHaveBeenCalledWith('b1');
  });
});
