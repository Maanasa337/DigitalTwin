import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchBenchmark,
  fetchBenchmarkReport,
  fetchBenchmarks,
  fetchJob,
  fetchModel,
  fetchModelMetrics,
  fetchModels,
  fetchPredictions,
  fetchPredictionsLatest,
  runBenchmark,
  trainModel,
} from '../api/pdm';
import type { BenchmarkRunRequest } from '../api/types';

/** A benchmark run is finished by the worker, so views poll while one is still running. */
const BENCHMARK_POLL_MS = 5000;
const JOB_POLL_MS = 3000;

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

/** `GET /jobs/{id}` reports Celery states as queued / running / done / failed. */
export const JOB_FINISHED = ['done', 'failed'];

export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ['jobs', jobId],
    queryFn: () => fetchJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (JOB_FINISHED.includes(query.state.data?.status ?? '') ? false : JOB_POLL_MS),
  });
}

export function useTrainModel() {
  return useMutation({ mutationFn: trainModel });
}

export function useBenchmarks(params?: { page?: number; size?: number }) {
  return useQuery({
    queryKey: ['benchmarks', 'list', params],
    queryFn: () => fetchBenchmarks(params),
    refetchInterval: (query) =>
      query.state.data?.items.some((run) => run.status === 'running') ? BENCHMARK_POLL_MS : false,
  });
}

export function useBenchmark(id: string | undefined) {
  return useQuery({
    queryKey: ['benchmarks', 'run', id],
    queryFn: () => fetchBenchmark(id!),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? BENCHMARK_POLL_MS : false),
  });
}

export function useRunBenchmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BenchmarkRunRequest) => runBenchmark(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['benchmarks'] }),
  });
}

/** A report is written once, when the run finishes, so it never goes stale. */
export function useBenchmarkReport(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['benchmarks', 'report', id],
    queryFn: () => fetchBenchmarkReport(id!),
    enabled: Boolean(id) && enabled,
    staleTime: Infinity,
  });
}
