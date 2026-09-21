import { http } from '../lib/axios';
import type {
  AasEnvironment,
  Asset,
  AssetClone,
  AssetCreate,
  AssetListParams,
  AssetType,
  Component,
  FailureMode,
  Line,
  Page,
  PageParams,
  Sensor,
} from './types';

export type AssetDocumentKind = 'aas' | 'dtdl' | 'ngsi-ld';

export async function listLines(params: PageParams & { plant_id?: string } = {}): Promise<Page<Line>> {
  const { data } = await http.get<Page<Line>>('/lines', { params });
  return data;
}

export async function listAssets(params: AssetListParams = {}): Promise<Page<Asset>> {
  const { data } = await http.get<Page<Asset>>('/assets', { params });
  return data;
}

export async function createAsset(body: AssetCreate): Promise<Asset> {
  const { data } = await http.post<Asset>('/assets', body);
  return data;
}

export async function retireAsset(id: string): Promise<void> {
  await http.delete(`/assets/${id}`);
}

export async function cloneAsset(id: string, body: AssetClone): Promise<Asset> {
  const { data } = await http.post<Asset>(`/assets/${id}/clone`, body);
  return data;
}

export async function importAasx(file: File, lineId: string, assetType: AssetType): Promise<Asset> {
  const form = new FormData();
  form.append('file', file);
  form.append('line_id', lineId);
  form.append('asset_type', assetType);
  const { data } = await http.post<Asset>('/assets/import-aasx', form);
  return data;
}

export async function getComponents(assetId: string): Promise<Component[]> {
  const { data } = await http.get<Component[]>(`/assets/${assetId}/components`);
  return data;
}

export async function getSensors(assetId: string): Promise<Sensor[]> {
  const { data } = await http.get<Sensor[]>(`/assets/${assetId}/sensors`);
  return data;
}

export async function listFailureModes(assetType: AssetType): Promise<FailureMode[]> {
  const { data } = await http.get<FailureMode[]>('/failure-modes', { params: { asset_type: assetType } });
  return data;
}

export async function getAas(assetId: string): Promise<AasEnvironment> {
  const { data } = await http.get<AasEnvironment>(`/assets/${assetId}/aas`);
  return data;
}

export async function getAssetDocument(assetId: string, kind: Exclude<AssetDocumentKind, 'aas'>): Promise<unknown> {
  const { data } = await http.get<unknown>(`/assets/${assetId}/${kind}`);
  return data;
}

export async function downloadAasx(assetId: string): Promise<Blob> {
  const { data } = await http.get<Blob>(`/assets/${assetId}/aas.aasx`, { responseType: 'blob' });
  return data;
}
