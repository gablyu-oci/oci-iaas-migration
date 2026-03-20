import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { usePlan, useExecuteWorkload } from '../api/plans';
import type { Workload, PlanPhase, MigrationPlan } from '../api/plans';
import { useTranslationJob, useTranslationJobArtifacts } from '../api/hooks/useTranslationJobs';
import { formatDate, formatCost } from '../lib/utils';
import SkillProgressTracker from '../components/SkillProgressTracker';
import ArtifactViewer from '../components/ArtifactViewer';

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

function statusBadge(status: string): string {
  const map: Record<string, string> = {
    pending:  'badge badge-neutral',
    draft:    'badge badge-neutral',
    running:  'badge badge-running',
    complete: 'badge badge-success',
    failed:   'badge badge-error',
  };
  return map[status] ?? 'badge badge-neutral';
}

type Tab = 'overview' | 'progress' | 'results';

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

export default function WorkloadDetail() {
  const { workloadId } = useParams<{ workloadId: string }>();
  const executeMut = useExecuteWorkload();

  const [planId, setPlanId] = useState<string | null>(null);
  const [skillRunId, setSkillRunId] = useState<string | null>(null);

  const searchParams = new URLSearchParams(
    typeof window !== 'undefined' ? window.location.search : '',
  );
  const urlPlanId = searchParams.get('planId') ?? '';

  const effectivePlanId = planId || urlPlanId;
  const { data: plan, isLoading: planLoading, isError: planError } = usePlan(effectivePlanId);

  const found = plan && workloadId ? findWorkloadInPlan(plan, workloadId) : null;
  const workload = found?.workload ?? null;
  const phase = found?.phase ?? null;
  const phaseIndex = found?.phaseIndex ?? 0;

  useEffect(() => {
    if (plan && !planId) setPlanId(plan.id);
  }, [plan, planId]);

  useEffect(() => {
    if (workload?.translation_job_id && !skillRunId) {
      setSkillRunId(workload.translation_job_id);
    }
  }, [workload?.translation_job_id, skillRunId]);

  const activeSkillRunId = skillRunId || workload?.translation_job_id || '';
  const { data: skillRun } = useTranslationJob(activeSkillRunId);
  const { data: artifacts } = useTranslationJobArtifacts(activeSkillRunId);

  const effectiveStatus = skillRun
    ? (skillRun.status === 'complete' ? 'complete'
       : skillRun.status === 'failed' ? 'failed'
       : skillRun.status === 'running' || skillRun.status === 'queued' ? 'running'
       : workload?.status ?? 'pending')
    : workload?.status ?? 'pending';

  const defaultTab: Tab =
    effectiveStatus === 'running' ? 'progress'
    : effectiveStatus === 'complete' || effectiveStatus === 'failed' ? 'results'
    : 'overview';

  const [tab, setTab] = useState<Tab>(defaultTab);

  useEffect(() => {
    if (effectiveStatus === 'running' && tab === 'overview') setTab('progress');
  }, [effectiveStatus, tab]);

  const phaseUnlocked =
    phaseIndex === 0 ||
    (plan && plan.phases[phaseIndex - 1]?.status === 'complete') ||
    false;

  const handleExecute = async () => {
    if (!workloadId) return;
    if (!confirm(`Execute this workload? This will translate ${workload?.resource_count ?? 0} AWS resources using the ${workload?.skill_type} skill.`)) return;
    const result = await executeMut.mutateAsync(workloadId);
    setSkillRunId(result.translation_job_id);
    setTab('progress');
  };

  const handleComplete = useCallback(() => {
    setTab('results');
  }, []);

  if (!workloadId) {
    return <div className="empty-state"><p>No workload ID provided.</p></div>;
  }

  if (planLoading) {
    return (
      <div className="flex justify-center py-12">
        <span className="spinner spinner-lg" role="status" aria-label="Loading" />
      </div>
    );
  }

  if (planError || !plan || !workload) {
    return (
      <div className="space-y-4 py-12 text-center">
        <p style={{ color: '#dc2626' }}>Failed to load workload details.</p>
        <Link to="/dashboard" className="back-link" style={{ justifyContent: 'center' }}>
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const TABS: { key: Tab; label: string; visible: boolean }[] = [
    { key: 'overview', label: 'Overview', visible: true },
    { key: 'progress', label: 'Progress', visible: !!activeSkillRunId && effectiveStatus === 'running' },
    { key: 'results', label: 'Results', visible: !!activeSkillRunId && (effectiveStatus === 'complete' || effectiveStatus === 'failed') },
  ];

  const confidencePct = skillRun ? Math.round(skillRun.confidence * 100) : null;
  const confidenceColor = skillRun
    ? skillRun.confidence >= 0.8 ? '#16a34a'
      : skillRun.confidence >= 0.5 ? '#d97706'
      : '#dc2626'
    : '#94a3b8';

  const durationSecs =
    skillRun?.started_at && skillRun?.completed_at
      ? (new Date(skillRun.completed_at).getTime() - new Date(skillRun.started_at).getTime()) / 1000
      : null;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <Link
          to={effectivePlanId ? `/plans/${effectivePlanId}` : '/dashboard'}
          className="back-link"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Plan
        </Link>
        <div className="flex items-start justify-between mt-2">
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="page-title" style={{ marginBottom: 0 }}>{workload.name}</h1>
              <span className={statusBadge(effectiveStatus)}>
                <span className="badge-dot" />
                {effectiveStatus.charAt(0).toUpperCase() + effectiveStatus.slice(1)}
              </span>
            </div>
            {phase && (
              <p className="text-xs mt-1" style={{ color: '#64748b' }}>
                Phase {phase.order_index}: {phase.name}
              </p>
            )}
            {workload.skill_type && (
              <p className="text-xs mt-0.5" style={{ color: '#475569', fontFamily: 'var(--font-mono)' }}>
                {workload.skill_type} · {workload.resource_count} resource{workload.resource_count !== 1 ? 's' : ''}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {TABS.filter((t) => t.visible).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`tab-btn ${tab === t.key ? 'active' : ''}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <div className="space-y-4">
          <div className="panel">
            <div className="panel-header">
              <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Workload Details</h2>
            </div>
            <div className="panel-body">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-xs">
                {[
                  { label: 'Skill Type', value: workload.skill_type ?? '—', mono: true },
                  { label: 'Description', value: workload.description ?? '—' },
                  { label: 'Status', value: effectiveStatus },
                  { label: 'Phase', value: phase ? `${phase.order_index} — ${phase.name}` : '—' },
                ].map(({ label, value, mono }) => (
                  <div key={label}>
                    <p className="field-label">{label}</p>
                    <p
                      className="mt-1 text-xs"
                      style={{ color: '#0f172a', fontFamily: mono ? 'var(--font-mono)' : undefined }}
                    >
                      {value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>
                Included Resources
                <span className="tab-count ml-2">{workload.resource_count}</span>
              </h2>
            </div>
            <div className="panel-body">
              <p className="text-xs" style={{ color: '#64748b' }}>
                This workload contains {workload.resource_count} AWS resource{workload.resource_count !== 1 ? 's' : ''} for migration.
              </p>
            </div>
          </div>

          {/* Action */}
          <div>
            {effectiveStatus === 'pending' && phaseUnlocked && (
              <button
                onClick={handleExecute}
                disabled={executeMut.isPending}
                className="btn btn-primary btn-lg"
              >
                {executeMut.isPending ? <><span className="spinner" />Starting…</> : 'Execute Workload'}
              </button>
            )}
            {effectiveStatus === 'pending' && !phaseUnlocked && (
              <button disabled className="btn btn-secondary btn-lg" style={{ opacity: 0.5, cursor: 'not-allowed' }}>
                Blocked: Complete Phase {phaseIndex} first
              </button>
            )}
            {effectiveStatus === 'running' && (
              <p className="text-sm" style={{ color: '#2563eb' }}>
                Execution in progress — view the Progress tab.
              </p>
            )}
            {effectiveStatus === 'complete' && (
              <p className="text-sm" style={{ color: '#16a34a' }}>
                Execution complete — view the Results tab.
              </p>
            )}
            {effectiveStatus === 'failed' && (
              <button
                onClick={handleExecute}
                disabled={executeMut.isPending}
                className="btn btn-danger btn-lg"
              >
                {executeMut.isPending ? <><span className="spinner" />Starting…</> : 'Retry Execution'}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Progress tab */}
      {tab === 'progress' && activeSkillRunId && (
        <div className="max-w-2xl">
          <SkillProgressTracker
            skillRunId={activeSkillRunId}
            onComplete={handleComplete}
          />
        </div>
      )}

      {/* Results tab */}
      {tab === 'results' && activeSkillRunId && skillRun && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="panel">
            <div className="panel-header">
              <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Summary</h2>
            </div>
            <div className="panel-body">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
                <div>
                  <p className="field-label">Confidence</p>
                  <p
                    className="text-2xl font-bold mt-1"
                    style={{ color: confidenceColor }}
                  >
                    {confidencePct != null ? `${confidencePct}%` : '—'}
                  </p>
                </div>
                {[
                  { label: 'Total Cost', value: formatCost(skillRun.total_cost_usd), mono: true },
                  { label: 'Iterations', value: String(skillRun.current_iteration ?? '—') },
                  { label: 'Duration', value: durationSecs != null ? formatDuration(durationSecs) : '—', mono: true },
                  { label: 'Status', value: skillRun.status },
                ].map(({ label, value, mono }) => (
                  <div key={label}>
                    <p className="field-label">{label}</p>
                    <p
                      className="text-sm mt-1"
                      style={{ color: '#0f172a', fontFamily: mono ? 'var(--font-mono)' : undefined }}
                    >
                      {value}
                    </p>
                  </div>
                ))}
              </div>
              <div
                className="mt-4 pt-4 grid grid-cols-2 gap-4 text-xs"
                style={{ borderTop: '1px solid var(--color-rule)', color: '#475569' }}
              >
                <div>
                  <span style={{ color: '#64748b' }}>Started: </span>
                  {formatDate(skillRun.started_at)}
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>Completed: </span>
                  {formatDate(skillRun.completed_at)}
                </div>
              </div>
            </div>
          </div>

          {/* Errors */}
          {skillRun.status === 'failed' && skillRun.errors && (
            <div className="panel">
              <div className="panel-header">
                <h2 className="text-sm font-semibold" style={{ color: '#dc2626' }}>Errors</h2>
              </div>
              <div className="panel-body space-y-3">
                <pre
                  className="text-xs rounded-lg p-4 overflow-auto"
                  style={{
                    background: 'var(--color-well)',
                    border: '1px solid rgba(248,113,113,0.2)',
                    color: '#dc2626',
                    fontFamily: 'var(--font-mono)',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {JSON.stringify(skillRun.errors, null, 2)}
                </pre>
                <button
                  onClick={handleExecute}
                  disabled={executeMut.isPending}
                  className="btn btn-danger btn-sm"
                >
                  {executeMut.isPending ? <><span className="spinner" />Starting…</> : 'Retry Execution'}
                </button>
              </div>
            </div>
          )}

          {/* Artifacts */}
          {artifacts && artifacts.length > 0 && (
            <div className="panel">
              <div className="panel-header">
                <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Artifacts</h2>
              </div>
              <div className="panel-body">
                <ArtifactViewer skillRunId={activeSkillRunId} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
