import { useState, type FormEvent } from 'react';
import {
  useConnections,
  useCreateConnection,
  useDeleteConnection,
} from '../api/hooks/useConnections';
import { formatDate } from '../lib/utils';

const AWS_REGIONS = [
  'us-east-1',
  'us-east-2',
  'us-west-1',
  'us-west-2',
  'eu-west-1',
  'eu-west-2',
  'eu-west-3',
  'eu-central-1',
  'eu-north-1',
  'ap-southeast-1',
  'ap-southeast-2',
  'ap-northeast-1',
  'ap-northeast-2',
  'ap-south-1',
  'sa-east-1',
  'ca-central-1',
];

export default function Settings() {
  const { data: connections, isLoading } = useConnections();
  const createConnection = useCreateConnection();
  const deleteConnection = useDeleteConnection();

  const [name, setName] = useState('');
  const [region, setRegion] = useState('us-east-1');
  const [credentialType, setCredentialType] = useState<
    'key_pair' | 'assume_role'
  >('key_pair');
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
    if (window.confirm('Are you sure you want to delete this connection?')) {
      deleteConnection.mutate(id);
    }
  };

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    inactive: 'bg-gray-100 text-gray-800',
    error: 'bg-red-100 text-red-800',
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-gray-600 mt-1">
          Manage your AWS connections for resource extraction.
        </p>
      </div>

      {/* Add Connection Form */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Add AWS Connection</h2>

        {createConnection.isError && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm" role="alert">
            {(createConnection.error as any)?.response?.data?.detail ||
              'Failed to create connection.'}
          </div>
        )}

        {createConnection.isSuccess && (
          <div className="mb-4 p-3 bg-green-50 text-green-700 rounded-lg text-sm" role="status">
            Connection created successfully.
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="conn-name"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Connection Name
              </label>
              <input
                id="conn-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="My AWS Account"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label
                htmlFor="conn-region"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Region
              </label>
              <select
                id="conn-region"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                {AWS_REGIONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Credential Type
            </label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="credential_type"
                  value="key_pair"
                  checked={credentialType === 'key_pair'}
                  onChange={() => setCredentialType('key_pair')}
                  className="text-blue-600"
                />
                <span className="text-sm">Access Key Pair</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="credential_type"
                  value="assume_role"
                  checked={credentialType === 'assume_role'}
                  onChange={() => setCredentialType('assume_role')}
                  className="text-blue-600"
                />
                <span className="text-sm">Assume Role</span>
              </label>
            </div>
          </div>

          {credentialType === 'key_pair' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="access-key-id"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Access Key ID
                </label>
                <input
                  id="access-key-id"
                  type="text"
                  value={accessKeyId}
                  onChange={(e) => setAccessKeyId(e.target.value)}
                  required
                  placeholder="AKIA..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono"
                />
              </div>
              <div>
                <label
                  htmlFor="secret-access-key"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Secret Access Key
                </label>
                <input
                  id="secret-access-key"
                  type="password"
                  value={secretAccessKey}
                  onChange={(e) => setSecretAccessKey(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono"
                />
              </div>
            </div>
          )}

          {credentialType === 'assume_role' && (
            <div>
              <label
                htmlFor="role-arn"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Role ARN
              </label>
              <input
                id="role-arn"
                type="text"
                value={roleArn}
                onChange={(e) => setRoleArn(e.target.value)}
                required
                placeholder="arn:aws:iam::123456789012:role/MyRole"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={createConnection.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
          >
            {createConnection.isPending
              ? 'Creating...'
              : 'Add Connection'}
          </button>
        </form>
      </div>

      {/* Existing Connections */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <h2 className="text-lg font-semibold">AWS Connections</h2>
        </div>

        {isLoading ? (
          <div className="p-6">
            <div className="animate-pulse space-y-3">
              <div className="h-10 bg-gray-100 rounded" />
              <div className="h-10 bg-gray-100 rounded" />
            </div>
          </div>
        ) : !connections?.length ? (
          <div className="p-6 text-center text-gray-500">
            No connections configured. Add one above.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Region
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Type
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Created
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {connections.map((conn) => (
                  <tr key={conn.id}>
                    <td className="px-4 py-3 text-sm font-medium">
                      {conn.name}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600 font-mono">
                      {conn.region}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {conn.credential_type}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${statusColors[conn.status] || 'bg-gray-100 text-gray-800'}`}
                      >
                        {conn.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDate(conn.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDelete(conn.id)}
                        disabled={deleteConnection.isPending}
                        className="text-red-600 hover:text-red-800 text-sm font-medium disabled:opacity-50"
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
