import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  usePlan,
  usePlanStatus,
  useDeletePlan,
  useExecuteWorkload,
} from '../api/plans';
import type { PlanPhase, Workload } from '../api/plans';
import { formatDate, cn } from '../lib/utils';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_BADGE: Record<string, { bg: string; dot: string }> = {
  pending: { bg: 'bg-gray-100 text-gray-700', dot: 'bg-gray-400' },
  draft:   { bg: 'bg-gray-100 text-gray-700', dot: 'bg-gray-400' },
  running: { bg: 'bg-blue-100 text-blue-700', dot: 'bg-blue-500 animate-pulse' },
  complete:{ bg: 'bg-green-100 text-green-700', dot: 'bg-green-500' },
  failed:  { bg: 'bg-red-100 text-red-700', dot: 'bg-red-500' },
};

const SKILL_CHIP_COLORS: Record<string, string> = {
  network_translation:      'bg-cyan-100 text-cyan-800',
  database_translation:     'bg-amber-100 text-amber-800',
  ec2_translation:          'bg-purple-100 text-purple-800',
  loadbalancer_translation: 'bg-indigo-100 text-indigo-800',
  cfn_terraform:            'bg-teal-100 text-teal-800',
  iam_translation:          'bg-orange-100 text-orange-800',
};

// ---------------------------------------------------------------------------
// StatusBadge
// ---------------------------------------------------------------------------
function StatusBadge({ status }: { status: string }) {
  const s = STATUS_BADGE[status] ?? STATUS_BADGE.pending;
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold', s.bg)}>
      <span className={cn('w-1.5 h-1.5 rounded-full', s.dot)} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Phase Timeline Bar
// ---------------------------------------------------------------------------
function PhaseTimeline({ phases }: { phases: PlanPhase[] }) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-5">
        Phase Timeline
      </p>
      <div className="flex items-center gap-0">
        {phases.map((phase, i) => {
          const done = phase.status === 'complete';
          const running = phase.status === 'running';
          const failed = phase.status === 'failed';
          const isLast = i === phases.length - 1;

          // Determine if this phase is locked (previous phase not complete)
          const prevComplete = i === 0 || phases[i - 1].status === 'complete';
          const locked = !prevComplete && phase.status === 'pending';

          return (
            <div key={phase.id} className="flex items-center flex-1 min-w-0">
              <div className="flex flex-col items-center flex-shrink-0">
                <div
                  className={cn(
                    'w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-500',
                    done && 'bg-green-100 text-green-600',
                    running && 'bg-blue-100 text-blue-600 ring-2 ring-blue-400 ring-offset-2',
                    failed && 'bg-red-100 text-red-600',
                    locked && 'bg-gray-50 text-gray-300',
                    !done && !running && !failed && !locked && 'bg-gray-100 text-gray-500',
                  )}
                >
                  {done ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : running ? (
                    <span className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                  ) : failed ? (
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  ) : locked ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                  ) : (
                    phase.order_index
                  )}
                </div>
                <span
                  className={cn(
                    'text-xs mt-1.5 font-medium text-center leading-tight max-w-[80px] truncate',
                    done && 'text-green-600',
                    running && 'text-blue-600',
                    failed && 'text-red-600',
                    !done && !running && !failed && 'text-gray-400',
                  )}
                >
                  {phase.name}
                </span>
              </div>

              {!isLast && (
                <div className="flex-1 h-0.5 mx-1 mb-5">
                  <div
                    className={cn(
                      'h-full transition-all duration-700 rounded-full',
                      done ? 'bg-green-400' : 'bg-gray-200',
                    )}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// WorkloadCard
// ---------------------------------------------------------------------------
function WorkloadCard({
  workload,
  phaseUnlocked,
  onExecute,
  executing,
}: {
  workload: Workload;
  phaseUnlocked: boolean;
  onExecute: (id: string) => void;
  executing: boolean;
}) {
  const chipColor = workload.skill_type
    ? SKILL_CHIP_COLORS[workload.skill_type] ?? 'bg-gray-100 text-gray-600'
    : 'bg-gray-100 text-gray-600';

  const borderClass =
    workload.status === 'running'
      ? 'border-blue-300 bg-blue-50/30'
      : workload.status === 'complete'
      ? 'border-green-300 bg-green-50/30'
      : workload.status === 'failed'
      ? 'border-red-300 bg-red-50/30'
      : 'border-gray-200';

  return (
    <div className={cn('bg-white rounded-lg border p-4 hover:border-gray-300 transition-colors', borderClass)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Link
              to={`/workloads/${workload.id}`}
              className="text-base font-semibold text-gray-900 hover:text-blue-600"
            >
              {workload.name}
            </Link>
            {workload.skill_type && (
              <span className={cn('inline-flex px-2 py-0.5 rounded text-xs font-mono font-medium', chipColor)}>
                {workload.skill_type}
              </span>
            )}
          </div>
          {workload.description && (
            <p className="text-sm text-gray-500 mt-1">{workload.description}</p>
          )}
          <p className="text-xs text-gray-400 mt-1">Resources: {workload.resource_count}</p>
        </div>
        <StatusBadge status={workload.status} />
      </div>

      {/* Action area */}
      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-3">
        {workload.status === 'pending' && phaseUnlocked && (
          <button
            onClick={() => {
              if (confirm(`Execute this workload? This will translate ${workload.resource_count} AWS resources using the ${workload.skill_type} skill.`)) {
                onExecute(workload.id);
              }
            }}
            disabled={executing}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm disabled:opacity-75 disabled:cursor-not-allowed"
          >
            {executing ? 'Starting...' : 'Execute'}
          </button>
        )}
        {workload.status === 'pending' && !phaseUnlocked && (
          <button
            disabled
            className="px-4 py-2 bg-gray-100 text-gray-400 rounded-lg font-medium text-sm cursor-not-allowed"
            title="Complete the previous phase first"
          >
            Blocked
          </button>
        )}
        {workload.status === 'running' && (
          <Link
            to={`/workloads/${workload.id}`}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            View Progress
          </Link>
        )}
        {workload.status === 'complete' && (
          <Link
            to={`/workloads/${workload.id}`}
            className="text-sm text-green-600 hover:text-green-800 font-medium"
          >
            View Results
          </Link>
        )}
        {workload.status === 'failed' && (
          <>
            <button
              onClick={() => onExecute(workload.id)}
              disabled={executing}
              className="px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 text-sm font-medium disabled:opacity-75"
            >
              Retry
            </button>
            <Link
              to={`/workloads/${workload.id}`}
              className="text-sm text-gray-600 hover:text-gray-800 font-medium"
            >
              View Details
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MigrationPlan Page
// ---------------------------------------------------------------------------
export default function MigrationPlanPage() {
  const { planId } = useParams<{ planId: string }>();
  const navigate = useNavigate();

  const { data: plan, isLoading, isError } = usePlan(planId || '');
  const { data: liveStatus } = usePlanStatus(planId || '');
  const deletePlanMut = useDeletePlan();
  const executeMut = useExecuteWorkload();

  const [expandedPhases, setExpandedPhases] = useState<Set<string>>(new Set());

  // Use live status data when available, else fall back to initial load
  const activePlan = liveStatus ?? plan;

  if (!planId) {
    return <div className="text-center py-12 text-gray-500">No plan ID provided.</div>;
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" role="status" aria-label="Loading" />
      </div>
    );
  }

  if (isError || !activePlan) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 mb-4">Failed to load migration plan.</p>
        <Link to="/dashboard" className="text-blue-600 hover:text-blue-800">Back to Dashboard</Link>
      </div>
    );
  }

  const phases = activePlan.phases;
  const totalResources = phases.reduce(
    (sum, p) => sum + p.workloads.reduce((ws, w) => ws + w.resource_count, 0),
    0,
  );
  const completedPhases = phases.filter((p) => p.status === 'complete').length;
  const completionPct = phases.length > 0 ? Math.round((completedPhases / phases.length) * 100) : 0;
  const pendingPhases = phases.filter((p) => p.status === 'pending').length;
  const runningPhases = phases.filter((p) => p.status === 'running').length;

  const progressBarColor =
    activePlan.status === 'complete'
      ? 'bg-green-500'
      : phases.some((p) => p.status === 'failed')
      ? 'bg-red-500'
      : phases.some((p) => p.status === 'running')
      ? 'bg-blue-500'
      : 'bg-gray-300';

  const togglePhase = (phaseId: string) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev);
      if (next.has(phaseId)) {
        next.delete(phaseId);
      } else {
        next.add(phaseId);
      }
      return next;
    });
  };

  const isPhaseUnlocked = (phaseIndex: number): boolean => {
    if (phaseIndex === 0) return true;
    const prevPhase = phases[phaseIndex - 1];
    return prevPhase.status === 'complete';
  };

  const handleDelete = async () => {
    if (confirm('Delete this plan? All workload progress will be lost.')) {
      await deletePlanMut.mutateAsync(planId);
      navigate('/dashboard');
    }
  };

  const handleExecuteWorkload = (workloadId: string) => {
    executeMut.mutate(workloadId);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <Link to="/dashboard" className="text-sm text-gray-500 hover:text-gray-700 mb-2 inline-block">
          &larr; Back to Dashboard
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">Migration Plan</h1>
              <StatusBadge status={activePlan.status} />
            </div>
            <p className="text-sm text-gray-500 mt-1">
              Generated {formatDate(activePlan.generated_at)}
            </p>
          </div>
          <button
            onClick={handleDelete}
            className="text-sm text-red-500 hover:text-red-700 font-medium"
          >
            Delete Plan
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Total Resources</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{totalResources}</p>
          <p className="text-sm text-gray-500">
            across {phases.length} phase{phases.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Phases</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{phases.length}</p>
          <p className="text-sm text-gray-500">
            {pendingPhases} pending, {runningPhases} in progress
          </p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Completion</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{completionPct}%</p>
          <div className="w-full h-2 bg-gray-200 rounded-full mt-2 overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-700', progressBarColor)}
              style={{ width: `${completionPct}%` }}
            />
          </div>
          <p className="text-sm text-gray-500 mt-1">
            {completedPhases}/{phases.length} phases done
          </p>
        </div>
      </div>

      {/* Phase Timeline */}
      {phases.length > 0 && <PhaseTimeline phases={phases} />}

      {/* Phase Accordion */}
      <div className="space-y-4">
        {phases.map((phase, i) => {
          const expanded = expandedPhases.has(phase.id);
          const unlocked = isPhaseUnlocked(i);
          const phaseResourceCount = phase.workloads.reduce((sum, w) => sum + w.resource_count, 0);

          return (
            <div
              key={phase.id}
              className={cn(
                'bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden',
                !unlocked && phase.status === 'pending' && 'opacity-60',
              )}
            >
              {/* Phase header */}
              <button
                onClick={() => togglePhase(phase.id)}
                className="w-full flex items-start justify-between p-5 cursor-pointer hover:bg-gray-50 transition-colors text-left"
                aria-expanded={expanded}
              >
                <div className="flex items-start gap-3 min-w-0">
                  <svg
                    className={cn(
                      'w-5 h-5 text-gray-400 transition-transform mt-0.5 flex-shrink-0',
                      expanded && 'rotate-90',
                    )}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                  <div className="min-w-0">
                    <p className="text-base font-semibold text-gray-900">
                      Phase {phase.order_index}: {phase.name}
                    </p>
                    {phase.description && (
                      <p className="text-sm text-gray-500 mt-1">{phase.description}</p>
                    )}
                    {!unlocked && phase.status === 'pending' && (
                      <p className="text-xs text-gray-400 mt-1">
                        (Requires Phase {phase.order_index - 1} to complete first)
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end flex-shrink-0 ml-4">
                  <StatusBadge status={phase.status} />
                  <p className="text-xs text-gray-400 mt-1">{phaseResourceCount} resources</p>
                  <p className="text-xs text-gray-400">
                    {phase.workloads.length} workload{phase.workloads.length !== 1 ? 's' : ''}
                  </p>
                </div>
              </button>

              {/* Expanded content */}
              {expanded && (
                <div className="border-t border-gray-200 px-5 py-4 bg-gray-50 space-y-3">
                  {phase.workloads.map((workload) => (
                    <WorkloadCard
                      key={workload.id}
                      workload={workload}
                      phaseUnlocked={unlocked}
                      onExecute={handleExecuteWorkload}
                      executing={executeMut.isPending}
                    />
                  ))}
                  {phase.workloads.length === 0 && (
                    <p className="text-sm text-gray-400">No workloads in this phase.</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
