import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from '../client';

export interface Migration {
  id: string;
  name: string;
  status: string;
  aws_connection_id: string | null;
  created_at: string;
  resource_count?: number | null;
  discovery_status: string;
  discovery_error?: string | null;
  discovered_at?: string | null;
  plan_status?: string | null;
  plan_workload_id?: string | null;
  plan_workload_name?: string | null;
  plan_started_at?: string | null;
  plan_max_iterations?: number | null;
  migrate_status?: string | null;
  migrate_workload_name?: string | null;
  migrate_started_at?: string | null;
  migrate_current_step?: string | null;
  migrate_terraform_plan?: string | null;
  migrate_logs?: string[] | null;
}

export function useMigrations() {
  return useQuery<Migration[]>({
    queryKey: ['migrations'],
    queryFn: () => client.get('/api/migrations').then((r) => r.data),
  });
}

export function useCreateMigration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; aws_connection_id?: string }) =>
      client.post('/api/migrations', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['migrations'] }),
  });
}

export function useMigration(id: string) {
  return useQuery<Migration>({
    queryKey: ['migrations', id],
    queryFn: () => client.get(`/api/migrations/${id}`).then((r) => r.data),
    enabled: !!id,
    refetchInterval: (query) => {
      const d = query.state.data;
      if (d?.discovery_status === 'discovering') return 3000;
      if (d?.plan_status === 'running') return 3000;
      if (d?.migrate_status && !['completed', 'failed', 'rolled_back', 'rejected'].includes(d.migrate_status)) return 3000;
      return false;
    },
  });
}

export function useExtractResources() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (migrationId: string) =>
      client.post(`/api/migrations/${migrationId}/extract`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resources'] }),
  });
}

export function useExtractWithInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      migrationId,
      instanceId,
    }: {
      migrationId: string;
      instanceId?: string;
    }) => {
      const params = instanceId ? { instance_id: instanceId } : undefined;
      return client
        .post(`/api/migrations/${migrationId}/extract`, null, { params })
        .then((r) => r.data);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['resources'] });
      qc.invalidateQueries({ queryKey: ['migrations', variables.migrationId] });
    },
  });
}

export function useDeleteMigration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (migrationId: string) =>
      client.delete(`/api/migrations/${migrationId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['migrations'] }),
  });
}

export function useUploadToMigration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      migrationId,
      file,
      fileType,
    }: {
      migrationId: string;
      file: File;
      fileType: string;
    }) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('file_type', fileType);
      return client
        .post(`/api/migrations/${migrationId}/upload`, formData)
        .then((r) => r.data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resources'] }),
  });
}
