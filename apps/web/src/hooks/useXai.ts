import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchCounterfactuals,
  fetchExplanation,
  fetchExplanationForPrediction,
  fetchGlobalImportance,
  fetchNarration,
  fetchNarrationAudits,
  fetchQualityMetrics,
  submitFeedback,
} from '../api/xai';
import type { FeedbackVerdict, NarrationKind } from '../api/types';

export function useExplanation(explanationId: string | undefined) {
  return useQuery({
    queryKey: ['explanation', explanationId],
    queryFn: () => fetchExplanation(explanationId!),
    enabled: Boolean(explanationId),
  });
}

export function useExplanationForPrediction(predictionId: string | undefined) {
  return useQuery({
    queryKey: ['explanation-for-prediction', predictionId],
    queryFn: () => fetchExplanationForPrediction(predictionId!),
    enabled: Boolean(predictionId),
    // The explain worker runs after the prediction is written, so a fresh prediction has no
    // explanation yet. A missing one is expected, not an error worth retrying hard.
    retry: false,
  });
}

export function useCounterfactuals(explanationId: string | undefined) {
  return useQuery({
    queryKey: ['counterfactuals', explanationId],
    queryFn: () => fetchCounterfactuals(explanationId!),
    enabled: Boolean(explanationId),
  });
}

export function useNarration(
  explanationId: string | undefined,
  kind: NarrationKind = 'why',
  lang = 'en',
) {
  return useQuery({
    queryKey: ['narration', explanationId, kind, lang],
    queryFn: () => fetchNarration(explanationId!, kind, lang),
    enabled: Boolean(explanationId),
    // Narrations are stored on first request, so the answer never changes for a given explanation.
    staleTime: Infinity,
  });
}

export function useSubmitFeedback(explanationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { verdict: FeedbackVerdict; reason?: string; suspect_sensor_id?: string }) =>
      submitFeedback(explanationId, { channel: 'ui', ...body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['explanation', explanationId] });
    },
  });
}

export function useGlobalImportance(modelId: string | undefined) {
  return useQuery({
    queryKey: ['global-importance', modelId],
    queryFn: () => fetchGlobalImportance(modelId!),
    enabled: Boolean(modelId),
  });
}

export function useXaiQualityMetrics(modelId: string | undefined) {
  return useQuery({
    queryKey: ['xai-quality', modelId],
    queryFn: () => fetchQualityMetrics(modelId!),
    enabled: Boolean(modelId),
  });
}

export function useNarrationAudits(params?: { model?: string; passed?: boolean; limit?: number }) {
  return useQuery({
    queryKey: ['narration-audits', params],
    queryFn: () => fetchNarrationAudits(params),
  });
}
