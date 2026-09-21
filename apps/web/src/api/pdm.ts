import { http } from '../lib/axios';
import type { ModelMetric, Page, PdmModel, Prediction, PredictionLatest } from './types';

// ── Models ───────────────────────────────────────────────────────────

export async function fetchModels(params?: {
  page?: number;
  size?: number;
  task?: string;
  stage?: string;
}): Promise<Page<PdmModel>> {
  const { data } = await http.get<Page<PdmModel>>('/models', { params });
  return data;
}

export async function fetchModel(modelId: string): Promise<PdmModel> {
  const { data } = await http.get<PdmModel>(`/models/${modelId}`);
  return data;
}

export async function fetchModelMetrics(modelId: string): Promise<ModelMetric[]> {
  const { data } = await http.get<ModelMetric[]>(`/models/${modelId}/metrics`);
  return data;
}

export async function promoteModel(modelId: string): Promise<PdmModel> {
  const { data } = await http.post<PdmModel>(`/models/${modelId}/promote`);
  return data;
}

export async function trainModel(body: {
  task?: string;
  algorithm?: string;
  asset_type?: string;
  window_size?: number;
  stride?: number;
  horizon?: number;
}): Promise<{ job_id: string; status: string }> {
  const { data } = await http.post('/models/train', body);
  return data;
}

// ── Predictions ──────────────────────────────────────────────────────

export async function fetchPredictions(
  asset: string,
  from: string,
  to: string,
): Promise<Prediction[]> {
  const { data } = await http.get<Prediction[]>('/predictions', { params: { asset, from, to } });
  return data;
}

export async function fetchPredictionsLatest(asset: string): Promise<PredictionLatest> {
  const { data } = await http.get<PredictionLatest>('/predictions/latest', { params: { asset } });
  return data;
}
