import { useEffect, useRef } from 'react';
import { useTranslationJobStream, useTranslationJob } from '../api/hooks/useTranslationJobs';
import type { InteractionEvent } from '../api/hooks/useTranslationJobs';

interface Props {
  skillRunId: string;
  onComplete?: () => void;
}

const PHASES = [
  { key: 'queued',       label: 'Queued',      icon: '○' },
  { key: 'gap_analysis', label: 'Gap Analysis', icon: '◎' },
  { key: 'enhancement',  label: 'Enhancement',  icon: '◈' },
  { key: 'review',       label: 'Review',       icon: '◉' },
  { key: 'fix',          label: 'Fix',          icon: '◐' },
  { key: 'complete',     label: 'Complete',     icon: '●' },
];

const PHASE_ORDER = PHASES.map((p) => p.key);

function phaseIndex(phase: string | null | undefined): number {
  if (!phase) return 0;
  const idx = PHASE_ORDER.indexOf(phase);
  return idx === -1 ? 0 : idx;
}

function formatTime(secs: number): string {
  if (secs < 60) return `${Math.floor(secs)}s`;
  return `${Math.floor(secs / 60)}m ${Math.floor(secs % 60)}s`;
}

const SKILL_LABELS: Record<string, string> = {
  cfn_terraform: 'CloudFormation → Terraform',
  iam_translation: 'IAM Policy Translation',
  dependency_discovery: 'Dependency Discovery',
  network_translation: 'Network Translation',
  ec2_translation: 'EC2 Translation',
  database_translation: 'Database Translation',
  loadbalancer_translation: 'Load Balancer Translation',
  migration_synthesis: 'Migration Synthesis',
};

const DECISION_COLORS: Record<string, string> = {
  APPROVED: '#16a34a',
  NEEDS_FIXES: '#d97706',
  REJECTED: '#dc2626',
};

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued:   'badge badge-neutral',
    running:  'badge badge-running',
    complete: 'badge badge-success',
    failed:   'badge badge-error',
  };
  return (
    <span className={map[status] ?? 'badge badge-neutral'}>
      <span className="badge-dot" />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function InteractionRow({ ix }: { ix: InteractionEvent }) {
  const totalTokens = (ix.tokens_input ?? 0) + (ix.tokens_output ?? 0);
  return (
    <tr>
      <td style={{ padding: '0.25rem 0.75rem', color: '#475569', whiteSpace: 'nowrap' }}>
        {ix.agent_type ?? '—'}
      </td>
      <td style={{ padding: '0.25rem 0.75rem', color: '#64748b', textAlign: 'center' }}>
        {ix.iteration ?? '—'}
      </td>
      <td style={{
        padding: '0.25rem 0.75rem',
        color: ix.decision ? (DECISION_COLORS[ix.decision] ?? '#475569') : '#475569',
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}>
        {ix.decision ?? '—'}
      </td>
      <td style={{ padding: '0.25rem 0.75rem', textAlign: 'right', color: '#64748b' }}>
        {ix.confidence != null ? `${Math.round(ix.confidence * 100)}%` : '—'}
      </td>
      <td style={{ padding: '0.25rem 0.75rem', textAlign: 'right', color: '#475569' }}>
        {totalTokens > 0 ? totalTokens.toLocaleString() : '—'}
      </td>
      <td style={{ padding: '0.25rem 0.75rem', textAlign: 'right', color: '#475569' }}>
        {ix.cost_usd != null ? `$${ix.cost_usd.toFixed(4)}` : '—'}
      </td>
      <td style={{ padding: '0.25rem 0.75rem', textAlign: 'right', color: '#94a3b8' }}>
        {ix.duration_seconds != null ? `${ix.duration_seconds.toFixed(1)}s` : '—'}
      </td>
    </tr>
  );
}

export default function SkillProgressTracker({ skillRunId, onComplete }: Props) {
  const { data: run } = useTranslationJob(skillRunId);
  const { event, interactions } = useTranslationJobStream(skillRunId);
  const completeFired = useRef(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  const phase     = event?.phase      ?? run?.current_phase      ?? 'queued';
  const iteration = event?.iteration  ?? run?.current_iteration  ?? 0;
  const confidence = event?.confidence ?? run?.confidence ?? 0;
  const status    = event?.status     ?? run?.status     ?? 'queued';
  const elapsed   = event?.elapsed_secs ?? 0;

  const maxIterations =
    (run?.config as Record<string, number> | undefined)?.max_iterations ?? 3;

  const currentPhaseIdx = status === 'complete'
    ? PHASE_ORDER.indexOf('complete')
    : status === 'failed'
    ? -1
    : phaseIndex(phase);

  useEffect(() => {
    if (status === 'complete' && onComplete && !completeFired.current) {
      completeFired.current = true;
      const timer = setTimeout(onComplete, 1200);
      return () => clearTimeout(timer);
    }
  }, [status, onComplete]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [interactions.length]);

  const confidencePct = Math.round(confidence * 100);
  const isFailed = status === 'failed';
  const isComplete = status === 'complete';
  const isRunning = status === 'running';

  // Confidence ring
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const strokeDash = (confidencePct / 100) * circumference;
  const ringColor = isFailed ? '#dc2626'
    : confidencePct >= 85 ? '#16a34a'
    : confidencePct >= 65 ? '#d97706'
    : '#2563eb';

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="panel panel-body">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="field-label">
              {SKILL_LABELS[run?.skill_type ?? ''] ?? run?.skill_type ?? 'Skill Run'}
            </p>
            <p
              className="text-xs truncate max-w-xs mt-1"
              style={{ color: '#475569', fontFamily: 'var(--font-mono)' }}
            >
              {skillRunId}
            </p>
          </div>
          <StatusBadge status={status} />
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4">
        {/* Confidence ring */}
        <div
          className="panel flex flex-col items-center gap-2 p-5"
        >
          <p className="field-label">Confidence</p>
          <div className="relative w-20 h-20">
            <svg className="w-20 h-20" style={{ transform: 'rotate(-90deg)' }} viewBox="0 0 88 88">
              <circle cx="44" cy="44" r={radius} fill="none" stroke="var(--color-well)" strokeWidth="8" />
              <circle
                cx="44" cy="44" r={radius}
                fill="none"
                stroke={ringColor}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${strokeDash} ${circumference}`}
                style={{ transition: 'stroke-dasharray 0.7s ease, stroke 0.3s ease' }}
              />
            </svg>
            <span
              className="absolute inset-0 flex items-center justify-center text-lg font-bold"
              style={{ color: '#0f172a' }}
            >
              {confidencePct}%
            </span>
          </div>
          <p className="text-xs" style={{ color: '#64748b' }}>
            {confidencePct >= 85 ? 'Approved' : confidencePct >= 65 ? 'With notes' : 'Needs fixes'}
          </p>
        </div>

        {/* Iteration */}
        <div className="panel flex flex-col items-center justify-center gap-1 p-5">
          <p className="field-label">Iteration</p>
          <p className="text-3xl font-bold" style={{ color: '#0f172a' }}>
            {iteration}
            <span className="text-xl font-normal" style={{ color: '#475569' }}>/{maxIterations}</span>
          </p>
          <p className="text-xs" style={{ color: '#64748b' }}>enhancement loops</p>
        </div>

        {/* Elapsed */}
        <div className="panel flex flex-col items-center justify-center gap-1 p-5">
          <p className="field-label">Elapsed</p>
          <p
            className="text-3xl font-bold"
            style={{ color: '#0f172a', fontFamily: 'var(--font-mono)' }}
          >
            {formatTime(elapsed)}
          </p>
          <p className="text-xs" style={{ color: '#64748b' }}>
            {isRunning ? 'in progress' : isComplete ? 'total' : '—'}
          </p>
        </div>
      </div>

      {/* Phase pipeline */}
      <div className="panel">
        <div className="panel-header">
          <p className="field-label mb-0">Pipeline</p>
        </div>
        <div className="panel-body">
          <div className="flex items-center">
            {PHASES.filter((p) => p.key !== 'queued').map((p, i, arr) => {
              const idx = PHASE_ORDER.indexOf(p.key);
              const done = currentPhaseIdx > idx || isComplete;
              const active = currentPhaseIdx === idx && !isFailed && !isComplete;
              const isLast = i === arr.length - 1;

              const dotColor = done ? '#16a34a'
                : active ? 'var(--color-ember)'
                : isFailed && active ? '#dc2626'
                : '#94a3b8';

              return (
                <div key={p.key} className="flex items-center flex-1 min-w-0">
                  <div className="flex flex-col items-center flex-shrink-0">
                    <div
                      className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold"
                      style={{
                        background: done
                          ? 'rgba(74,222,128,0.12)'
                          : active
                          ? 'rgba(249,115,22,0.12)'
                          : 'var(--color-well)',
                        border: `2px solid ${dotColor}`,
                        color: dotColor,
                        boxShadow: active ? '0 0 10px rgba(249,115,22,0.2)' : undefined,
                        transition: 'all 0.3s ease',
                      }}
                    >
                      {active && isRunning ? (
                        <span className="spinner" style={{ borderTopColor: 'var(--color-ember)', borderColor: 'rgba(249,115,22,0.2)', width: '1rem', height: '1rem' }} />
                      ) : done ? (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <span>{p.icon}</span>
                      )}
                    </div>
                    <span
                      className="text-xs mt-1.5 text-center leading-tight"
                      style={{ color: dotColor, maxWidth: '4.5rem' }}
                    >
                      {p.label}
                    </span>
                  </div>
                  {!isLast && (
                    <div
                      className="flex-1 h-px mx-2 mb-5"
                      style={{ background: done ? '#16a34a' : 'var(--color-rule)', transition: 'background 0.5s ease' }}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Confidence guide */}
      {isRunning && (
        <div
          className="rounded-lg px-4 py-3 flex gap-6 justify-center text-xs"
          style={{
            background: 'var(--color-well)',
            border: '1px solid var(--color-rule)',
            color: '#64748b',
          }}
        >
          {[
            { color: '#16a34a', label: '≥ 85% Approved' },
            { color: '#d97706', label: '65–85% With notes' },
            { color: '#2563eb', label: '< 65% Needs fixes' },
          ].map(({ color, label }) => (
            <span key={label} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
              {label}
            </span>
          ))}
        </div>
      )}

      {/* Agent log */}
      {(interactions.length > 0 || isRunning) && (
        <div className="panel overflow-hidden">
          <div className="panel-header">
            <p className="field-label mb-0">Agent Log</p>
            {isRunning && (
              <span className="flex items-center gap-1.5 text-xs" style={{ color: '#2563eb' }}>
                <span className="badge-dot" style={{ background: '#2563eb', animation: 'pulse-dot 1.4s ease-in-out infinite' }} />
                Live
              </span>
            )}
          </div>
          <div
            style={{
              maxHeight: '16rem',
              overflowY: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.75rem',
            }}
          >
            {interactions.length === 0 ? (
              <div className="px-5 py-4" style={{ color: '#475569', fontStyle: 'italic' }}>
                Waiting for agent activity…
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead style={{ position: 'sticky', top: 0, background: 'var(--color-surface)', borderBottom: '1px solid var(--color-rule)' }}>
                  <tr>
                    {['Agent', 'Iter', 'Decision', 'Conf', 'Tokens', 'Cost', 'Dur'].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: '0.375rem 0.75rem',
                          textAlign: h === 'Agent' || h === 'Iter' || h === 'Decision' ? 'left' : 'right',
                          color: '#475569',
                          fontWeight: 600,
                          fontSize: '0.6875rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.05em',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {interactions.map((ix) => (
                    <InteractionRow key={ix.id} ix={ix} />
                  ))}
                </tbody>
              </table>
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}
