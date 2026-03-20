import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMigrations, useCreateMigration } from '../api/hooks/useMigrations';
import { useConnections } from '../api/hooks/useConnections';
import { formatDate } from '../lib/utils';

function statusBadge(status: string) {
  const map: Record<string, string> = {
    active: 'badge badge-success',
    complete: 'badge badge-success',
    failed: 'badge badge-error',
    created: 'badge badge-neutral',
    extracting: 'badge badge-info',
    extracted: 'badge badge-success',
    planning: 'badge badge-warning',
  };
  return map[status] || 'badge badge-neutral';
}

export default function Migrations() {
  const navigate = useNavigate();
  const { data: migrations, isLoading } = useMigrations();
  const { data: connections } = useConnections();
  const createMigration = useCreateMigration();

  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [selectedConnectionId, setSelectedConnectionId] = useState('');

  const handleCreate = () => {
    if (!newName.trim()) return;
    const payload: { name: string; aws_connection_id?: string } = { name: newName.trim() };
    if (selectedConnectionId) payload.aws_connection_id = selectedConnectionId;
    createMigration.mutate(payload, {
      onSuccess: (m) => {
        setShowModal(false);
        setNewName('');
        setSelectedConnectionId('');
        navigate(`/migrations/${m.id}`);
      },
    });
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Migrations</h1>
          <p className="page-subtitle">AWS to OCI migration projects</p>
        </div>
        <button onClick={() => setShowModal(true)} className="btn btn-primary">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Migration
        </button>
      </div>

      <div className="panel">
        {isLoading ? (
          <div className="panel-body space-y-2">
            {[...Array(4)].map((_, i) => <div key={i} className="skel h-11" />)}
          </div>
        ) : !migrations?.length ? (
          <div className="empty-state">
            <p>No migrations yet.</p>
            <button onClick={() => setShowModal(true)} className="btn btn-secondary btn-sm mt-3">
              Create your first migration
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
                      {m.resource_count != null
                        ? `${m.resource_count} resource${m.resource_count !== 1 ? 's' : ''}`
                        : '—'}
                    </td>
                    <td>{formatDate(m.created_at)}</td>
                    <td>
                      <Link to={`/migrations/${m.id}`} className="btn btn-ghost btn-sm">
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

      {/* Modal */}
      {showModal && (
        <div
          className="modal-overlay"
          onClick={(e) => { if (e.target === e.currentTarget) setShowModal(false); }}
          role="dialog"
          aria-modal="true"
          aria-label="Create new migration"
        >
          <div className="modal">
            <div className="modal-header">
              <h3 className="text-sm font-semibold" style={{ color: '#0f172a' }}>New Migration</h3>
              <button onClick={() => setShowModal(false)} className="btn btn-ghost btn-sm" aria-label="Close">
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
                <label htmlFor="migration-name" className="field-label">Migration Name</label>
                <input
                  id="migration-name"
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g., Production VPC Migration"
                  className="field-input"
                  autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); }}
                />
              </div>
              <div>
                <label htmlFor="aws-connection" className="field-label">AWS Connection (optional)</label>
                <select
                  id="aws-connection"
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
                onClick={() => { setShowModal(false); setNewName(''); setSelectedConnectionId(''); createMigration.reset(); }}
                className="btn btn-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={!newName.trim() || createMigration.isPending}
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
