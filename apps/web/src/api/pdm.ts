import { http } from '../lib/axios';
import type {
  BenchmarkRun,
  BenchmarkRunRequest,
  ModelMetric,
  Page,
  PdmModel,
  Prediction,
  PredictionLatest,
  TrainJob,
} from './types';

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
  /** `synthetic:{asset_type}`, `cmapss:FD00x` or `ai4i`; defaults to the asset type's simulator data. */
  dataset_ref?: string;
  window_size?: number;
  stride?: number;
  horizon?: number;
}): Promise<{ job_id: string; status: string }> {
  const { data } = await http.post('/models/train', body);
  return data;
}

/** The exported ONNX graph, fetched as a blob because the endpoint needs the bearer token. */
export async function fetchModelOnnx(modelId: string): Promise<Blob> {
  const { data } = await http.get<Blob>(`/models/${modelId}/onnx`, { responseType: 'blob' });
  return data;
}

export async function fetchJob(jobId: string): Promise<TrainJob> {
  const { data } = await http.get<TrainJob>(`/jobs/${jobId}`);
  return data;
}

// ── Benchmarks ───────────────────────────────────────────────────────

export async function fetchBenchmarks(params?: { page?: number; size?: number }): Promise<Page<BenchmarkRun>> {
  const { data } = await http.get<Page<BenchmarkRun>>('/benchmarks', { params });
  return data;
}

export async function fetchBenchmark(id: string): Promise<BenchmarkRun> {
  const { data } = await http.get<BenchmarkRun>(`/benchmarks/${id}`);
  return data;
}

export async function runBenchmark(body: BenchmarkRunRequest): Promise<BenchmarkRun> {
  const { data } = await http.post<BenchmarkRun>('/benchmarks/run', body);
  return data;
}

export async function fetchBenchmarkReport(id: string): Promise<string> {
  const { data } = await http.get<string>(`/benchmarks/${id}/report.md`, { responseType: 'text' });
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
