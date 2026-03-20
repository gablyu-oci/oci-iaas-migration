import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useResources } from '../api/hooks/useResources';
import { useTranslationJobs, useDeleteTranslationJob } from '../api/hooks/useTranslationJobs';
import { useCreateMigration, useMigrations } from '../api/hooks/useMigrations';
import { useConnections } from '../api/hooks/useConnections';
import { formatDate, formatCost, getSkillRunName } from '../lib/utils';

function statusBadge(status: string): string {
  const map: Record<string, string> = {
    complete: 'badge badge-success',
    running: 'badge badge-running',
    failed: 'badge badge-error',
    queued: 'badge badge-neutral',
    draft: 'badge badge-neutral',
    planning: 'badge badge-info',
    active: 'badge badge-success',
    created: 'badge badge-neutral',
    extracting: 'badge badge-info',
    extracted: 'badge badge-success',
    ready: 'badge badge-success',
  };
  return map[status] || 'badge badge-neutral';
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: resources, isLoading: loadingResources } = useResources();
  const { data: skillRuns, isLoading: loadingSkillRuns } = useTranslationJobs();
  const { data: migrations, isLoading: loadingMigrations } = useMigrations();
  const { data: connections } = useConnections();
  const createMigration = useCreateMigration();
  const deleteSkillRun = useDeleteTranslationJob();

  const recentRuns = (skillRuns || []).slice(0, 10);

  const [showNewMigrationModal, setShowNewMigrationModal] = useState(false);
  const [newMigrationName, setNewMigrationName] = useState('');
  const [selectedConnectionId, setSelectedConnectionId] = useState('');

  const handleCreateMigration = () => {
    if (!newMigrationName.trim()) return;
    const payload: { name: string; aws_connection_id?: string } = { name: newMigrationName.trim() };
    if (selectedConnectionId) payload.aws_connection_id = selectedConnectionId;
    createMigration.mutate(payload, {
      onSuccess: (newMigration) => {
        setShowNewMigrationModal(false);
        setNewMigrationName('');
        setSelectedConnectionId('');
        navigate(`/migrations/${newMigration.id}`);
      },
    });
  };

  const statCards = [
    {
      label: 'AWS Resources',
      value: resources?.length ?? 0,
      loading: loadingResources,
      link: '/resources',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
        </svg>
      ),
      color: '#60a5fa',
    },
    {
      label: 'Translation Jobs',
      value: skillRuns?.length ?? 0,
      loading: loadingSkillRuns,
      link: '/translation-jobs',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      color: 'var(--color-ember)',
    },
    {
      label: 'Migrations',
      value: migrations?.length ?? 0,
      loading: loadingMigrations,
      link: '/migrations',
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ),
      color: '#4ade80',
    },
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">AWS to OCI migration overview</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/translation-jobs/new" className="btn btn-secondary">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Translation Job
          </Link>
          <button onClick={() => setShowNewMigrationModal(true)} className="btn btn-primary">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Migration
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {statCards.map((card) => (
          <Link
            key={card.label}
            to={card.link}
            className="panel flex items-center gap-4 p-5 hover:border-fence transition-colors duration-150"
            style={{ textDecoration: 'none' }}
          >
            <div
              className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: `${card.color}18`, color: card.color, border: `1px solid ${card.color}22` }}
            >
              {card.icon}
            </div>
            <div>
              <p className="text-xs" style={{ color: '#64748b' }}>{card.label}</p>
              {card.loading ? (
                <div className="skel h-7 w-12 mt-1" />
              ) : (
                <p className="text-2xl font-bold mt-0.5" style={{ color: '#0f172a' }}>{card.value}</p>
              )}
            </div>
          </Link>
        ))}
      </div>

      {/* Migrations */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Migrations</h2>
          <Link to="/migrations" className="text-xs" style={{ color: 'var(--color-ember)' }}>View all →</Link>
        </div>
        {loadingMigrations ? (
          <div className="panel-body space-y-2">
            {[...Array(3)].map((_, i) => <div key={i} className="skel h-10" />)}
          </div>
        ) : !migrations?.length ? (
          <div className="empty-state">
            <p>No migrations yet.</p>
            <button
              onClick={() => setShowNewMigrationModal(true)}
              className="btn btn-secondary btn-sm mt-3"
            >
              Create Migration
            </button>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="dt">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Status</th>
                  <th>Resources</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {migrations.map((m) => (
                  <tr key={m.id}>
                    <td className="td-primary">
                      <Link
                        to={`/migrations/${m.id}`}
                        style={{ color: 'var(--color-ember)', textDecoration: 'none' }}
                        className="hover:opacity-80 transition-opacity"
                      >
                        {m.name}
                      </Link>
                    </td>
                    <td>
                      <span className={statusBadge(m.status)}>
                        <span className="badge-dot" />
                        {m.status}
                      </span>
                    </td>
                    <td>
                      {(m as any).resource_count != null
                        ? `${(m as any).resource_count} resource${(m as any).resource_count !== 1 ? 's' : ''}`
                        : '—'}
                    </td>
                    <td>{formatDate(m.created_at)}</td>
                    <td>
                      <Link
                        to={`/migrations/${m.id}`}
                        className="btn btn-ghost btn-sm"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent Translation Jobs */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Recent Translation Jobs</h2>
          <Link to="/translation-jobs" className="text-xs" style={{ color: 'var(--color-ember)' }}>View all →</Link>
        </div>
        {loadingSkillRuns ? (
          <div className="panel-body space-y-2">
            {[...Array(3)].map((_, i) => <div key={i} className="skel h-10" />)}
          </div>
        ) : recentRuns.length === 0 ? (
          <div className="empty-state">
            <p>No translation jobs yet.</p>
            <Link to="/translation-jobs/new" className="btn btn-secondary btn-sm mt-3">
              Create one
            </Link>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="dt">
              <thead>
                <tr>
                  <th>Run Name</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Cost</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((run) => (
                  <tr key={run.id}>
                    <td className="td-primary">
                      {getSkillRunName(run.skill_type, run.resource_names, run.resource_name)}
                    </td>
                    <td>
                      <span className={statusBadge(run.status)}>
                        <span className="badge-dot" />
                        {run.status}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                      {run.status === 'complete' ? `${(run.confidence * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                      {formatCost(run.total_cost_usd)}
                    </td>
                    <td>{formatDate(run.created_at)}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        {run.status === 'complete' ? (
                          <Link to={`/translation-jobs/${run.id}/results`} className="btn btn-ghost btn-sm">
                            Results →
                          </Link>
                        ) : run.status === 'running' || run.status === 'queued' ? (
                          <Link to={`/translation-jobs/${run.id}`} className="btn btn-ghost btn-sm">
                            Progress →
                          </Link>
                        ) : (
                          <Link to={`/translation-jobs/${run.id}/results`} className="btn btn-ghost btn-sm">
                            Details →
                          </Link>
                        )}
                        <button
                          onClick={() => {
                            if (confirm('Delete this translation job?')) deleteSkillRun.mutate(run.id);
                          }}
                          className="btn btn-danger btn-sm"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* New Migration Modal */}
      {showNewMigrationModal && (
        <div
          className="modal-overlay"
          onClick={(e) => { if (e.target === e.currentTarget) setShowNewMigrationModal(false); }}
          role="dialog"
          aria-modal="true"
          aria-label="Create new migration"
        >
          <div className="modal">
            <div className="modal-header">
              <h3 className="text-sm font-semibold" style={{ color: '#0f172a' }}>New Migration</h3>
              <button onClick={() => setShowNewMigrationModal(false)} className="btn-ghost btn btn-sm" aria-label="Close">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="modal-body space-y-4">
              {createMigration.isError && (
                <div className="alert alert-error" role="alert">
                  {(createMigration.error as any)?.response?.data?.detail || 'Failed to create migration.'}
                </div>
              )}
              <div>
                <label htmlFor="dash-migration-name" className="field-label">Migration Name</label>
                <input
                  id="dash-migration-name"
                  type="text"
                  value={newMigrationName}
                  onChange={(e) => setNewMigrationName(e.target.value)}
                  placeholder="e.g., Production VPC Migration"
                  className="field-input"
                  autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateMigration(); }}
                />
              </div>
              <div>
                <label htmlFor="dash-aws-connection" className="field-label">AWS Connection (optional)</label>
                <select
                  id="dash-aws-connection"
                  value={selectedConnectionId}
                  onChange={(e) => setSelectedConnectionId(e.target.value)}
                  className="field-input field-select"
                >
                  <option value="">No connection</option>
                  {(connections || []).map((conn) => (
                    <option key={conn.id} value={conn.id}>{conn.name} ({conn.region})</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                onClick={() => { setShowNewMigrationModal(false); setNewMigrationName(''); setSelectedConnectionId(''); createMigration.reset(); }}
                className="btn btn-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreateMigration}
                disabled={!newMigrationName.trim() || createMigration.isPending}
                className="btn btn-primary"
              >
                {createMigration.isPending ? <><span className="spinner" />Creating…</> : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
