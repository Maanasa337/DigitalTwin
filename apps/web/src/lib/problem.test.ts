import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { describe, expect, it } from 'vitest';

import { problemMessage, problemStatus } from './problem';

function axiosError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  const response: AxiosResponse = { status, statusText: '', headers: {}, config, data };
  return new AxiosError(`Request failed with status code ${status}`, 'ERR_BAD_RESPONSE', config, null, response);
}

describe('problemMessage', () => {
  it('prefers detail over title', () => {
    const err = axiosError(409, { type: 'about:blank', title: 'Conflict', status: 409, detail: 'Asset code cnc-01 exists' });
    expect(problemMessage(err)).toBe('Asset code cnc-01 exists');
    expect(problemStatus(err)).toBe(409);
  });

  it('falls back to title when detail is missing or null', () => {
    expect(problemMessage(axiosError(423, { title: 'Locked', status: 423 }))).toBe('Locked');
    expect(problemMessage(axiosError(403, { title: 'Forbidden', status: 403, detail: null }))).toBe('Forbidden');
  });

  it('appends field errors from validation problems', () => {
    const err = axiosError(422, {
      title: 'Validation failed',
      status: 422,
      errors: [{ loc: ['body', 'code'], msg: 'invalid pattern', type: 'value_error' }],
    });
    expect(problemMessage(err)).toBe('Validation failed (body.code: invalid pattern)');
  });

  it('uses the axios message for non-problem bodies', () => {
    expect(problemMessage(axiosError(502, '<html>Bad gateway</html>'))).toBe('Request failed with status code 502');
  });

  it('handles plain errors and unknown values', () => {
    expect(problemMessage(new Error('boom'))).toBe('boom');
    expect(problemMessage('nope', 'Fallback')).toBe('Fallback');
    expect(problemStatus(new Error('boom'))).toBeUndefined();
  });
});
