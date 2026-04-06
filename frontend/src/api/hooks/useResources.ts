import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from '../client';

export interface LatestSkillRunSummary {
  id: string;
  status: string;
  skill_type: string;
  confidence: number;
  completed_at: string | null;
}

export interface Resource {
  id: string;
  aws_type: string;
  aws_arn: string;
  name: string;
  status: string;
  migration_id: string;
  created_at: string;
  raw_config: Record<string, unknown>;
  migration_name: string | null;
  latest_skill_run: LatestSkillRunSummary | null;
}

export function useResources(params?: {
  type?: string;
  migration_id?: string;
  connection_id?: string;
  status?: string;
}) {
  return useQuery<Resource[]>({
    queryKey: ['resources', params],
    queryFn: () => client.get('/api/aws/resources', { params }).then((r) => r.data),
  });
}

export function useResourcesByMigration(migrationId: string) {
  return useResources(migrationId ? { migration_id: migrationId } : undefined);
}

export function useDeleteResource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (resourceId: string) =>
      client.delete(`/api/aws/resources/${resourceId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['resources'] }),
  });
}
