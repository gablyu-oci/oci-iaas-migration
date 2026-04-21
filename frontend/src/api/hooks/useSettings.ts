import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from '../client';

export interface ModelInfo {
  id: string;
  family: 'openai' | 'google' | 'xai' | 'meta' | string;
  label: string;
  reasoning?: boolean;
}

export interface ModelSettings {
  writer_model: string;
  reviewer_model: string;
  available: ModelInfo[];
}

export interface Credentials {
  base_url: string;
  api_key_masked: string;
  api_key_set: boolean;
}

export interface CredentialsUpdate {
  api_key?: string;   // blank string = clear; undefined = keep existing
  base_url: string;
}

export interface TestResult {
  ok: boolean;
  error: string | null;
  model_tested: string | null;
  latency_ms: number | null;
}

export function useModelSettings() {
  return useQuery<ModelSettings>({
    queryKey: ['settings', 'models'],
    queryFn: async () => (await client.get('/api/settings/models')).data,
  });
}

export function useUpdateModelSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { writer_model: string; reviewer_model: string }) =>
      (await client.put('/api/settings/models', body)).data as ModelSettings,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['settings', 'models'] }); },
  });
}

export function useCredentials() {
  return useQuery<Credentials>({
    queryKey: ['settings', 'credentials'],
    queryFn: async () => (await client.get('/api/settings/credentials')).data,
  });
}

export function useUpdateCredentials() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CredentialsUpdate) =>
      (await client.put('/api/settings/credentials', body)).data as Credentials,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['settings', 'credentials'] }); },
  });
}

export function useTestCredentials() {
  return useMutation({
    // When body is omitted we POST with no payload at all — the backend
    // treats the request as "test the currently saved config". Passing an
    // empty {} would fail validation, so we explicitly elide the data arg.
    mutationFn: async (body?: CredentialsUpdate) => {
      const url = '/api/settings/credentials/test';
      const res = body ? await client.post(url, body) : await client.post(url);
      return res.data as TestResult;
    },
  });
}
