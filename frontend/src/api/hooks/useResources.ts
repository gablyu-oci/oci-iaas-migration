import { useQuery } from '@tanstack/react-query';
import client from '../client';

export interface Resource {
  id: string;
  aws_type: string;
  aws_arn: string;
  name: string;
  status: string;
  migration_id: string;
  created_at: string;
  raw_config: Record<string, unknown>;
}

export function useResources(params?: {
  type?: string;
  migration_id?: string;
  status?: string;
}) {
  return useQuery<Resource[]>({
    queryKey: ['resources', params],
    queryFn: () => client.get('/api/aws/resources', { params }).then((r) => r.data),
  });
}
