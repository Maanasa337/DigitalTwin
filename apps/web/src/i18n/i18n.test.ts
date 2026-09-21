import { describe, expect, it } from 'vitest';

import en from './en.json';
import hi from './hi.json';

function keys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix];
  return Object.entries(value).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
}

describe('translations', () => {
  it('has the same keys in en and hi', () => {
    expect(keys(hi).sort()).toEqual(keys(en).sort());
  });
});
