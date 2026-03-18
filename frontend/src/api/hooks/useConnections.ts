import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from '../client';

export interface AWSConnection {
  id: string;
  name: string;
  region: string;
  credential_type: string;
  status: string;
  created_at: string;
}

interface CreateConnectionPayload {
  name: string;
  region: string;
  credential_type: string;
  credentials: Record<string, string>;
}

export function useConnections() {
  return useQuery<AWSConnection[]>({
    queryKey: ['connections'],
    queryFn: () => client.get('/api/aws/connections').then((r) => r.data),
  });
}

export function useCreateConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateConnectionPayload) =>
      client.post('/api/aws/connections', data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connections'] }),
  });
}

export function useDeleteConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      client.delete(`/api/aws/connections/${id}`).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['connections'] }),
  });
}
