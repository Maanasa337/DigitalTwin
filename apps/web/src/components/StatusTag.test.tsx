import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ASSET_STATUSES, type AssetStatus } from '../api/types';
import { StatusTag } from './StatusTag';

function tagFor(label: string | RegExp) {
  const tag = screen.getByText(label).closest('.ant-tag');
  expect(tag).not.toBeNull();
  return tag as HTMLElement;
}

describe('StatusTag', () => {
  const expected: Record<AssetStatus, [string, string]> = {
    RUNNING: ['Running', 'good'],
    IDLE: ['Idle', 'warning'],
    MAINTENANCE: ['Maintenance', 'serious'],
    DOWN: ['Down', 'critical'],
    UNKNOWN: ['Unknown', 'neutral'],
  };

  it.each(ASSET_STATUSES)('renders icon and label for asset status %s', (status) => {
    render(<StatusTag status={status} />);
    const [label, level] = expected[status];
    const tag = tagFor(label);
    expect(tag).toHaveAttribute('data-level', level);
    expect(tag.querySelector('.anticon')).not.toBeNull();
  });

  it.each([
    [95, 'good', '95 · Good'],
    [80, 'good', '80 · Good'],
    [79, 'warning', '79 · Warning'],
    [60, 'warning', '60 · Warning'],
    [59, 'serious', '59 · Serious'],
    [40, 'serious', '40 · Serious'],
    [39, 'critical', '39 · Critical'],
    [0, 'critical', '0 · Critical'],
  ])('maps health %d to %s with icon and label', (health, level, label) => {
    render(<StatusTag health={health} />);
    const tag = tagFor(label);
    expect(tag).toHaveAttribute('data-level', level);
    expect(tag.querySelector('.anticon')).not.toBeNull();
  });

  it('renders "No data" with the neutral icon when health is null', () => {
    render(<StatusTag health={null} />);
    const tag = tagFor('No data');
    expect(tag).toHaveAttribute('data-level', 'neutral');
    expect(tag.querySelector('.anticon-minus-circle')).not.toBeNull();
  });
});
