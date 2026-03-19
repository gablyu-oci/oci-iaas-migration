import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMigrations, useCreateMigration } from '../api/hooks/useMigrations';
import { useConnections } from '../api/hooks/useConnections';
import { formatDate, cn } from '../lib/utils';

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-800',
  complete: 'bg-blue-100 text-blue-800',
  failed: 'bg-red-100 text-red-800',
  created: 'bg-gray-100 text-gray-800',
  extracting: 'bg-blue-100 text-blue-800',
  extracted: 'bg-green-100 text-green-800',
  planning: 'bg-yellow-100 text-yellow-800',
};

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
    const payload: { name: string; aws_connection_id?: string } = {
      name: newName.trim(),
    };
    if (selectedConnectionId) {
      payload.aws_connection_id = selectedConnectionId;
    }
    createMigration.mutate(payload, {
      onSuccess: (newMigration) => {
        setShowModal(false);
        setNewName('');
        setSelectedConnectionId('');
        navigate(`/migrations/${newMigration.id}`);
      },
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Migrations</h1>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm"
        >
          New Migration
        </button>
      </div>

      <div className="bg-white rounded-lg shadow">
        {isLoading ? (
          <div className="p-6">
            <div className="animate-pulse space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-12 bg-gray-100 rounded" />
              ))}
            </div>
          </div>
        ) : !migrations?.length ? (
          <div className="p-8 text-center text-gray-500">
            No migrations yet.{' '}
            <button
              onClick={() => setShowModal(true)}
              className="text-blue-600 hover:text-blue-800 font-medium"
            >
              Create one
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Resources</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {migrations.map((m) => (
                  <tr key={m.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link
                        to={`/migrations/${m.id}`}
                        className="text-sm font-medium text-blue-600 hover:text-blue-800"
                      >
                        {m.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        'px-2 py-0.5 rounded text-xs font-medium',
                        STATUS_COLORS[m.status] || 'bg-gray-100 text-gray-800'
                      )}>
                        {m.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {m.resource_count != null ? `${m.resource_count} resource${m.resource_count !== 1 ? 's' : ''}` : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{formatDate(m.created_at)}</td>
                    <td className="px-4 py-3">
                      <Link
                        to={`/migrations/${m.id}`}
                        className="text-sm font-medium text-blue-600 hover:text-blue-800"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* New Migration Modal */}
      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowModal(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-label="Create new migration"
        >
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-semibold">New Migration</h2>

            {createMigration.isError && (
              <div className="p-3 bg-red-50 text-red-700 rounded-lg text-sm" role="alert">
                {(createMigration.error as any)?.response?.data?.detail || 'Failed to create migration.'}
              </div>
            )}

            <div>
              <label htmlFor="migration-name" className="block text-sm font-medium text-gray-700 mb-1">
                Migration Name
              </label>
              <input
                id="migration-name"
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g., Production VPC Migration"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                autoFocus
                onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); }}
              />
            </div>

            <div>
              <label htmlFor="aws-connection" className="block text-sm font-medium text-gray-700 mb-1">
                AWS Connection (optional)
              </label>
              <select
                id="aws-connection"
                value={selectedConnectionId}
                onChange={(e) => setSelectedConnectionId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">No connection</option>
                {(connections || []).map((conn) => (
                  <option key={conn.id} value={conn.id}>
                    {conn.name} ({conn.region})
                  </option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowModal(false);
                  setNewName('');
                  setSelectedConnectionId('');
                  createMigration.reset();
                }}
                className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={!newName.trim() || createMigration.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
              >
                {createMigration.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
