import { http } from '../lib/axios';
import type { Twin, TwinCommandRequest, TwinCommandResult, TwinTree } from './types';

export async function getTwinTree(): Promise<TwinTree> {
  const { data } = await http.get<TwinTree>('/twin/tree');
  return data;
}

export async function getTwin(code: string): Promise<Twin> {
  const { data } = await http.get<Twin>(`/twin/${encodeURIComponent(code)}`);
  return data;
}

export async function sendTwinCommand(code: string, body: TwinCommandRequest): Promise<TwinCommandResult> {
  const { data } = await http.post<TwinCommandResult>(`/twin/${encodeURIComponent(code)}/commands`, body);
  return data;
}
