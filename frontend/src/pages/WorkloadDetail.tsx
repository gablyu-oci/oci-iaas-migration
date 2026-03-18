import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { usePlan, useExecuteWorkload } from '../api/plans';
import type { Workload, PlanPhase, MigrationPlan } from '../api/plans';
import { useSkillRun, useSkillRunArtifacts } from '../api/hooks/useSkillRuns';
import { formatDate, formatCost, cn } from '../lib/utils';
import SkillProgressTracker from '../components/SkillProgressTracker';
import ArtifactViewer from '../components/ArtifactViewer';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

const STATUS_BADGE: Record<string, { bg: string; dot: string }> = {
  pending:  { bg: 'bg-gray-100 text-gray-700', dot: 'bg-gray-400' },
  draft:    { bg: 'bg-gray-100 text-gray-700', dot: 'bg-gray-400' },
  running:  { bg: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500 animate-pulse' },
  complete: { bg: 'bg-green-100 text-green-700', dot: 'bg-green-500' },
  failed:   { bg: 'bg-red-100 text-red-700', dot: 'bg-red-500' },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_BADGE[status] ?? STATUS_BADGE.pending;
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold', s.bg)}>
      <span className={cn('w-1.5 h-1.5 rounded-full', s.dot)} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

type Tab = 'overview' | 'progress' | 'results';

// ---------------------------------------------------------------------------
// Find workload from plan data
// ---------------------------------------------------------------------------
function findWorkloadInPlan(
  plan: MigrationPlan,
  workloadId: string,
): { workload: Workload; phase: PlanPhase; phaseIndex: number } | null {
  for (let i = 0; i < plan.phases.length; i++) {
    const phase = plan.phases[i];
    const workload = phase.workloads.find((w) => w.id === workloadId);
    if (workload) return { workload, phase, phaseIndex: i };
  }
  return null;
}

// ---------------------------------------------------------------------------
// WorkloadDetail Page
// ---------------------------------------------------------------------------
export default function WorkloadDetail() {
  const { workloadId } = useParams<{ workloadId: string }>();
  const executeMut = useExecuteWorkload();

  // We store the planId and the skill_run_id in local state because we might
  // receive a new skill_run_id after executing.
  const [planId, setPlanId] = useState<string | null>(null);
  const [skillRunId, setSkillRunId] = useState<string | null>(null);

  // We need to discover which plan this workload belongs to. We pass planId
  // from URL search params if available, otherwise we try all known plans.
  // For simplicity, use search params.
  const searchParams = new URLSearchParams(
    typeof window !== 'undefined' ? window.location.search : '',
  );
  const urlPlanId = searchParams.get('planId') ?? '';

  // Try to load the plan
  const effectivePlanId = planId || urlPlanId;
  const { data: plan, isLoading: planLoading, isError: planError } = usePlan(effectivePlanId);

  // Extract workload, phase, and phase index from the plan
  const found = plan && workloadId ? findWorkloadInPlan(plan, workloadId) : null;
  const workload = found?.workload ?? null;
  const phase = found?.phase ?? null;
  const phaseIndex = found?.phaseIndex ?? 0;

  // Set planId from the plan data when it loads
  useEffect(() => {
    if (plan && !planId) {
      setPlanId(plan.id);
    }
  }, [plan, planId]);

  // Track the skill_run_id (may update when workload is executed)
  useEffect(() => {
    if (workload?.skill_run_id && !skillRunId) {
      setSkillRunId(workload.skill_run_id);
    }
  }, [workload?.skill_run_id, skillRunId]);

  // Load the skill run data if we have a skill_run_id
  const activeSkillRunId = skillRunId || workload?.skill_run_id || '';
  const { data: skillRun } = useSkillRun(activeSkillRunId);
  const { data: artifacts } = useSkillRunArtifacts(activeSkillRunId);

  // Determine effective status (from live skill run or workload)
  const effectiveStatus = skillRun
    ? (skillRun.status === 'complete' ? 'complete'
       : skillRun.status === 'failed' ? 'failed'
       : skillRun.status === 'running' || skillRun.status === 'queued' ? 'running'
       : workload?.status ?? 'pending')
    : workload?.status ?? 'pending';

  // Default tab based on status
  const defaultTab: Tab =
    effectiveStatus === 'running' ? 'progress'
    : effectiveStatus === 'complete' || effectiveStatus === 'failed' ? 'results'
    : 'overview';

  const [tab, setTab] = useState<Tab>(defaultTab);

  // Update tab when status changes to running or complete
  useEffect(() => {
    if (effectiveStatus === 'running' && tab === 'overview') {
      setTab('progress');
    }
  }, [effectiveStatus, tab]);

  // Is this phase unlocked?
  const phaseUnlocked =
    phaseIndex === 0 ||
    (plan && plan.phases[phaseIndex - 1]?.status === 'complete') ||
    false;

  const handleExecute = async () => {
    if (!workloadId) return;
    if (!confirm(`Execute this workload? This will translate ${workload?.resource_count ?? 0} AWS resources using the ${workload?.skill_type} skill.`)) return;
    const result = await executeMut.mutateAsync(workloadId);
    setSkillRunId(result.skill_run_id);
    setTab('progress');
  };

  const handleComplete = useCallback(() => {
    setTab('results');
  }, []);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!workloadId) {
    return <div className="text-center py-12 text-gray-500">No workload ID provided.</div>;
  }

  if (planLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" role="status" aria-label="Loading" />
      </div>
    );
  }

  if (planError || !plan || !workload) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 mb-4">Failed to load workload details.</p>
        <Link to="/dashboard" className="text-blue-600 hover:text-blue-800">Back to Dashboard</Link>
      </div>
    );
  }

  const TABS: { key: Tab; label: string; visible: boolean }[] = [
    { key: 'overview', label: 'Overview', visible: true },
    { key: 'progress', label: 'Progress', visible: !!activeSkillRunId && effectiveStatus === 'running' },
    { key: 'results', label: 'Results', visible: !!activeSkillRunId && (effectiveStatus === 'complete' || effectiveStatus === 'failed') },
  ];

  const confidencePercent = skillRun ? (skillRun.confidence * 100).toFixed(0) : null;
  const confidenceColor = skillRun
    ? skillRun.confidence >= 0.8 ? 'text-green-600' : skillRun.confidence >= 0.5 ? 'text-yellow-600' : 'text-red-600'
    : '';

  const durationSecs =
    skillRun?.started_at && skillRun?.completed_at
      ? (new Date(skillRun.completed_at).getTime() - new Date(skillRun.started_at).getTime()) / 1000
      : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to={effectivePlanId ? `/plans/${effectivePlanId}` : '/dashboard'}
          className="text-sm text-gray-500 hover:text-gray-700 mb-2 inline-block"
        >
          &larr; Back to Plan
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{workload.name}</h1>
              <StatusBadge status={effectiveStatus} />
            </div>
            {phase && (
              <p className="text-sm text-gray-500 mt-1">
                Phase {phase.order_index}: {phase.name}
              </p>
            )}
            <p className="text-sm text-gray-400 mt-0.5">
              {workload.skill_type && (
                <span className="font-mono">{workload.skill_type}</span>
              )}
              {workload.skill_type && ' \u00B7 '}
              {workload.resource_count} resource{workload.resource_count !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6" aria-label="Tabs">
          {TABS.filter((t) => t.visible).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'py-3 px-1 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                tab === t.key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">Workload Details</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
              <div>
                <p className="text-gray-500">Skill Type</p>
                <p className="font-mono mt-1">{workload.skill_type ?? '\u2014'}</p>
              </div>
              <div>
                <p className="text-gray-500">Description</p>
                <p className="mt-1">{workload.description ?? '\u2014'}</p>
              </div>
              <div>
                <p className="text-gray-500">Status</p>
                <p className="mt-1">{effectiveStatus}</p>
              </div>
              <div>
                <p className="text-gray-500">Phase</p>
                <p className="mt-1">{phase ? `${phase.order_index} - ${phase.name}` : '\u2014'}</p>
              </div>
            </div>
          </div>

          {/* Resource count summary */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">
              Included Resources ({workload.resource_count})
            </h2>
            <p className="text-sm text-gray-500">
              This workload contains {workload.resource_count} AWS resource{workload.resource_count !== 1 ? 's' : ''} for migration.
            </p>
          </div>

          {/* Action area */}
          <div>
            {effectiveStatus === 'pending' && phaseUnlocked && (
              <button
                onClick={handleExecute}
                disabled={executeMut.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium disabled:opacity-75 disabled:cursor-not-allowed"
              >
                {executeMut.isPending ? 'Starting...' : 'Execute Workload'}
              </button>
            )}
            {effectiveStatus === 'pending' && !phaseUnlocked && (
              <button
                disabled
                className="px-4 py-2 bg-gray-100 text-gray-400 rounded-lg font-medium cursor-not-allowed"
              >
                Blocked: Complete Phase {phaseIndex} first
              </button>
            )}
            {effectiveStatus === 'running' && (
              <p className="text-sm text-blue-600">
                Execution in progress... View the Progress tab.
              </p>
            )}
            {effectiveStatus === 'complete' && (
              <p className="text-sm text-green-600">
                Execution complete. View the Results tab.
              </p>
            )}
            {effectiveStatus === 'failed' && (
              <button
                onClick={handleExecute}
                disabled={executeMut.isPending}
                className="px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 text-sm font-medium disabled:opacity-75"
              >
                {executeMut.isPending ? 'Starting...' : 'Retry Execution'}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Progress tab */}
      {tab === 'progress' && activeSkillRunId && (
        <div className="max-w-2xl mx-auto">
          <SkillProgressTracker
            skillRunId={activeSkillRunId}
            onComplete={handleComplete}
          />
        </div>
      )}

      {/* Results tab */}
      {tab === 'results' && activeSkillRunId && skillRun && (
        <div className="space-y-6">
          {/* Summary */}
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">Summary</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
              <div>
                <p className="text-sm text-gray-500">Confidence</p>
                <p className={cn('text-2xl font-bold mt-1', confidenceColor)}>
                  {confidencePercent != null ? `${confidencePercent}%` : '\u2014'}
                </p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Total Cost</p>
                <p className="font-mono text-sm mt-1">{formatCost(skillRun.total_cost_usd)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Iterations</p>
                <p className="text-sm mt-1">{skillRun.current_iteration ?? '\u2014'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Duration</p>
                <p className="text-sm mt-1">{durationSecs != null ? formatDuration(durationSecs) : '\u2014'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Status</p>
                <p className="text-sm mt-1">{skillRun.status}</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t grid grid-cols-2 gap-4 text-sm">
              <div><span className="text-gray-500">Started:</span> {formatDate(skillRun.started_at)}</div>
              <div><span className="text-gray-500">Completed:</span> {formatDate(skillRun.completed_at)}</div>
            </div>
          </div>

          {/* Errors */}
          {skillRun.status === 'failed' && skillRun.errors && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="text-red-800 font-semibold mb-2">Errors</h3>
              <pre className="text-red-700 text-sm whitespace-pre-wrap">
                {JSON.stringify(skillRun.errors, null, 2)}
              </pre>
              <div className="mt-4">
                <button
                  onClick={handleExecute}
                  disabled={executeMut.isPending}
                  className="px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 text-sm font-medium disabled:opacity-75"
                >
                  {executeMut.isPending ? 'Starting...' : 'Retry Execution'}
                </button>
              </div>
            </div>
          )}

          {/* Artifacts */}
          {artifacts && artifacts.length > 0 && (
            <div className="bg-white rounded-lg shadow p-6">
              <ArtifactViewer skillRunId={activeSkillRunId} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
