import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from '../client';

export interface Migration {
  id: string;
  name: string;
  status: string;
  aws_connection_id: string | null;
  created_at: string;
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
