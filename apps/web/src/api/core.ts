import { http } from '../lib/axios';
import type { Me } from './types';

export async function getMe(): Promise<Me> {
  const { data } = await http.get<Me>('/me');
  return data;
}
