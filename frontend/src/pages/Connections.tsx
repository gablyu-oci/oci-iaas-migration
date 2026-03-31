import { useState, type FormEvent } from 'react';
import { useConnections, useCreateConnection, useDeleteConnection } from '../api/hooks/useConnections';
import { formatDate } from '../lib/utils';

const AWS_REGIONS = [
  'us-east-1','us-east-2','us-west-1','us-west-2',
  'eu-west-1','eu-west-2','eu-west-3','eu-central-1','eu-north-1',
  'ap-southeast-1','ap-southeast-2','ap-northeast-1','ap-northeast-2','ap-south-1',
  'sa-east-1','ca-central-1',
];

function statusBadge(status: string) {
  const map: Record<string, string> = {
    active: 'badge badge-success',
    inactive: 'badge badge-neutral',
    invalid: 'badge badge-error',
    error: 'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

// ── Connection Card ───────────────────────────────────────────────────────────

function ConnectionCard({
  connection,
  onDelete,
  isDeleting,
}: {
  connection: {
    id: string;
    name: string;
    region: string;
    credential_type: string;
    status: string;
    created_at: string;
  };
  onDelete: (id: string) => void;
  isDeleting: boolean;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-rule)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: 'var(--color-ember-dim)', color: 'var(--color-ember)' }}
          >
            <svg viewBox="0 0 24 24" fill="currentColor" style={{ width: '18px', height: '18px' }}>
              <path d="M13.527 3.41a2 2 0 00-3.054 0L3.41 10.473A2 2 0 003 11.85v.3a2 2 0 00.41 1.377l7.063 7.063a2 2 0 003.054 0l7.063-7.063A2 2 0 0021 12.15v-.3a2 2 0 00-.41-1.377L13.527 3.41z" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
              {connection.name}
            </h3>
            <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>
              {connection.region}
            </p>
          </div>
        </div>
        <span className={`${statusBadge(connection.status)} flex-shrink-0`}>
          <span className="badge-dot" />
          {connection.status}
        </span>
      </div>

      <div
        className="flex items-center gap-3 flex-wrap py-2.5 mb-3"
        style={{ borderTop: '1px solid var(--color-rule)', borderBottom: '1px solid var(--color-rule)' }}
      >
        <div>
          <p className="text-xs" style={{ color: 'var(--color-rail)' }}>Credential type</p>
          <p className="text-xs font-medium mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
            {connection.credential_type === 'key_pair' ? 'Access Key Pair' : 'Assume Role'}
          </p>
        </div>
        <div style={{ marginLeft: 'auto' }}>
          <p className="text-xs" style={{ color: 'var(--color-rail)' }}>Added</p>
          <p className="text-xs font-medium mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
            {formatDate(connection.created_at)}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button className="btn btn-secondary btn-sm flex-1" onClick={() => {}}>
          Test Connection
        </button>
        <button
          onClick={() => onDelete(connection.id)}
          disabled={isDeleting}
          className="btn btn-danger btn-sm"
        >
          Delete
        </button>
      </div>
    </div>
  );
}

// ── Add Connection Form ───────────────────────────────────────────────────────

function AddConnectionCard() {
  const createConnection = useCreateConnection();
  const [name, setName] = useState('');
  const [region, setRegion] = useState('us-east-1');
  const [credentialType, setCredentialType] = useState<'key_pair' | 'assume_role'>('key_pair');
  const [accessKeyId, setAccessKeyId] = useState('');
  const [secretAccessKey, setSecretAccessKey] = useState('');
  const [roleArn, setRoleArn] = useState('');
  const [expanded, setExpanded] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const credentials: Record<string, string> =
      credentialType === 'key_pair'
        ? { aws_access_key_id: accessKeyId, aws_secret_access_key: secretAccessKey }
        : { role_arn: roleArn };
    createConnection.mutate(
      { name, region, credential_type: credentialType, credentials },
      {
        onSuccess: () => {
          setName(''); setAccessKeyId(''); setSecretAccessKey(''); setRoleArn('');
          setExpanded(false);
        },
      }
    );
  };

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full rounded-xl p-4 flex items-center gap-3 transition-colors text-left"
        style={{ background: 'var(--color-surface)', border: '2px dashed var(--color-fence)' }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-ember)'; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-fence)'; }}
      >
        <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: 'var(--color-ember-dim)', color: 'var(--color-ember)' }}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </div>
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Add AWS Connection</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>Connect an AWS account to start discovering resources</p>
        </div>
      </button>
    );
  }

  return (
    <div className="rounded-xl overflow-hidden"
      style={{ background: 'var(--color-surface)', border: '2px solid var(--color-ember)', boxShadow: 'var(--shadow-ember)' }}>
      <div className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: '1px solid var(--color-rule)', background: 'var(--color-ember-dim)' }}>
        <div>
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-display)' }}>
            New AWS Connection
          </h3>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
            Credentials are stored securely and used only for resource discovery
          </p>
        </div>
        <button onClick={() => setExpanded(false)} className="btn btn-ghost btn-sm" aria-label="Cancel">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <form onSubmit={handleSubmit} className="p-5 space-y-4">
        {createConnection.isError && (
          <div className="alert alert-error" role="alert">
            {(createConnection.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to create connection.'}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="conn-name" className="field-label">Connection Name</label>
            <input id="conn-name" type="text" value={name} onChange={(e) => setName(e.target.value)}
              required placeholder="My AWS Account" className="field-input" />
          </div>
          <div>
            <label htmlFor="conn-region" className="field-label">Region</label>
            <select id="conn-region" value={region} onChange={(e) => setRegion(e.target.value)}
              className="field-input field-select">
              {AWS_REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        </div>

        <div>
          <p className="field-label mb-2">Credential Type</p>
          <div className="flex rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-fence)', width: 'fit-content' }}>
            {(['key_pair', 'assume_role'] as const).map((type) => (
              <button key={type} type="button" onClick={() => setCredentialType(type)}
                className="px-4 py-2 text-xs font-medium transition-colors"
                style={{
                  background: credentialType === type ? 'var(--color-ember)' : 'var(--color-surface)',
                  color: credentialType === type ? 'white' : 'var(--color-text-dim)',
                  border: 'none', cursor: 'pointer',
                }}>
                {type === 'key_pair' ? 'Access Key Pair' : 'Assume Role'}
              </button>
            ))}
          </div>
        </div>

        {credentialType === 'key_pair' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label htmlFor="access-key-id" className="field-label">Access Key ID</label>
              <input id="access-key-id" type="text" value={accessKeyId}
                onChange={(e) => setAccessKeyId(e.target.value)} required placeholder="AKIA…"
                className="field-input" style={{ fontFamily: 'var(--font-mono)' }} />
            </div>
            <div>
              <label htmlFor="secret-access-key" className="field-label">Secret Access Key</label>
              <input id="secret-access-key" type="password" value={secretAccessKey}
                onChange={(e) => setSecretAccessKey(e.target.value)} required
                className="field-input" style={{ fontFamily: 'var(--font-mono)' }} />
            </div>
          </div>
        )}

        {credentialType === 'assume_role' && (
          <div>
            <label htmlFor="role-arn" className="field-label">Role ARN</label>
            <input id="role-arn" type="text" value={roleArn} onChange={(e) => setRoleArn(e.target.value)}
              required placeholder="arn:aws:iam::123456789012:role/MyRole"
              className="field-input" style={{ fontFamily: 'var(--font-mono)' }} />
          </div>
        )}

        <div className="flex items-center gap-3 pt-1" style={{ borderTop: '1px solid var(--color-rule)' }}>
          <button type="submit" disabled={createConnection.isPending} className="btn btn-primary">
            {createConnection.isPending ? <><span className="spinner" />Connecting…</> : 'Add Connection'}
          </button>
          <button type="button" onClick={() => setExpanded(false)} className="btn btn-secondary">Cancel</button>
        </div>
      </form>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Connections() {
  const { data: connections, isLoading } = useConnections();
  const deleteConnection = useDeleteConnection();

  const handleDelete = (id: string) => {
    if (window.confirm('Delete this connection?')) deleteConnection.mutate(id);
  };

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h1 className="page-title" style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem' }}>
          Connections
        </h1>
        <p className="page-subtitle">Manage AWS accounts used for resource discovery and extraction</p>
      </div>

      <AddConnectionCard />

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(2)].map((_, i) => <div key={i} className="skel rounded-xl" style={{ height: '168px' }} />)}
        </div>
      ) : !connections?.length ? (
        <div className="rounded-xl p-6 text-center"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)' }}>
          <p className="text-sm" style={{ color: 'var(--color-text-dim)' }}>
            No connections yet. Add one above to get started.
          </p>
        </div>
      ) : (
        <div>
          <p className="text-xs font-semibold mb-3" style={{ color: 'var(--color-text-dim)' }}>
            {connections.length} connection{connections.length !== 1 ? 's' : ''}
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {connections.map((conn) => (
              <ConnectionCard key={conn.id} connection={conn} onDelete={handleDelete}
                isDeleting={deleteConnection.isPending} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
