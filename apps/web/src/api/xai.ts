import { http } from '../lib/axios';
import type {
  Counterfactual,
  Explanation,
  ExplanationFeedback,
  FeedbackVerdict,
  GlobalImportance,
  Narration,
  NarrationAuditRow,
  NarrationKind,
  XaiQualityMetrics,
} from './types';

export async function fetchExplanation(explanationId: string): Promise<Explanation> {
  const { data } = await http.get<Explanation>(`/explanations/${explanationId}`);
  return data;
}

export async function fetchExplanationForPrediction(predictionId: string): Promise<Explanation> {
  const { data } = await http.get<Explanation>(`/predictions/${predictionId}/explanation`);
  return data;
}

export async function fetchCounterfactuals(explanationId: string): Promise<Counterfactual[]> {
  const { data } = await http.get<Counterfactual[]>(`/explanations/${explanationId}/counterfactual`);
  return data;
}

export async function fetchNarration(
  explanationId: string,
  kind: NarrationKind = 'why',
  lang = 'en',
): Promise<Narration> {
  const { data } = await http.get<Narration>(`/explanations/${explanationId}/narration`, {
    params: { kind, lang },
  });
  return data;
}

export async function submitFeedback(
  explanationId: string,
  body: { verdict: FeedbackVerdict; reason?: string; suspect_sensor_id?: string; channel?: string },
): Promise<ExplanationFeedback> {
  const { data } = await http.post<ExplanationFeedback>(
    `/explanations/${explanationId}/feedback`,
    body,
  );
  return data;
}

export async function fetchGlobalImportance(modelId: string): Promise<GlobalImportance> {
  const { data } = await http.get<GlobalImportance>(`/models/${modelId}/global-importance`);
  return data;
}

export async function fetchQualityMetrics(modelId: string): Promise<XaiQualityMetrics> {
  const { data } = await http.get<XaiQualityMetrics>(`/models/${modelId}/quality-metrics`);
  return data;
}

/** Queues a recompute of importance and explanation quality in the worker. */
export async function refreshQualityMetrics(modelId: string): Promise<void> {
  await http.post(`/models/${modelId}/quality-metrics/refresh`);
}

export async function fetchNarrationAudits(params?: {
  model?: string;
  passed?: boolean;
  limit?: number;
}): Promise<NarrationAuditRow[]> {
  const { data } = await http.get<NarrationAuditRow[]>('/narration-audits', { params });
  return data;
}
