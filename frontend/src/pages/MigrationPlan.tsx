import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  usePlan, usePlanStatus, useDeletePlan,
  useExecuteWorkload, useLatestSynthesis,
} from '../api/plans';
import type { PlanPhase, Workload } from '../api/plans';
import {
  useTranslationJobArtifacts,
  getArtifactDownloadUrl,
  downloadArtifactsAsZip,
} from '../api/hooks/useTranslationJobs';
import { formatDate } from '../lib/utils';

// ── Status Badge ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending:  'badge badge-neutral',
    draft:    'badge badge-neutral',
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

// ── Download Dropdown ──────────────────────────────────────────────────────────

function DownloadDropdown({ synthesisJobId }: { synthesisJobId: string }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [zipping, setZipping] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data: artifacts, isLoading } = useTranslationJobArtifacts(synthesisJobId);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const tfFiles = artifacts?.filter(a => a.file_name.endsWith('.tf')) ?? [];
  const mdFiles = artifacts?.filter(a =>
    a.file_name.endsWith('.md') && a.file_name !== 'synthesis-summary.md'
  ) ?? [];
  const allFiles = [...tfFiles, ...mdFiles];

  const toggle = (id: string) =>
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const toggleSection = (ids: string[]) => {
    const allChecked = ids.every(id => selected.has(id));
    setSelected(prev => {
      const n = new Set(prev);
      allChecked ? ids.forEach(id => n.delete(id)) : ids.forEach(id => n.add(id));
      return n;
    });
  };

  const handleZip = async () => {
    if (selected.size === 0) return;
    setZipping(true);
    try { await downloadArtifactsAsZip([...selected]); }
    finally { setZipping(false); }
  };

  const FileRow = ({ art, iconColor, mono }: { art: typeof allFiles[0]; iconColor: string; mono?: boolean }) => (
    <div
      className="flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors"
      style={{ background: selected.has(art.id) ? 'rgba(249,115,22,0.06)' : 'transparent' }}
      onClick={() => toggle(art.id)}
      onMouseEnter={e => { if (!selected.has(art.id)) e.currentTarget.style.background = 'var(--color-well)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = selected.has(art.id) ? 'rgba(249,115,22,0.06)' : 'transparent'; }}
    >
      <input type="checkbox" className="cb" checked={selected.has(art.id)}
        onChange={() => toggle(art.id)} onClick={e => e.stopPropagation()} />
      <span style={{ color: iconColor, display: 'flex', flexShrink: 0 }}>
        {mono ? (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
          </svg>
        ) : (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        )}
      </span>
      <span className="text-sm flex-1 truncate"
        style={{ color: '#0f172a', fontFamily: mono ? 'var(--font-mono)' : undefined }}>
        {art.file_name}
      </span>
      <a href={getArtifactDownloadUrl(art.id)} download={art.file_name}
        className="flex-shrink-0 p-1 rounded" style={{ color: '#475569' }}
        title="Download this file" onClick={e => e.stopPropagation()}
        onMouseEnter={e => (e.currentTarget.style.color = '#94a3b8')}
        onMouseLeave={e => (e.currentTarget.style.color = '#475569')}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </a>
    </div>
  );

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen(o => !o)} className="btn btn-secondary flex items-center gap-2">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
        Download Output Files
        <svg className="w-3.5 h-3.5 transition-transform duration-200"
          style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}
          fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 z-50 rounded-lg overflow-hidden animate-fade-in"
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-fence)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.12), 0 0 0 1px rgba(203,213,225,0.8)',
            minWidth: '320px',
          }}
        >
          {isLoading ? (
            <div className="flex items-center gap-2 p-4 text-sm" style={{ color: '#64748b' }}>
              <span className="spinner" /> Loading files…
            </div>
          ) : allFiles.length === 0 ? (
            <div className="p-4 text-sm" style={{ color: '#64748b' }}>No output files available.</div>
          ) : (
            <>
              {tfFiles.length > 0 && (
                <div>
                  <div className="flex items-center justify-between px-4 pt-3 pb-1.5">
                    <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#475569' }}>Terraform Files</p>
                    <button className="text-xs" style={{ color: '#475569', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                      onClick={() => toggleSection(tfFiles.map(a => a.id))}
                      onMouseEnter={e => (e.currentTarget.style.color = '#94a3b8')}
                      onMouseLeave={e => (e.currentTarget.style.color = '#475569')}
                    >
                      {tfFiles.every(a => selected.has(a.id)) ? 'Deselect all' : 'Select all'}
                    </button>
                  </div>
                  {tfFiles.map(art => <FileRow key={art.id} art={art} iconColor="var(--color-ember)" mono />)}
                </div>
              )}

              {mdFiles.length > 0 && (
                <div style={{ borderTop: tfFiles.length > 0 ? '1px solid var(--color-rule)' : undefined }}>
                  <div className="flex items-center justify-between px-4 pt-3 pb-1.5">
                    <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#475569' }}>Guides &amp; Runbooks</p>
                    <button className="text-xs" style={{ color: '#475569', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                      onClick={() => toggleSection(mdFiles.map(a => a.id))}
                      onMouseEnter={e => (e.currentTarget.style.color = '#94a3b8')}
                      onMouseLeave={e => (e.currentTarget.style.color = '#475569')}
                    >
                      {mdFiles.every(a => selected.has(a.id)) ? 'Deselect all' : 'Select all'}
                    </button>
                  </div>
                  {mdFiles.map(art => <FileRow key={art.id} art={art} iconColor="#60a5fa" />)}
                </div>
              )}

              {/* Footer */}
              <div className="flex items-center justify-between px-4 py-3"
                style={{ borderTop: '1px solid var(--color-rule)', background: 'var(--color-well)' }}>
                <span className="text-xs" style={{ color: '#64748b' }}>
                  {selected.size > 0 ? `${selected.size} of ${allFiles.length} selected` : 'Select files to download'}
                </span>
                <div className="flex items-center gap-2">
                  <button className="btn btn-ghost btn-sm text-xs"
                    onClick={() => selected.size === allFiles.length
                      ? setSelected(new Set())
                      : setSelected(new Set(allFiles.map(a => a.id)))}>
                    {selected.size === allFiles.length ? 'Deselect all' : 'Select all'}
                  </button>
                  <button className="btn btn-primary btn-sm" disabled={selected.size === 0 || zipping} onClick={handleZip}>
                    {zipping
                      ? <><span className="spinner" style={{ width: 12, height: 12 }} /> Zipping…</>
                      : `Download ZIP${selected.size > 0 ? ` (${selected.size})` : ''}`}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Phase Timeline ─────────────────────────────────────────────────────────────

function PhaseTimeline({ phases }: { phases: PlanPhase[] }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <p className="field-label mb-0">Phase Timeline</p>
      </div>
      <div className="panel-body">
        <div className="flex items-center">
          {phases.map((phase, i) => {
            const done    = phase.status === 'complete';
            const running = phase.status === 'running';
            const failed  = phase.status === 'failed';
            const isLast  = i === phases.length - 1;
            const prevComplete = i === 0 || phases[i - 1].status === 'complete';
            const locked  = !prevComplete && phase.status === 'pending';

            const dotColor = done    ? '#16a34a'
              : running  ? 'var(--color-ember)'
              : failed   ? '#dc2626'
              : locked   ? '#1e2d45'
              : '#334155';

            return (
              <div key={phase.id} className="flex items-center flex-1 min-w-0">
                <div className="flex flex-col items-center flex-shrink-0">
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-300"
                    style={{
                      background: done    ? 'rgba(74,222,128,0.12)'
                        : running ? 'rgba(249,115,22,0.12)'
                        : failed  ? 'rgba(248,113,113,0.12)'
                        : 'var(--color-well)',
                      border: `2px solid ${dotColor}`,
                      color: dotColor,
                      boxShadow: running ? '0 0 12px rgba(249,115,22,0.25)' : undefined,
                    }}
                  >
                    {done ? (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : running ? (
                      <span className="spinner" style={{ borderTopColor: 'var(--color-ember)', borderColor: 'rgba(249,115,22,0.2)' }} />
                    ) : failed ? (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    ) : locked ? (
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                    ) : (
                      <span style={{ fontSize: '0.75rem' }}>{phase.order_index}</span>
                    )}
                  </div>
                  <span
                    className="text-xs mt-1.5 text-center leading-tight max-w-[72px] truncate"
                    style={{ color: dotColor }}
                  >
                    {phase.name}
                  </span>
                </div>
                {!isLast && (
                  <div
                    className="flex-1 h-px mx-2 mb-5"
                    style={{ background: done ? '#16a34a' : 'var(--color-rule)' }}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Skill metadata ─────────────────────────────────────────────────────────────

const SKILL_LABEL: Record<string, string> = {
  network_translation:      'Network',
  database_translation:     'Database',
  ec2_translation:          'Compute',
  storage_translation:      'Storage',
  loadbalancer_translation: 'Load Balancer',
  cfn_terraform:            'CloudFormation',
  iam_translation:          'IAM',
  dependency_discovery:     'Dependencies',
};

const SKILL_BADGE_CLASS: Record<string, string> = {
  network_translation:      'badge badge-info',
  database_translation:     'badge badge-warning',
  ec2_translation:          'badge badge-neutral',
  storage_translation:      'badge badge-success',
  loadbalancer_translation: 'badge badge-running',
  cfn_terraform:            'badge badge-accent',
  iam_translation:          'badge badge-error',
};

// ── Workload Checklist Row ─────────────────────────────────────────────────────

function WorkloadRow({
  workload,
  index,
  phaseUnlocked,
  onExecute,
  executing,
  isLast,
}: {
  workload: Workload;
  index: number;
  phaseUnlocked: boolean;
  onExecute: (id: string) => void;
  executing: boolean;
  isLast: boolean;
}) {
  const isDone    = workload.status === 'complete';
  const isFailed  = workload.status === 'failed';
  const isRunning = workload.status === 'running';

  const indicatorColor = isDone    ? '#16a34a'
    : isFailed  ? '#dc2626'
    : isRunning ? 'var(--color-ember)'
    : '#334155';

  return (
    <div
      className="flex items-start gap-4 px-5 py-4"
      style={{ borderBottom: isLast ? 'none' : '1px solid var(--color-rule)' }}
    >
      {/* Step circle */}
      <div className="flex-shrink-0 pt-0.5">
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
          style={{
            background: isDone    ? 'rgba(74,222,128,0.1)'
              : isFailed  ? 'rgba(248,113,113,0.1)'
              : isRunning ? 'rgba(249,115,22,0.1)'
              : 'var(--color-well)',
            border: `1.5px solid ${indicatorColor}`,
            color: indicatorColor,
          }}
        >
          {isDone ? (
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          ) : isFailed ? (
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : isRunning ? (
            <span
              className="spinner"
              style={{
                width: '13px', height: '13px',
                borderTopColor: 'var(--color-ember)',
                borderColor: 'rgba(249,115,22,0.2)',
              }}
            />
          ) : (
            String(index + 1)
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Link
                to={`/workloads/${workload.id}`}
                className="text-sm font-semibold hover:opacity-75 transition-opacity"
                style={{
                  color: isDone ? '#15803d' : isFailed ? '#b91c1c' : '#0f172a',
                  textDecoration: 'none',
                }}
              >
                {workload.name}
              </Link>
              {workload.skill_type && (
                <span
                  className={SKILL_BADGE_CLASS[workload.skill_type] ?? 'badge badge-neutral'}
                  style={{ fontSize: '0.65rem', padding: '1px 6px' }}
                >
                  {SKILL_LABEL[workload.skill_type] ?? workload.skill_type}
                </span>
              )}
            </div>
            {workload.description && (
              <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>{workload.description}</p>
            )}
            <p className="text-xs mt-0.5" style={{ color: '#475569' }}>
              {workload.resource_count} resource{workload.resource_count !== 1 ? 's' : ''}
            </p>
          </div>
          <StatusBadge status={workload.status} />
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-2.5">
          {workload.status === 'pending' && phaseUnlocked && (
            <button
              onClick={() => {
                if (confirm(`Run translation job for "${workload.name}"?`)) onExecute(workload.id);
              }}
              disabled={executing}
              className="btn btn-primary btn-sm"
            >
              {executing ? <><span className="spinner" />Starting…</> : '▶ Run'}
            </button>
          )}
          {workload.status === 'pending' && !phaseUnlocked && (
            <span className="text-xs" style={{ color: '#475569' }}>Previous phase not complete</span>
          )}
          {workload.status === 'running' && workload.translation_job_id && (
            <Link to={`/translation-jobs/${workload.translation_job_id}`} className="btn btn-ghost btn-sm">
              View Progress →
            </Link>
          )}
          {workload.status === 'running' && !workload.translation_job_id && (
            <Link to={`/workloads/${workload.id}`} className="btn btn-ghost btn-sm">View Progress</Link>
          )}
          {workload.status === 'complete' && workload.translation_job_id && (
            <Link
              to={`/translation-jobs/${workload.translation_job_id}/results`}
              className="btn btn-ghost btn-sm"
              style={{ color: '#16a34a' }}
            >
              View Results →
            </Link>
          )}
          {workload.status === 'complete' && !workload.translation_job_id && (
            <Link to={`/workloads/${workload.id}`} className="btn btn-ghost btn-sm" style={{ color: '#16a34a' }}>
              View Results
            </Link>
          )}
          {workload.status === 'failed' && (
            <>
              <button
                onClick={() => onExecute(workload.id)}
                disabled={executing}
                className="btn btn-danger btn-sm"
              >
                Retry
              </button>
              {workload.translation_job_id ? (
                <Link to={`/translation-jobs/${workload.translation_job_id}/results`} className="btn btn-ghost btn-sm">
                  See Error →
                </Link>
              ) : (
                <Link to={`/workloads/${workload.id}`} className="btn btn-ghost btn-sm">Details</Link>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Phase Section ──────────────────────────────────────────────────────────────

function PhaseSection({
  phase,
  isUnlocked,
  onExecute,
  executing,
}: {
  phase: PlanPhase;
  isUnlocked: boolean;
  onExecute: (id: string) => void;
  executing: boolean;
}) {
  const [expanded, setExpanded] = useState(false);

  const completedCount = phase.workloads.filter(w => w.status === 'complete').length;
  const failedWorkloads = phase.workloads.filter(w => w.status === 'failed');
  const total = phase.workloads.length;

  const headerBorderColor =
    phase.status === 'running'  ? 'rgba(249,115,22,0.25)' :
    phase.status === 'complete' ? 'rgba(74,222,128,0.2)'  :
    phase.status === 'failed'   ? 'rgba(248,113,113,0.2)' :
    'var(--color-rule)';

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: 'var(--color-surface)',
        border: `1px solid ${expanded ? headerBorderColor : 'var(--color-rule)'}`,
        boxShadow: 'var(--shadow-card)',
        opacity: !isUnlocked && phase.status === 'pending' ? 0.55 : 1,
        transition: 'border-color 0.2s, opacity 0.2s',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-5 py-4 text-left transition-colors"
        aria-expanded={expanded}
        style={{ cursor: 'pointer', background: 'transparent' }}
        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(0,0,0,0.02)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* Chevron */}
          <svg
            className="w-4 h-4 flex-shrink-0 transition-transform duration-200"
            style={{ color: '#475569', transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>

          <div className="min-w-0">
            <p className="text-sm font-semibold" style={{ color: '#0f172a' }}>
              Phase {phase.order_index}: {phase.name}
            </p>
            {phase.description && (
              <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>{phase.description}</p>
            )}
            {!isUnlocked && phase.status === 'pending' && (
              <p className="text-xs mt-0.5" style={{ color: '#475569' }}>
                Complete Phase {phase.order_index - 1} to unlock
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0 ml-4">
          <span className="text-xs" style={{ color: '#475569' }}>
            {completedCount}/{total} complete
          </span>
          <StatusBadge status={phase.status} />
        </div>
      </button>

      {/* Body */}
      {expanded && (
        <div style={{ borderTop: `1px solid var(--color-rule)`, background: 'rgba(0,0,0,0.015)' }}>
          {/* Workload checklist */}
          {phase.workloads.length === 0 ? (
            <p className="text-xs text-center py-8" style={{ color: '#475569' }}>No workloads in this phase.</p>
          ) : (
            phase.workloads.map((workload, i) => (
              <WorkloadRow
                key={workload.id}
                workload={workload}
                index={i}
                phaseUnlocked={isUnlocked}
                onExecute={onExecute}
                executing={executing}
                isLast={i === phase.workloads.length - 1}
              />
            ))
          )}

          {/* Special Attention */}
          {failedWorkloads.length > 0 && (
            <div
              className="mx-5 mb-5 mt-3 rounded-lg p-4"
              style={{
                background: 'rgba(248,113,113,0.05)',
                border: '1px solid rgba(248,113,113,0.2)',
              }}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  style={{ color: '#dc2626' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span className="text-xs font-semibold" style={{ color: '#dc2626' }}>Special Attention Required</span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: '#94a3b8' }}>
                {failedWorkloads.length === 1
                  ? `"${failedWorkloads[0].name}" failed and needs attention.`
                  : `${failedWorkloads.length} workloads failed: ${failedWorkloads.map(w => `"${w.name}"`).join(', ')}.`}{' '}
                Review the error details and retry the affected workloads before proceeding.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Synthesis Banner ───────────────────────────────────────────────────────────

function SynthesisBanner({
  status, confidence, errors,
}: {
  status: string;
  confidence: number | null;
  errors: Record<string, unknown> | null;
}) {
  if (status === 'running' || status === 'queued') {
    return (
      <div
        className="rounded-lg px-4 py-3 flex items-center gap-3"
        style={{ background: 'rgba(249,115,22,0.06)', border: '1px solid rgba(249,115,22,0.2)' }}
      >
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ background: 'var(--color-ember)', boxShadow: '0 0 8px rgba(249,115,22,0.5)', animation: 'pulse-dot 1.4s ease-in-out infinite' }}
        />
        <span className="text-sm" style={{ color: '#c2410c' }}>
          Migration synthesis in progress — combining all translation outputs into a unified plan…
        </span>
      </div>
    );
  }
  if (status === 'failed') {
    const msg = errors?.error as string | undefined;
    return (
      <div
        className="rounded-lg px-4 py-3 flex items-start gap-3"
        style={{ background: 'rgba(248,113,113,0.06)', border: '1px solid rgba(248,113,113,0.2)' }}
      >
        <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"
          style={{ color: '#dc2626' }}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <span className="text-sm" style={{ color: '#b91c1c' }}>
          Synthesis failed{msg ? `: ${msg}` : '.'}
        </span>
      </div>
    );
  }
  if (status === 'complete') {
    const pct = confidence != null ? Math.round(confidence * 100) : null;
    return (
      <div
        className="rounded-lg px-4 py-3 flex items-center gap-3"
        style={{ background: 'rgba(74,222,128,0.05)', border: '1px solid rgba(74,222,128,0.18)' }}
      >
        <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"
          style={{ color: '#16a34a' }}>
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
        <span className="text-sm" style={{ color: '#15803d' }}>
          Synthesis complete{pct != null ? ` — ${pct}% confidence` : ''}. Output files are ready to download.
        </span>
      </div>
    );
  }
  return null;
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MigrationPlanPage() {
  const { planId } = useParams<{ planId: string }>();
  const navigate = useNavigate();

  const { data: plan, isLoading, isError } = usePlan(planId || '');
  const { data: liveStatus } = usePlanStatus(planId || '');
  const deletePlanMut = useDeletePlan();
  const executeMut = useExecuteWorkload();

  const activePlan = liveStatus ?? plan;

  const { data: synthesisJob } = useLatestSynthesis(activePlan?.migration_id ?? '');
  const synthesisDone = synthesisJob?.status === 'complete';

  if (!planId) return <div className="empty-state"><p>No plan ID provided.</p></div>;

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="spinner spinner-lg" role="status" aria-label="Loading" />
      </div>
    );
  }

  if (isError || !activePlan) {
    return (
      <div className="space-y-4">
        <Link to="/migrations" className="back-link">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Migrations
        </Link>
        <div className="alert alert-error">Failed to load migration plan.</div>
      </div>
    );
  }

  const phases = activePlan.phases;
  const totalResources  = phases.reduce((s, p) => s + p.workloads.reduce((ws, w) => ws + w.resource_count, 0), 0);
  const completedPhases = phases.filter(p => p.status === 'complete').length;
  const completionPct   = phases.length > 0 ? Math.round((completedPhases / phases.length) * 100) : 0;
  const pendingPhases   = phases.filter(p => p.status === 'pending').length;
  const runningPhases   = phases.filter(p => p.status === 'running').length;

  const progressColor =
    activePlan.status === 'complete'               ? '#16a34a' :
    phases.some(p => p.status === 'failed')        ? '#dc2626' :
    phases.some(p => p.status === 'running')       ? 'var(--color-ember)' :
    'var(--color-rail)';

  const isPhaseUnlocked = (i: number) => i === 0 || phases[i - 1].status === 'complete';

  const handleDelete = async () => {
    if (confirm('Delete this plan? All workload progress will be lost.')) {
      await deletePlanMut.mutateAsync(planId);
      navigate(activePlan?.migration_id ? `/migrations/${activePlan.migration_id}` : '/migrations');
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">

      {/* ── Header ── */}
      <div>
        <Link
          to={activePlan?.migration_id ? `/migrations/${activePlan.migration_id}` : '/migrations'}
          className="back-link"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Migration
        </Link>

        <div className="flex items-start justify-between gap-4 mt-1">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="page-title">Migration Plan</h1>
              <StatusBadge status={activePlan.status} />
            </div>
            <p className="page-subtitle">Generated {formatDate(activePlan.generated_at)}</p>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {synthesisDone && synthesisJob ? (
              <DownloadDropdown synthesisJobId={synthesisJob.id} />
            ) : (
              <button
                className="btn btn-secondary flex items-center gap-2"
                disabled
                title="Run synthesis first to generate output files"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download Output Files
              </button>
            )}
            <button onClick={handleDelete} className="btn btn-danger">
              Delete Plan
            </button>
          </div>
        </div>
      </div>

      {/* ── Stats ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          {
            label: 'Total Resources',
            value: totalResources,
            sub: `across ${phases.length} phase${phases.length !== 1 ? 's' : ''}`,
          },
          {
            label: 'Phases',
            value: phases.length,
            sub: `${pendingPhases} pending · ${runningPhases} in progress`,
          },
          {
            label: 'Completion',
            value: `${completionPct}%`,
            sub: `${completedPhases}/${phases.length} phases done`,
            progress: true,
          },
        ].map(({ label, value, sub, progress }) => (
          <div key={label} className="panel panel-body">
            <p className="field-label">{label}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: '#0f172a' }}>{value}</p>
            {progress && (
              <div className="w-full h-1.5 rounded-full mt-2 overflow-hidden" style={{ background: 'var(--color-well)' }}>
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{ width: `${completionPct}%`, background: progressColor }}
                />
              </div>
            )}
            <p className="text-xs mt-1" style={{ color: '#64748b' }}>{sub}</p>
          </div>
        ))}
      </div>

      {/* ── Synthesis Banner ── */}
      {synthesisJob && (
        <SynthesisBanner
          status={synthesisJob.status}
          confidence={synthesisJob.confidence}
          errors={synthesisJob.errors}
        />
      )}

      {/* ── Phase Timeline ── */}
      {phases.length > 0 && <PhaseTimeline phases={phases} />}

      {/* ── Phase Accordion ── */}
      <div className="space-y-3">
        {phases.map((phase, i) => (
          <PhaseSection
            key={phase.id}
            phase={phase}
            isUnlocked={isPhaseUnlocked(i)}
            onExecute={executeMut.mutate}
            executing={executeMut.isPending}
          />
        ))}
      </div>

    </div>
  );
}
