import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  cloneAsset,
  createAsset,
  getAas,
  getAssetDocument,
  getComponents,
  getSensors,
  importAasx,
  listAssets,
  listFailureModes,
  listLines,
  listPlants,
  retireAsset,
} from '../api/assets';
import type { AssetClone, AssetCreate, AssetType } from '../api/types';

const PLANTS_PARAMS = { size: 100 };
const LINES_PARAMS = { size: 100 };

export function usePlants() {
  return useQuery({ queryKey: ['assets', 'plants', PLANTS_PARAMS], queryFn: () => listPlants(PLANTS_PARAMS) });
}

export function useLines() {
  return useQuery({ queryKey: ['assets', 'lines', LINES_PARAMS], queryFn: () => listLines(LINES_PARAMS) });
}

export function useAssets(params: Parameters<typeof listAssets>[0] = {}) {
  return useQuery({ queryKey: ['assets', 'list', params], queryFn: () => listAssets(params) });
}

export function useAssetIdByCode(code: string | undefined) {
  return useQuery({
    queryKey: ['assets', 'list', { q: code }],
    queryFn: () => listAssets({ q: code, size: 20 }),
    enabled: Boolean(code),
    select: (page) => page.items.find((asset) => asset.code === code)?.id ?? null,
  });
}

export function useComponents(assetId: string) {
  return useQuery({ queryKey: ['assets', 'components', assetId], queryFn: () => getComponents(assetId) });
}

export function useSensors(assetId: string | null | undefined) {
  return useQuery({
    queryKey: ['assets', 'sensors', assetId],
    queryFn: () => getSensors(assetId as string),
    enabled: Boolean(assetId),
  });
}

export function useFailureModes(assetType: AssetType | undefined) {
  return useQuery({
    queryKey: ['assets', 'failure-modes', assetType],
    queryFn: () => listFailureModes(assetType as AssetType),
    enabled: Boolean(assetType),
    staleTime: 5 * 60_000,
  });
}

export function useAas(assetId: string) {
  return useQuery({ queryKey: ['assets', 'aas', assetId], queryFn: () => getAas(assetId) });
}

export function useAssetDocument(assetId: string, kind: 'dtdl' | 'ngsi-ld') {
  return useQuery({ queryKey: ['assets', kind, assetId], queryFn: () => getAssetDocument(assetId, kind) });
}

function useInvalidateAssets() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['twin'] }),
      queryClient.invalidateQueries({ queryKey: ['assets'] }),
    ]);
}

export function useCreateAsset() {
  const invalidate = useInvalidateAssets();
  return useMutation({ mutationFn: (body: AssetCreate) => createAsset(body), onSuccess: invalidate });
}

export function useCloneAsset(assetId: string) {
  const invalidate = useInvalidateAssets();
  return useMutation({ mutationFn: (body: AssetClone) => cloneAsset(assetId, body), onSuccess: invalidate });
}

export function useRetireAsset() {
  const invalidate = useInvalidateAssets();
  return useMutation({ mutationFn: (assetId: string) => retireAsset(assetId), onSuccess: invalidate });
}

export function useImportAasx() {
  const invalidate = useInvalidateAssets();
  return useMutation({
    mutationFn: (input: { file: File; lineId: string; assetType: AssetType }) =>
      importAasx(input.file, input.lineId, input.assetType),
    onSuccess: invalidate,
  });
}
