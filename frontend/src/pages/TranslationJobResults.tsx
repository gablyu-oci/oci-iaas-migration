import { useParams, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import {
  useTranslationJob,
  useTranslationJobArtifacts,
  useTranslationJobInteractions,
} from '../api/hooks/useTranslationJobs';
import { formatDate, formatCost, getSkillRunName } from '../lib/utils';
import ArtifactViewer from '../components/ArtifactViewer';
import DependencyGraph from '../components/DependencyGraph';
import client from '../api/client';

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

type Tab = 'summary' | 'log';

function statusBadge(status: string) {
  const map: Record<string, string> = {
    complete: 'badge badge-success',
    running: 'badge badge-running',
    failed: 'badge badge-error',
    queued: 'badge badge-neutral',
  };
  return map[status] || 'badge badge-neutral';
}

const DECISION_COLORS: Record<string, string> = {
  APPROVED: '#16a34a',
  APPROVED_WITH_NOTES: '#d97706',
  NEEDS_FIXES: '#dc2626',
};

export default function TranslationJobResults() {
  const { id } = useParams<{ id: string }>();
  const { data: run, isLoading, isError } = useTranslationJob(id || '');
  const { data: artifacts } = useTranslationJobArtifacts(id || '');
  const { data: interactions } = useTranslationJobInteractions(id || '');
  const [graphData, setGraphData] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('summary');

  useEffect(() => {
    if (run?.skill_type === 'dependency_discovery' && artifacts?.length) {
      const depArtifact = artifacts.find(
        (a) => a.file_type === 'dependency_json' || a.file_name.includes('dependency')
      );
      if (depArtifact) {
        client
          .get(`/api/artifacts/${depArtifact.id}/download`, { responseType: 'text' })
          .then((resp) => setGraphData(resp.data))
          .catch(() => {});
      }
    }
  }, [run?.skill_type, artifacts]);

  if (!id) return <div className="empty-state"><p>No translation job ID provided.</p></div>;
  if (isLoading) return (
    <div className="flex justify-center py-16">
      <span className="spinner spinner-lg" role="status" aria-label="Loading" />
    </div>
  );
  if (isError || !run) return (
    <div className="space-y-4">
      <Link to="/dashboard" className="back-link">
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to Dashboard
      </Link>
      <div className="alert alert-error">Failed to load translation job results.</div>
    </div>
  );

  const confidencePercent = (run.confidence * 100).toFixed(0);
  const confidenceColor =
    run.confidence >= 0.8 ? '#16a34a' : run.confidence >= 0.5 ? '#d97706' : '#dc2626';

  const durationSecs =
    run.started_at && run.completed_at
      ? (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000
      : null;

  const iterationCount =
    (run.output as Record<string, unknown> | null)?.iterations as number | undefined
    ?? run.current_iteration;

  const TABS: { key: Tab; label: string; count?: number }[] = [
    { key: 'summary', label: 'Summary' },
    { key: 'log', label: 'Agent Log', count: interactions?.length },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/translation-jobs" className="back-link">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Translation Jobs
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="page-title">Translation Job Results</h1>
            <span className={statusBadge(run.status)}>
              <span className="badge-dot" />
              {run.status}
            </span>
          </div>
          <p className="page-subtitle">
            {getSkillRunName(run.skill_type, run.resource_names, run.resource_name)}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`tab-btn ${tab === t.key ? 'active' : ''}`}
          >
            {t.label}
            {t.count != null && <span className="tab-count">{t.count}</span>}
          </button>
        ))}
      </div>

      {/* Summary */}
      {tab === 'summary' && (
        <div className="space-y-4 animate-fade-in">
          <div className="panel">
            <div className="panel-header">
              <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Summary</h2>
            </div>
            <div className="panel-body space-y-5">
              {/* Resource(s) */}
              <div>
                <p className="field-label mb-1.5">
                  {run.resource_names && run.resource_names.length > 1
                    ? `Resources (${run.resource_names.length})`
                    : 'Resource'}
                </p>
                {run.resource_names && run.resource_names.length > 1 ? (
                  <ul className="space-y-0.5">
                    {run.resource_names.map((n, i) => (
                      <li key={i} className="text-sm" style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}>{n || '—'}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm" style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}>
                    {run.resource_name || '—'}
                  </p>
                )}
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {[
                  { label: 'Skill Type', value: run.skill_type, mono: true },
                  { label: 'Confidence', value: <span style={{ color: confidenceColor, fontSize: '1.375rem', fontWeight: 700 }}>{confidencePercent}%</span>, mono: false },
                  { label: 'Total Cost', value: formatCost(run.total_cost_usd), mono: true },
                  { label: 'Iterations', value: iterationCount ?? '—', mono: false },
                  { label: 'Duration', value: durationSecs != null ? formatDuration(durationSecs) : '—', mono: false },
                ].map(({ label, value, mono }) => (
                  <div
                    key={label}
                    className="rounded-lg p-3"
                    style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}
                  >
                    <p className="field-label">{label}</p>
                    <p className="text-sm mt-1" style={{ color: 'var(--color-text-bright)', fontFamily: mono ? 'var(--font-mono)' : undefined }}>
                      {value}
                    </p>
                  </div>
                ))}
              </div>

              {/* Dates */}
              <div
                className="grid grid-cols-2 gap-4 pt-4 text-xs"
                style={{ borderTop: '1px solid var(--color-rule)', color: 'var(--color-text-dim)' }}
              >
                <div><span>Started: </span><span style={{ color: 'var(--color-text-dim)' }}>{formatDate(run.started_at)}</span></div>
                <div><span>Completed: </span><span style={{ color: 'var(--color-text-dim)' }}>{formatDate(run.completed_at)}</span></div>
              </div>
            </div>
          </div>

          {run.status === 'failed' && run.errors && (
            <div className="alert alert-error">
              <p className="font-semibold mb-2">Errors</p>
              <pre className="text-xs whitespace-pre-wrap" style={{ fontFamily: 'var(--font-mono)' }}>
                {JSON.stringify(run.errors, null, 2)}
              </pre>
            </div>
          )}

          {run.skill_type === 'dependency_discovery' && graphData && (
            <div className="panel">
              <div className="panel-header">
                <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Dependency Graph</h2>
              </div>
              <div className="panel-body">
                <DependencyGraph data={graphData} />
              </div>
            </div>
          )}

          {artifacts?.length ? (
            <div className="panel">
              <div className="panel-body">
                <ArtifactViewer skillRunId={id} />
              </div>
            </div>
          ) : null}
        </div>
      )}

      {/* Agent Log */}
      {tab === 'log' && (
        <div className="panel animate-fade-in">
          {!interactions?.length ? (
            <div className="empty-state">
              <p>No agent interactions recorded.</p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="dt" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Model</th>
                    <th>Iter</th>
                    <th>Decision</th>
                    <th className="text-right">Conf</th>
                    <th className="text-right">In</th>
                    <th className="text-right">Out</th>
                    <th className="text-right">Cost</th>
                    <th className="text-right">Dur</th>
                    <th className="text-right">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {interactions.map((ix) => (
                    <tr key={ix.id}>
                      <td style={{ color: 'var(--color-text-dim)' }}>{ix.agent_type ?? '—'}</td>
                      <td style={{ color: 'var(--color-text-dim)' }}>{ix.model ?? '—'}</td>
                      <td style={{ color: 'var(--color-text-dim)', textAlign: 'center' }}>{ix.iteration ?? '—'}</td>
                      <td style={{ color: ix.decision ? (DECISION_COLORS[ix.decision] ?? '#475569') : '#475569', fontWeight: 600 }}>
                        {ix.decision ?? '—'}
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--color-text-dim)' }}>
                        {ix.confidence != null ? `${Math.round(ix.confidence * 100)}%` : '—'}
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--color-text-dim)' }}>
                        {ix.tokens_input?.toLocaleString() ?? '—'}
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--color-text-dim)' }}>
                        {ix.tokens_output?.toLocaleString() ?? '—'}
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--color-text-dim)' }}>
                        {ix.cost_usd != null ? `$${ix.cost_usd.toFixed(4)}` : '—'}
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--color-rail)' }}>
                        {ix.duration_seconds != null ? `${ix.duration_seconds.toFixed(1)}s` : '—'}
                      </td>
                      <td style={{ textAlign: 'right', color: 'var(--color-rail)' }}>
                        {new Date(ix.created_at).toLocaleTimeString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
