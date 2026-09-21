import axios from 'axios';

import type { Problem } from '../api/types';

function isProblem(data: unknown): data is Problem {
  return typeof data === 'object' && data !== null && typeof (data as Problem).title === 'string';
}

export function problemStatus(err: unknown): number | undefined {
  return axios.isAxiosError(err) ? err.response?.status : undefined;
}

export function problemMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (axios.isAxiosError(err)) {
    const data: unknown = err.response?.data;
    if (isProblem(data)) {
      const base = data.detail || data.title;
      const fields = data.errors?.map((e) => `${e.loc.join('.')}: ${e.msg}`) ?? [];
      return fields.length ? `${base} (${fields.join('; ')})` : base;
    }
    return err.message || fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
