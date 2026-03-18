import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import client from './client';

// ---------------------------------------------------------------------------
// Types (match backend PlanOut, PhaseOut, WorkloadOut exactly)
// ---------------------------------------------------------------------------

export interface WorkloadResource {
  id: string;
  workload_id: string;
  resource_id: string;
}

export interface Workload {
  id: string;
  name: string;
  description: string | null;
  skill_type: string | null;
  status: string;
  skill_run_id: string | null;
  resource_count: number;
}

export interface PlanPhase {
  id: string;
  name: string;
  description: string | null;
  order_index: number;
  status: string;
  workloads: Workload[];
}

export interface MigrationPlan {
  id: string;
  migration_id: string;
  status: string;
  generated_at: string | null;
  summary: Record<string, unknown> | null;
  phases: PlanPhase[];
}

export interface ExecuteOut {
  skill_run_id: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export function generatePlan(migrationId: string): Promise<MigrationPlan> {
  return client.post(`/api/migrations/${migrationId}/plan`).then((r) => r.data);
}

export function getPlan(planId: string): Promise<MigrationPlan> {
  return client.get(`/api/plans/${planId}`).then((r) => r.data);
}

export function getPlanStatus(planId: string): Promise<MigrationPlan> {
  return client.get(`/api/plans/${planId}/status`).then((r) => r.data);
}

export function executeWorkload(workloadId: string): Promise<ExecuteOut> {
  return client.post(`/api/workloads/${workloadId}/execute`).then((r) => r.data);
}

export function deletePlan(planId: string): Promise<void> {
  return client.delete(`/api/plans/${planId}`).then(() => undefined);
}

export function getWorkloadStreamUrl(skillRunId: string): string {
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const token = localStorage.getItem('token');
  return `${API_URL}/api/skill-runs/${skillRunId}/stream?token=${token}`;
}

// ---------------------------------------------------------------------------
// React Query hooks
// ---------------------------------------------------------------------------

export function usePlan(planId: string) {
  return useQuery<MigrationPlan>({
    queryKey: ['plans', planId],
    queryFn: () => getPlan(planId),
    enabled: !!planId,
  });
}

export function usePlanStatus(planId: string) {
  return useQuery<MigrationPlan>({
    queryKey: ['plans', planId, 'status'],
    queryFn: () => getPlanStatus(planId),
    enabled: !!planId,
    refetchInterval: (query) => {
      const plan = query.state.data;
      if (plan && (plan.status === 'complete' || plan.status === 'failed')) return false;
      if (plan?.phases?.some((p) => p.status === 'running')) return 3000;
      return false;
    },
  });
}

export function useGeneratePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (migrationId: string) => generatePlan(migrationId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] });
      qc.invalidateQueries({ queryKey: ['migrations'] });
    },
  });
}

export function useExecuteWorkload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (workloadId: string) => executeWorkload(workloadId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] });
    },
  });
}

export function useDeletePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => deletePlan(planId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] });
      qc.invalidateQueries({ queryKey: ['migrations'] });
    },
  });
}
