import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Page, Report, ReportSchedule } from '../../api/types';
import { renderWithProviders } from '../../test/renderWithProviders';
import ReportsPage from './ReportsPage';

vi.mock('../../api/reports', () => ({
  fetchReports: vi.fn(),
  fetchReport: vi.fn(),
  createReport: vi.fn(),
  fetchReportFile: vi.fn(),
  fetchSchedules: vi.fn(),
  createSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
}));
vi.mock('../../hooks/useAssets', () => ({
  useAssets: () => ({ data: { items: [{ id: 'a1', code: 'cnc-01', name: 'CNC Mill 01' }] } }),
  useLines: () => ({ data: { items: [{ id: 'l1', code: 'line-1', name: 'Line 1', plant_id: 'p1' }] } }),
}));

const api = await import('../../api/reports');

function report(overrides: Partial<Report> = {}): Report {
  return {
    id: 'r1',
    type: 'weekly_maintenance',
    scope: 'line',
    scope_id: 'l1',
    period_start: '2026-09-14T00:00:00Z',
    period_end: '2026-09-21T00:00:00Z',
    format: 'pdf',
    status: 'done',
    file_uri: 'data/reports/2026/09/r1.pdf',
    summary_text: '7 work orders were raised and 5 were closed.',
    summary_audit: { passed: true, used_llm: false, word_count: 11, unsupported_numbers: [], reason: null },
    error: null,
    requested_by: null,
    requested_via: 'ui',
    schedule_id: null,
    created_at: '2026-09-21T06:00:00Z',
    finished_at: '2026-09-21T06:00:20Z',
    ...overrides,
  };
}

function page<T>(items: T[]): Page<T> {
  return { items, total: items.length, page: 1, size: 20 };
}



describe('ReportsPage', () => {
  beforeEach(() => {
    vi.mocked(api.fetchReports).mockReset().mockResolvedValue(page([report()]));
    vi.mocked(api.fetchSchedules).mockReset().mockResolvedValue(page<ReportSchedule>([]));
    vi.mocked(api.createReport).mockReset().mockResolvedValue(report({ status: 'queued' }));
    vi.mocked(api.fetchReportFile).mockReset().mockResolvedValue(new Blob(['%PDF-']));
  });

  it('lists the archive with a labelled status', async () => {
    renderWithProviders(<ReportsPage />);
    expect(await screen.findByText('Weekly maintenance')).toBeInTheDocument();
    // Status is a word, not a colour (§9.1).
    expect(screen.getByText('Ready')).toBeInTheDocument();
  });

  it('shows a failed report without pretending it succeeded', async () => {
    vi.mocked(api.fetchReports).mockResolvedValue(
      page([report({ status: 'failed', error: 'That machine is not in the registry', file_uri: null })]),
    );
    renderWithProviders(<ReportsPage />);
    expect(await screen.findByText('Failed')).toBeInTheDocument();
  });

  it('submits the generate form with a resolved scope and period', async () => {
    renderWithProviders(<ReportsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /generate report/i }));

    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Generate report' }));

    await waitFor(() => expect(api.createReport).toHaveBeenCalled());
    const body = vi.mocked(api.createReport).mock.calls[0][0];
    expect(body).toMatchObject({ type: 'weekly_maintenance', format: 'pdf' });
    // ScopePicker defaults to the only plant rather than sending an unscoped request.
    expect(body.scope).toBe('plant');
    expect(body.scope_id).toBeTruthy();
    expect(body.period_start).toBeTruthy();
    expect(body.period_end).toBeTruthy();
  });

  it('opens the preview drawer with the audited summary', async () => {
    renderWithProviders(<ReportsPage />);
    await userEvent.click(await screen.findByText('Weekly maintenance'));

    expect(await screen.findByText('Executive summary')).toBeInTheDocument();
    expect(screen.getByText('7 work orders were raised and 5 were closed.')).toBeInTheDocument();
    expect(screen.getByText(/Generated from the figures/)).toBeInTheDocument();
  });

  it('flags a summary that failed its numeric check', async () => {
    vi.mocked(api.fetchReports).mockResolvedValue(
      page([
        report({
          summary_text: 'A replaced summary.',
          summary_audit: {
            passed: false,
            used_llm: true,
            word_count: 3,
            unsupported_numbers: [99.9],
            reason: 'numbers not present in the report data',
          },
        }),
      ]),
    );
    renderWithProviders(<ReportsPage />);
    await userEvent.click(await screen.findByText('Weekly maintenance'));

    expect(await screen.findByText(/failed the check/)).toBeInTheDocument();
  });

  it('hides schedule editing from a technician', async () => {
    renderWithProviders(<ReportsPage />, { roles: ['technician'] });
    await screen.findByText('Schedules');
    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
  });

  it('opens the schedule form for an engineer', async () => {
    renderWithProviders(<ReportsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Add' }));
    expect(await screen.findByPlaceholderText('0 6 * * 1')).toBeInTheDocument();
  });

  it('lists an existing schedule with its cron and last run', async () => {
    vi.mocked(api.fetchSchedules).mockResolvedValue(
      page<ReportSchedule>([
        {
          id: 's1', type: 'energy', scope: null, scope_id: null, format: 'pdf',
          cron: '0 6 * * 1', recipients: ['plant@example.test'], enabled: true,
          last_run_at: '2026-09-21T06:00:00Z', created_at: '', updated_at: '',
        },
      ]),
    );
    renderWithProviders(<ReportsPage />);
    expect(await screen.findByText('0 6 * * 1')).toBeInTheDocument();
    expect(screen.getByText('plant@example.test')).toBeInTheDocument();
  });
});
