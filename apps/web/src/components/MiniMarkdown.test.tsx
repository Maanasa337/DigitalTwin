import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MiniMarkdown } from './MiniMarkdown';

describe('MiniMarkdown', () => {
  it('renders headings, tables and lists as elements', () => {
    render(
      <MiniMarkdown
        source={'# Benchmark\n\nRun with **seed 42**.\n\n| Metric | Value |\n|---|---|\n| rmse | 12.1 |\n\n- one\n- two'}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Benchmark' })).toBeInTheDocument();
    expect(screen.getByText('seed 42').tagName).toBe('STRONG');
    expect(screen.getByRole('columnheader', { name: 'Metric' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '12.1' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('never interprets HTML', () => {
    const { container } = render(<MiniMarkdown source={'<img src=x onerror="alert(1)"> hi'} />);
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(/<img src=x/)).toBeInTheDocument();
  });
});
