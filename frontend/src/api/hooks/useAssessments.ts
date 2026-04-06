import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from '../client';

export interface Assessment {
  id: string;
  migration_id: string;
  status: string;
  current_step?: string | null;
  resources_assessed: number;
  avg_readiness_score: number;
  aws_monthly_cost: number;
  oci_projected_cost: number;
  dependency_artifacts?: {
    workload_graphs?: Record<string, string>;
    cloudtrail_event_count?: number;
    has_flowlogs?: boolean;
  } | null;
  created_at: string;
  completed_at?: string | null;
}

export interface ResourceAssessment {
  id: string;
  resource_id: string;
  name: string;
  aws_type: string;
  readiness_score: number;
  oci_shape: string;
  aws_monthly_cost: number;
  oci_monthly_cost: number;
  six_r_strategy: string;
  six_r_confidence?: string;
  os_name?: string;
  os_version?: string;
  os_compat_status: string;
  remediation_notes?: string;
}

export interface AppGroup {
  id: string;
  name: string;
  workload_type?: string | null;
  six_r_strategy: string;
  six_r_confidence?: string;
  resource_count: number;
  members: {
    resource_id: string;
    name: string;
    aws_type: string;
  }[];
}

export interface CostBreakdown {
  compute: { aws: number; oci: number };
  storage: { aws: number; oci: number };
  database: { aws: number; oci: number };
  networking: { aws: number; oci: number };
}

export interface TCOReport {
  aws_monthly: number;
  oci_monthly: number;
  savings_pct: number;
  three_year_aws: number;
  three_year_oci: number;
  three_year_savings: number;
  breakdown: CostBreakdown;
}

export interface DependencyData {
  nodes: { id: string; service?: string }[];
  edges: { source: string; target: string; edge_type?: string }[];
}

export interface WorkloadResource {
  id: string;
  name: string;
  aws_type: string;
}

export interface Workload {
  id: string | null;
  name: string;
  workload_type: string;
  grouping_method?: string | null;
  sixr_strategy?: string | null;
  readiness_score?: number | null;
  total_aws_cost_usd?: number | null;
  total_oci_cost_usd?: number | null;
  resource_count: number;
  resources: WorkloadResource[];
}

export function useWorkloads(migrationId: string) {
  return useQuery<Workload[]>({
    queryKey: ['workloads', migrationId],
    queryFn: () =>
      client.get(`/api/migrations/${migrationId}/workloads`).then((r) => r.data),
    enabled: !!migrationId,
  });
}

export function useAssessments(migrationId: string) {
  return useQuery<Assessment[]>({
    queryKey: ['assessments', migrationId],
    queryFn: () =>
      client.get(`/api/migrations/${migrationId}/assessments`).then((r) => r.data),
    enabled: !!migrationId,
    refetchInterval: (query) => {
      const data = query.state.data as Assessment[] | undefined;
      const latest = data?.[0];
      return latest?.status === 'pending' || latest?.status === 'running' ? 2000 : false;
    },
  });
}

export function useAssessment(assessmentId: string) {
  return useQuery<Assessment>({
    queryKey: ['assessment', assessmentId],
    queryFn: () =>
      client.get(`/api/assessments/${assessmentId}`).then((r) => r.data),
    enabled: !!assessmentId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'pending' || status === 'running' ? 3000 : false;
    },
  });
}

export function useResourceAssessments(assessmentId: string) {
  return useQuery<ResourceAssessment[]>({
    queryKey: ['assessment-resources', assessmentId],
    queryFn: () =>
      client.get(`/api/assessments/${assessmentId}/resources`).then((r) => r.data),
    enabled: !!assessmentId,
  });
}

export function useAppGroups(assessmentId: string) {
  return useQuery<AppGroup[]>({
    queryKey: ['assessment-app-groups', assessmentId],
    queryFn: () =>
      client.get(`/api/assessments/${assessmentId}/app-groups`).then((r) => r.data),
    enabled: !!assessmentId,
  });
}

export function useTCOReport(assessmentId: string) {
  return useQuery<TCOReport>({
    queryKey: ['assessment-tco', assessmentId],
    queryFn: () =>
      client.get(`/api/assessments/${assessmentId}/tco`).then((r) => r.data),
    enabled: !!assessmentId,
  });
}

export function useDependencies(assessmentId: string) {
  return useQuery<DependencyData>({
    queryKey: ['assessment-dependencies', assessmentId],
    queryFn: () =>
      client.get(`/api/assessments/${assessmentId}/dependencies`).then((r) => r.data),
    enabled: !!assessmentId,
  });
}

export function useRunAssessment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (migrationId: string) =>
      client.post(`/api/migrations/${migrationId}/assess`).then((r) => r.data),
    onSuccess: (_data, migrationId) => {
      qc.invalidateQueries({ queryKey: ['assessments', migrationId] });
    },
  });
}

export function useDeleteAssessment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assessmentId: string) =>
      client.delete(`/api/assessments/${assessmentId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['assessments'] });
      qc.invalidateQueries({ queryKey: ['assessment'] });
    },
  });
}

export function useBindGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ migrationId, appGroupId }: { migrationId: string; appGroupId: string }) =>
      client.post(`/api/migrations/${migrationId}/bind-group`, { app_group_id: appGroupId }).then((r) => r.data),
    onSuccess: (_data, { migrationId }) => {
      qc.invalidateQueries({ queryKey: ['migrations', migrationId] });
      qc.invalidateQueries({ queryKey: ['migrations'] });
    },
  });
}

export function useUnbindGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (migrationId: string) =>
      client.post(`/api/migrations/${migrationId}/unbind-group`).then((r) => r.data),
    onSuccess: (_data, migrationId) => {
      qc.invalidateQueries({ queryKey: ['migrations', migrationId] });
      qc.invalidateQueries({ queryKey: ['migrations'] });
    },
  });
}

export function useUpdateGroupMembers() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ groupId, addResourceIds, removeResourceIds }: { groupId: string; addResourceIds: string[]; removeResourceIds: string[] }) =>
      client.patch(`/api/app-groups/${groupId}/members`, { add_resource_ids: addResourceIds, remove_resource_ids: removeResourceIds }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workloads'] });
      qc.invalidateQueries({ queryKey: ['assessment-app-groups'] });
    },
  });
}

export function useCreateAppGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assessmentId, name, resourceIds }: { assessmentId: string; name: string; resourceIds: string[] }) =>
      client.post(`/api/assessments/${assessmentId}/app-groups`, { name, resource_ids: resourceIds }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workloads'] });
      qc.invalidateQueries({ queryKey: ['assessment-app-groups'] });
    },
  });
}
