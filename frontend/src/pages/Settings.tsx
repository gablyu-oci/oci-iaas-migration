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
    error: 'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

export default function Settings() {
  const { data: connections, isLoading } = useConnections();
  const createConnection = useCreateConnection();
  const deleteConnection = useDeleteConnection();

  const [name, setName] = useState('');
  const [region, setRegion] = useState('us-east-1');
  const [credentialType, setCredentialType] = useState<'key_pair' | 'assume_role'>('key_pair');
  const [accessKeyId, setAccessKeyId] = useState('');
  const [secretAccessKey, setSecretAccessKey] = useState('');
  const [roleArn, setRoleArn] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const credentials: Record<string, string> =
      credentialType === 'key_pair'
        ? { access_key_id: accessKeyId, secret_access_key: secretAccessKey }
        : { role_arn: roleArn };
    createConnection.mutate(
      { name, region, credential_type: credentialType, credentials },
      {
        onSuccess: () => {
          setName('');
          setAccessKeyId('');
          setSecretAccessKey('');
          setRoleArn('');
        },
      }
    );
  };

  const handleDelete = (id: string) => {
    if (window.confirm('Delete this connection?')) deleteConnection.mutate(id);
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">Manage AWS connections for resource extraction</p>
      </div>

      {/* Add connection form */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Add AWS Connection</h2>
        </div>
        <div className="panel-body">
          {createConnection.isError && (
            <div className="alert alert-error mb-4" role="alert">
              {(createConnection.error as any)?.response?.data?.detail || 'Failed to create connection.'}
            </div>
          )}
          {createConnection.isSuccess && (
            <div className="alert alert-success mb-4" role="status">
              Connection created successfully.
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label htmlFor="conn-name" className="field-label">Connection Name</label>
                <input
                  id="conn-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  placeholder="My AWS Account"
                  className="field-input"
                />
              </div>
              <div>
                <label htmlFor="conn-region" className="field-label">Region</label>
                <select
                  id="conn-region"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  className="field-input field-select"
                >
                  {AWS_REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
            </div>

            <div>
              <p className="field-label mb-2">Credential Type</p>
              <div className="flex gap-6">
                {(['key_pair', 'assume_role'] as const).map((type) => (
                  <label key={type} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="credential_type"
                      value={type}
                      checked={credentialType === type}
                      onChange={() => setCredentialType(type)}
                      style={{ accentColor: 'var(--color-ember)' }}
                    />
                    <span className="text-xs" style={{ color: '#475569' }}>
                      {type === 'key_pair' ? 'Access Key Pair' : 'Assume Role'}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {credentialType === 'key_pair' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="access-key-id" className="field-label">Access Key ID</label>
                  <input
                    id="access-key-id"
                    type="text"
                    value={accessKeyId}
                    onChange={(e) => setAccessKeyId(e.target.value)}
                    required
                    placeholder="AKIA…"
                    className="field-input"
                    style={{ fontFamily: 'var(--font-mono)' }}
                  />
                </div>
                <div>
                  <label htmlFor="secret-access-key" className="field-label">Secret Access Key</label>
                  <input
                    id="secret-access-key"
                    type="password"
                    value={secretAccessKey}
                    onChange={(e) => setSecretAccessKey(e.target.value)}
                    required
                    className="field-input"
                    style={{ fontFamily: 'var(--font-mono)' }}
                  />
                </div>
              </div>
            )}

            {credentialType === 'assume_role' && (
              <div>
                <label htmlFor="role-arn" className="field-label">Role ARN</label>
                <input
                  id="role-arn"
                  type="text"
                  value={roleArn}
                  onChange={(e) => setRoleArn(e.target.value)}
                  required
                  placeholder="arn:aws:iam::123456789012:role/MyRole"
                  className="field-input"
                  style={{ fontFamily: 'var(--font-mono)' }}
                />
              </div>
            )}

            <button
              type="submit"
              disabled={createConnection.isPending}
              className="btn btn-primary"
            >
              {createConnection.isPending ? <><span className="spinner" />Creating…</> : 'Add Connection'}
            </button>
          </form>
        </div>
      </div>

      {/* Existing connections */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>AWS Connections</h2>
          {connections?.length ? (
            <span className="badge badge-neutral">{connections.length}</span>
          ) : null}
        </div>
        {isLoading ? (
          <div className="panel-body space-y-2">
            {[...Array(2)].map((_, i) => <div key={i} className="skel h-10" />)}
          </div>
        ) : !connections?.length ? (
          <div className="empty-state">
            <p>No connections configured. Add one above.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="dt">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Region</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {connections.map((conn) => (
                  <tr key={conn.id}>
                    <td className="td-primary">{conn.name}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{conn.region}</td>
                    <td style={{ fontSize: '0.75rem' }}>{conn.credential_type}</td>
                    <td>
                      <span className={statusBadge(conn.status)}>
                        <span className="badge-dot" />
                        {conn.status}
                      </span>
                    </td>
                    <td>{formatDate(conn.created_at)}</td>
                    <td>
                      <button
                        onClick={() => handleDelete(conn.id)}
                        disabled={deleteConnection.isPending}
                        className="btn btn-danger btn-sm"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
