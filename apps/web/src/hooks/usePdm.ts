import { useQuery } from '@tanstack/react-query';

import { fetchModel, fetchModelMetrics, fetchModels, fetchPredictions, fetchPredictionsLatest } from '../api/pdm';

export function useModels(params?: { page?: number; size?: number; task?: string; stage?: string }) {
  return useQuery({
    queryKey: ['models', params],
    queryFn: () => fetchModels(params),
  });
}

export function useModel(modelId: string) {
  return useQuery({
    queryKey: ['model', modelId],
    queryFn: () => fetchModel(modelId),
    enabled: Boolean(modelId),
  });
}

export function useModelMetrics(modelId: string) {
  return useQuery({
    queryKey: ['model-metrics', modelId],
    queryFn: () => fetchModelMetrics(modelId),
    enabled: Boolean(modelId),
  });
}

export function usePredictions(asset: string, from: string, to: string) {
  return useQuery({
    queryKey: ['predictions', asset, from, to],
    queryFn: () => fetchPredictions(asset, from, to),
    enabled: Boolean(asset && from && to),
    refetchInterval: 30_000,
  });
}

export function usePredictionsLatest(asset: string) {
  return useQuery({
    queryKey: ['predictions-latest', asset],
    queryFn: () => fetchPredictionsLatest(asset),
    enabled: Boolean(asset),
    refetchInterval: 15_000,
  });
}
