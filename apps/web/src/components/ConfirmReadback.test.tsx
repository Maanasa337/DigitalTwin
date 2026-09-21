import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ConfirmReadback } from './ConfirmReadback';

const TEXT = 'Set load on cnc-01 to 80 %. This writes to the machine.';

function setup(props: Partial<Parameters<typeof ConfirmReadback>[0]> = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(<ConfirmReadback open text={TEXT} onConfirm={onConfirm} onCancel={onCancel} {...props} />);
  return { onConfirm, onCancel };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('ConfirmReadback', () => {
  it('shows the read-back text', () => {
    setup();
    expect(screen.getByText(TEXT)).toBeInTheDocument();
  });

  it('confirms on Enter', () => {
    const { onConfirm, onCancel } = setup();
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(onConfirm).toHaveBeenCalledWith(undefined);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('cancels on Escape', () => {
    const { onConfirm, onCancel } = setup();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('auto-cancels when the 10 s countdown reaches zero', () => {
    vi.useFakeTimers();
    const { onCancel } = setup();
    act(() => vi.advanceTimersByTime(9_000));
    expect(onCancel).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1_000));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('keeps Confirm disabled until a PIN is entered when required', () => {
    const { onConfirm } = setup({ requirePin: true });
    const confirm = screen.getByRole('button', { name: 'Confirm' });
    expect(confirm).toBeDisabled();

    fireEvent.keyDown(window, { key: 'Enter' });
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('PIN', { selector: 'input' }), { target: { value: '12a34' } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledWith('1234');
  });
});
