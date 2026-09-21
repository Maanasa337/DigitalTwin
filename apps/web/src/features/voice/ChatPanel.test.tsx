import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TurnResponse, VoiceAction } from '../../api/types';
import { renderWithProviders } from '../../test/renderWithProviders';
import { useVoiceStore } from '../../store/voiceStore';
import { ChatPanel } from './ChatPanel';

vi.mock('../../api/voice', () => ({
  sendUtterance: vi.fn(),
  confirmAction: vi.fn(),
  cancelAction: vi.fn(),
  fetchSessions: vi.fn(),
  fetchSession: vi.fn(),
  endSession: vi.fn(),
  fetchIntents: vi.fn(),
  fetchSuiteAccuracy: vi.fn(),
  seedSuite: vi.fn(),
}));

const api = await import('../../api/voice');

function turn(overrides: Partial<TurnResponse> = {}): TurnResponse {
  return {
    session_id: 's1',
    turn_id: 't1',
    intent: 'get_machine_status',
    tier: 'T0',
    router: 'rules',
    confidence: 0.95,
    lang: 'en',
    slots: {},
    text: 'CNC Mill 01 is at 62 percent health.',
    citations: { asset: 'cnc-01' },
    hypothetical: false,
    action: null,
    suggestions: [],
    navigate: null,
    total_ms: 40,
    ...overrides,
  };
}

function pendingAction(overrides: Partial<VoiceAction> = {}): VoiceAction {
  return {
    id: 'a1',
    turn_id: 't1',
    tool: 'create_work_order',
    params: {},
    tier: 'T2',
    readback: 'Creating work order: bearing replacement on CNC Mill 01. Say confirm or cancel.',
    status: 'pending',
    validation_errors: null,
    expires_at: null,
    confirmed_at: null,
    second_factor_ok: null,
    executed_at: null,
    result: null,
    error: null,
    created_at: '2026-09-20T10:00:00Z',
    ...overrides,
  };
}

describe('ChatPanel', () => {
  beforeEach(() => {
    useVoiceStore.getState().reset();
    vi.mocked(api.sendUtterance).mockReset();
    vi.mocked(api.confirmAction).mockReset();
    vi.mocked(api.cancelAction).mockReset();
  });

  afterEach(() => {
    useVoiceStore.getState().reset();
  });

  it('shows the question and the grounded answer with its citation', async () => {
    vi.mocked(api.sendUtterance).mockResolvedValue(turn());
    renderWithProviders(<ChatPanel />);

    await userEvent.type(screen.getByLabelText('Ask about a machine...'), 'how is cnc one');
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    expect(await screen.findByText('how is cnc one')).toBeInTheDocument();
    expect(await screen.findByText('CNC Mill 01 is at 62 percent health.')).toBeInTheDocument();
    expect(screen.getByText(/asset cnc-01/)).toBeInTheDocument();
  });

  it('carries the session id into the next turn so context survives', async () => {
    vi.mocked(api.sendUtterance).mockResolvedValue(turn());
    renderWithProviders(<ChatPanel />);
    const input = screen.getByLabelText('Ask about a machine...');

    await userEvent.type(input, 'how is cnc one{Enter}');
    await screen.findByText('CNC Mill 01 is at 62 percent health.');
    await userEvent.type(input, 'why{Enter}');

    await waitFor(() => expect(api.sendUtterance).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.sendUtterance).mock.calls[0][0].session_id).toBeUndefined();
    expect(vi.mocked(api.sendUtterance).mock.calls[1][0].session_id).toBe('s1');
  });

  it('marks a T1 answer as hypothetical', async () => {
    vi.mocked(api.sendUtterance).mockResolvedValue(
      turn({ intent: 'run_what_if', tier: 'T1', hypothetical: true, text: 'Life goes to 152 cycles.' }),
    );
    renderWithProviders(<ChatPanel />);

    await userEvent.type(screen.getByLabelText('Ask about a machine...'), 'what if we reduce load to 80 percent{Enter}');

    expect(await screen.findByText('Hypothetical')).toBeInTheDocument();
    expect(screen.getByText(/T1/)).toBeInTheDocument();
  });

  it('reads a T2 action back and only acts once it is confirmed', async () => {
    const action = pendingAction();
    vi.mocked(api.sendUtterance).mockResolvedValue(
      turn({ intent: 'create_work_order', tier: 'T2', text: action.readback!, action }),
    );
    vi.mocked(api.confirmAction).mockResolvedValue({ ...action, status: 'executed' });
    renderWithProviders(<ChatPanel />);

    await userEvent.type(screen.getByLabelText('Ask about a machine...'), 'schedule bearing replacement for cnc one{Enter}');

    // The read-back is a modal, and nothing has been sent to the API yet.
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Creating work order/)).toBeInTheDocument();
    expect(api.confirmAction).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(api.confirmAction).toHaveBeenCalledWith('a1', undefined));
    expect(await screen.findByText('Done.')).toBeInTheDocument();
  });

  it('cancels a read-back without calling confirm', async () => {
    const action = pendingAction();
    vi.mocked(api.sendUtterance).mockResolvedValue(
      turn({ intent: 'create_work_order', tier: 'T2', text: action.readback!, action }),
    );
    vi.mocked(api.cancelAction).mockResolvedValue({ ...action, status: 'cancelled' });
    renderWithProviders(<ChatPanel />);

    await userEvent.type(screen.getByLabelText('Ask about a machine...'), 'schedule bearing replacement for cnc one{Enter}');
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(api.cancelAction).toHaveBeenCalledWith('a1'));
    expect(api.confirmAction).not.toHaveBeenCalled();
    expect(await screen.findByText('Cancelled.')).toBeInTheDocument();
  });

  it('asks for a PIN before a T3 action', async () => {
    const action = pendingAction({ tier: 'T3', tool: 'set_simulation_scenario', readback: 'Injecting a bearing fault. Say confirm or cancel.' });
    vi.mocked(api.sendUtterance).mockResolvedValue(
      turn({ intent: 'set_simulation_scenario', tier: 'T3', text: action.readback!, action }),
    );
    vi.mocked(api.confirmAction).mockResolvedValue({ ...action, status: 'executed' });
    renderWithProviders(<ChatPanel />);

    await userEvent.type(screen.getByLabelText('Ask about a machine...'), 'inject a bearing fault on cnc one{Enter}');
    const dialog = await screen.findByRole('dialog');

    const pin = within(dialog).getByLabelText('PIN');
    expect(pin).toBeInTheDocument();
    // The confirm button stays inert until a PIN is typed, so a tap alone cannot actuate.
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();

    await userEvent.type(pin, '246810');
    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(api.confirmAction).toHaveBeenCalledWith('a1', '246810'));
  });

  it('offers the alternatives when the assistant could not resolve a machine', async () => {
    vi.mocked(api.sendUtterance)
      .mockResolvedValueOnce(
        turn({
          text: 'I didn’t catch that. Did you mean CNC Mill 01 or CNC Mill 03?',
          suggestions: [
            { label: 'CNC Mill 01', value: 'a' },
            { label: 'CNC Mill 03', value: 'b' },
          ],
        }),
      )
      .mockResolvedValueOnce(turn());
    renderWithProviders(<ChatPanel />);

    await userEvent.type(screen.getByLabelText('Ask about a machine...'), 'how is cnc{Enter}');
    await userEvent.click(await screen.findByRole('button', { name: 'CNC Mill 01' }));

    await waitFor(() => expect(api.sendUtterance).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.sendUtterance).mock.calls[1][0].text).toBe('CNC Mill 01');
  });
});
