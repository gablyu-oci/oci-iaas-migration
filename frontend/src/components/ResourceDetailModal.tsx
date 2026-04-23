import { useState } from 'react';
import { Link } from 'react-router-dom';
import ResourceDetailPanel from './ResourceDetailPanel';
import { useResourceTranslationJobs, type TranslationJob } from '../api/hooks/useTranslationJobs';
import { formatDate } from '../lib/utils';

// ─── Types & helpers ──────────────────────────────────────────────────────

export interface ResourceDetailModalResource {
  id: string;
  name?: string | null;
  aws_type?: string | null;
  aws_arn?: string | null;
  status?: string | null;
  raw_config?: Record<string, unknown> | null;
}

function jobStatusBadge(status: string): string {
  const map: Record<string, string> = {
    queued:   'badge badge-neutral',
    running:  'badge badge-running',
    complete: 'badge badge-success',
    failed:   'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

// ─── Translation jobs panel (was inline in Resources.tsx) ────────────────

function ResourceSkillRunsPanel({ resourceId }: { resourceId: string }) {
  const { data: runs, isLoading } = useResourceTranslationJobs(resourceId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => <div key={i} className="skel h-10" />)}
      </div>
    );
  }
  if (!runs || runs.length === 0) {
    return <div className="empty-state"><p>No translation jobs for this resource yet.</p></div>;
  }
  return (
    <div className="space-y-2">
      {runs.map((run: TranslationJob) => (
        <div
          key={run.id}
          className="flex items-center justify-between p-3 rounded-lg text-sm"
          style={{ background: 'var(--color-well)', border: '1px solid var(--color-fence)' }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <span className={jobStatusBadge(run.status)}>
              <span className="badge-dot" />
              {run.status}
            </span>
            <span className="text-xs truncate" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>
              {run.skill_type}
            </span>
            {run.status === 'complete' && (
              <span className="text-xs" style={{ color: 'var(--color-rail)' }}>
                {Math.round(run.confidence * 100)}%
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 flex-shrink-0 ml-3">
            <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>{formatDate(run.created_at)}</span>
            <Link
              to={run.status === 'complete' ? `/translation-jobs/${run.id}/results` : `/translation-jobs/${run.id}`}
              className="btn btn-ghost btn-sm"
            >
              {run.status === 'complete' ? 'Results' : 'View'} →
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main modal ──────────────────────────────────────────────────────────

export default function ResourceDetailModal({
  resource,
  onClose,
}: {
  resource: ResourceDetailModalResource;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<'details' | 'config' | 'runs'>('details');

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Resource Details"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal modal-lg" style={{ maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
        <div className="modal-header">
          <div>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
              {resource.name || 'Unnamed Resource'}
            </h3>
            <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>
              {resource.aws_type || ''}
            </p>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm"
            aria-label="Close modal"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="tabs px-4">
          {(['details', 'config', 'runs'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`tab-btn ${tab === t ? 'active' : ''}`}
            >
              {t === 'details' ? 'Details' : t === 'config' ? 'Raw Config' : 'Translation Jobs'}
            </button>
          ))}
        </div>

        <div className="modal-body overflow-y-auto flex-1 space-y-4">
          {tab === 'details' && (
            <ResourceDetailPanel resourceId={resource.id} />
          )}
          {tab === 'config' && (
            <>
              <div className="grid grid-cols-2 gap-4 text-xs">
                {[
                  { label: 'Name', value: resource.name || '—' },
                  { label: 'Type', value: resource.aws_type || '—', mono: true },
                  { label: 'ARN', value: resource.aws_arn || '—', mono: true, breakAll: true },
                  { label: 'Status', value: resource.status || '—' },
                ].map(({ label, value, mono, breakAll }) => (
                  <div key={label}>
                    <p className="field-label">{label}</p>
                    <p
                      className="mt-1 text-xs"
                      style={{
                        color: 'var(--color-text-bright)',
                        fontFamily: mono ? 'var(--font-mono)' : undefined,
                        wordBreak: breakAll ? 'break-all' : undefined,
                      }}
                    >
                      {value}
                    </p>
                  </div>
                ))}
              </div>
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="field-label">Raw Configuration</p>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => navigator.clipboard.writeText(JSON.stringify(resource.raw_config, null, 2))}
                      className="btn btn-secondary btn-sm"
                    >
                      Copy
                    </button>
                    <button
                      onClick={() => {
                        const blob = new Blob([JSON.stringify(resource.raw_config, null, 2)], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `${resource.name || 'resource'}.json`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className="btn btn-primary btn-sm"
                    >
                      Download
                    </button>
                  </div>
                </div>
                <pre
                  className="rounded-lg p-4 text-xs overflow-auto"
                  style={{
                    background: 'var(--color-well)',
                    border: '1px solid var(--color-fence)',
                    color: 'var(--color-text-dim)',
                    fontFamily: 'var(--font-mono)',
                    maxHeight: '20rem',
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {JSON.stringify(resource.raw_config, null, 2)}
                </pre>
              </div>
            </>
          )}
          {tab === 'runs' && (
            <ResourceSkillRunsPanel resourceId={resource.id} />
          )}
        </div>
      </div>
    </div>
  );
}
