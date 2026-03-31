import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMigrations, useCreateMigration } from '../api/hooks/useMigrations';
import { useConnections } from '../api/hooks/useConnections';
import { formatDate } from '../lib/utils';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Migration {
  id: string;
  name: string;
  status: string;
  discovery_status?: string;
  resource_count?: number | null;
  aws_connection_id?: string | null;
  created_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── MigrationCard ─────────────────────────────────────────────────────────────

function MigrationCard({ migration, connectionName }: { migration: Migration; connectionName?: string }) {
  return (
    <Link
      to={`/migrations/${migration.id}`}
      style={{ textDecoration: 'none', display: 'block' }}
    >
      <div
        className="rounded-xl p-4 transition-all cursor-pointer"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-rule)',
          boxShadow: 'var(--shadow-card)',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-hover)';
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-fence)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-card)';
          (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-rule)';
        }}
      >
        {/* Card header */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <h3
            className="text-sm font-semibold leading-tight truncate"
            style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-display)' }}
          >
            {migration.name}
          </h3>
          <span className={`${statusBadge(migration.status)} flex-shrink-0`}>
            <span className="badge-dot" />
            {migration.status}
          </span>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-3 flex-wrap mb-3">
          {migration.resource_count != null ? (
            <div
              className="flex items-center gap-1.5 text-xs"
              style={{ color: 'var(--color-text-dim)' }}
            >
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7c0-2-1-3-3-3H7C5 4 4 5 4 7z" />
              </svg>
              <span>
                <strong style={{ color: 'var(--color-text-bright)' }}>{migration.resource_count}</strong>
                {' '}resource{migration.resource_count !== 1 ? 's' : ''}
              </span>
            </div>
          ) : (
            <span className="text-xs" style={{ color: 'var(--color-rail)' }}>No resources yet</span>
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center justify-between pt-2.5"
          style={{ borderTop: '1px solid var(--color-rule)' }}
        >
          <span className="text-xs" style={{ color: 'var(--color-rail)' }}>
            {formatDate(migration.created_at)}
          </span>
          {connectionName ? (
            <span
              className="text-xs truncate max-w-[120px]"
              style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}
              title={connectionName}
            >
              {connectionName}
            </span>
          ) : (
            <span className="text-xs" style={{ color: 'var(--color-rail)' }}>No connection</span>
          )}
        </div>
      </div>
    </Link>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Migrations() {
  const navigate = useNavigate();
  const { data: migrations, isLoading } = useMigrations();
  const { data: connections } = useConnections();
  const createMigration = useCreateMigration();

  const [showModal, setShowModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [selectedConnectionId, setSelectedConnectionId] = useState('');
  const [search, setSearch] = useState('');

  const connectionMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const c of connections || []) map[c.id] = `${c.name} (${c.region})`;
    return map;
  }, [connections]);

  const filtered = useMemo(() => {
    if (!migrations) return [];
    if (!search.trim()) return migrations;
    const q = search.toLowerCase();
    return migrations.filter((m) => m.name.toLowerCase().includes(q));
  }, [migrations, search]);

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
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

      {/* ── Page header + toolbar ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1
            className="page-title"
            style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem' }}
          >
            Migrations
          </h1>
          <p className="page-subtitle">
            {migrations?.length ?? 0} project{(migrations?.length ?? 0) !== 1 ? 's' : ''} · AWS → OCI migration journeys
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <svg
              className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
              style={{ color: 'var(--color-rail)' }}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search migrations…"
              className="field-input"
              style={{ paddingLeft: '2rem', width: '200px' }}
            />
          </div>

          <button onClick={() => setShowModal(true)} className="btn btn-primary">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Migration
          </button>
        </div>
      </div>

      {/* ── Migration grid ── */}
      {isLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skel h-36 rounded-xl" />
          ))}
        </div>
      ) : !migrations?.length ? (
        <div className="panel">
          <div className="empty-state">
            <svg className="w-10 h-10 mx-auto mb-3 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <p>No migrations yet.</p>
            <button onClick={() => setShowModal(true)} className="btn btn-secondary btn-sm mt-3">
              Create your first migration
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
          {filtered.map((m) => (
            <MigrationCard
              key={m.id}
              migration={m}
              connectionName={m.aws_connection_id ? connectionMap[m.aws_connection_id] : undefined}
            />
          ))}
        </div>
      )}

      {/* ── Create Migration Modal ── */}
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
              <div>
                <h3
                  className="text-sm font-semibold"
                  style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-display)' }}
                >
                  New Migration
                </h3>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                  Start a new AWS → OCI migration project
                </p>
              </div>
              <button onClick={() => setShowModal(false)} className="btn btn-ghost btn-sm" aria-label="Close">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="modal-body space-y-4">
              {createMigration.isError && (
                <div className="alert alert-error" role="alert">
                  {(createMigration.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to create migration.'}
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
                {createMigration.isPending ? <><span className="spinner" />Creating…</> : 'Create Migration'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
