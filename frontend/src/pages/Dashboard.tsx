import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useResources } from '../api/hooks/useResources';
import { useTranslationJobs, useDeleteTranslationJob } from '../api/hooks/useTranslationJobs';
import { useCreateMigration, useMigrations } from '../api/hooks/useMigrations';
import { useConnections } from '../api/hooks/useConnections';
import { formatDate, formatCost, cn, getSkillRunName } from '../lib/utils';

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: resources, isLoading: loadingResources } = useResources();
  const { data: skillRuns, isLoading: loadingSkillRuns } = useTranslationJobs();
  const { data: migrations, isLoading: loadingMigrations } = useMigrations();
  const { data: connections } = useConnections();
  const createMigration = useCreateMigration();

  const recentRuns = (skillRuns || []).slice(0, 10);
  const deleteSkillRun = useDeleteTranslationJob();

  const [showNewMigrationModal, setShowNewMigrationModal] = useState(false);
  const [newMigrationName, setNewMigrationName] = useState('');
  const [selectedConnectionId, setSelectedConnectionId] = useState('');

  const handleCreateMigration = () => {
    if (!newMigrationName.trim()) return;
    const payload: { name: string; aws_connection_id?: string } = {
      name: newMigrationName.trim(),
    };
    if (selectedConnectionId) {
      payload.aws_connection_id = selectedConnectionId;
    }
    createMigration.mutate(payload, {
      onSuccess: (newMigration) => {
        setShowNewMigrationModal(false);
        setNewMigrationName('');
        setSelectedConnectionId('');
        navigate(`/migrations/${newMigration.id}`);
      },
    });
  };

  const statusColors: Record<string, string> = {
    queued: 'bg-gray-100 text-gray-800',
    running: 'bg-blue-100 text-blue-800',
    complete: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    draft: 'bg-yellow-100 text-yellow-800',
    planning: 'bg-blue-100 text-blue-800',
    ready: 'bg-green-100 text-green-800',
  };

  const cards = [
    {
      label: 'Resources',
      count: resources?.length ?? 0,
      loading: loadingResources,
      icon: (
        <svg className="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
        </svg>
      ),
      link: '/resources',
    },
    {
      label: 'Translation Jobs',
      count: skillRuns?.length ?? 0,
      loading: loadingSkillRuns,
      icon: (
        <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      link: '/translation-jobs',
    },
    {
      label: 'Migrations',
      count: migrations?.length ?? 0,
      loading: loadingMigrations,
      icon: (
        <svg className="w-8 h-8 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ),
      link: '/resources',
    },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-gray-600 mt-1">
          Overview of your AWS to OCI migration progress.
        </p>
      </div>

      {/* Count Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards.map((card) => (
          <Link
            key={card.label}
            to={card.link}
            className="bg-white rounded-lg shadow p-6 flex items-center gap-4 hover:shadow-md transition-shadow"
          >
            <div className="flex-shrink-0">{card.icon}</div>
            <div>
              <p className="text-sm text-gray-500">{card.label}</p>
              {card.loading ? (
                <div className="animate-pulse h-8 w-16 bg-gray-200 rounded mt-1" />
              ) : (
                <p className="text-3xl font-bold">{card.count}</p>
              )}
            </div>
          </Link>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="flex gap-4">
        <Link
          to="/translation-jobs/new"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
        >
          New Translation Job
        </Link>
        <button
          onClick={() => setShowNewMigrationModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
        >
          New Migration
        </button>
        <Link
          to="/settings"
          className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
        >
          Manage Connections
        </Link>
      </div>

      {/* New Migration Modal */}
      {showNewMigrationModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowNewMigrationModal(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-label="Create new migration"
        >
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 space-y-4">
            <h2 className="text-lg font-semibold">New Migration</h2>

            {createMigration.isError && (
              <div className="p-3 bg-red-50 text-red-700 rounded-lg text-sm" role="alert">
                {(createMigration.error as any)?.response?.data?.detail ||
                  'Failed to create migration.'}
              </div>
            )}

            <div>
              <label htmlFor="migration-name" className="block text-sm font-medium text-gray-700 mb-1">
                Migration Name
              </label>
              <input
                id="migration-name"
                type="text"
                value={newMigrationName}
                onChange={(e) => setNewMigrationName(e.target.value)}
                placeholder="e.g., Production VPC Migration"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                autoFocus
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
                  setShowNewMigrationModal(false);
                  setNewMigrationName('');
                  setSelectedConnectionId('');
                  createMigration.reset();
                }}
                className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreateMigration}
                disabled={!newMigrationName.trim() || createMigration.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium text-sm"
              >
                {createMigration.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Migrations */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b flex items-center justify-between">
          <h2 className="text-lg font-semibold">Migrations</h2>
        </div>
        {loadingMigrations ? (
          <div className="p-6">
            <div className="animate-pulse space-y-3">
              {[...Array(2)].map((_, i) => <div key={i} className="h-12 bg-gray-100 rounded" />)}
            </div>
          </div>
        ) : !migrations?.length ? (
          <div className="p-6 text-center text-gray-500">
            No migrations yet. Upload a CloudFormation template or IAM policy to get started.
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {migrations.map((m) => (
              <div key={m.id} className="p-4 flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link
                      to={`/migrations/${m.id}`}
                      className="font-medium text-sm text-blue-600 hover:text-blue-800 truncate"
                    >
                      {m.name}
                    </Link>
                    <span
                      className={cn(
                        'px-2 py-0.5 rounded text-xs font-medium flex-shrink-0',
                        statusColors[m.status] || statusColors.queued
                      )}
                    >
                      {m.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    <p className="text-xs text-gray-400">{formatDate(m.created_at)}</p>
                    {(m as any).resource_count !== undefined && (m as any).resource_count !== null && (
                      <p className="text-xs text-gray-400">
                        {(m as any).resource_count} resource{(m as any).resource_count !== 1 ? 's' : ''}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Link
                    to={`/migrations/${m.id}`}
                    className="px-3 py-1.5 text-sm bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
                  >
                    View Details
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Skill Runs */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <h2 className="text-lg font-semibold">Recent Translation Jobs</h2>
        </div>

        {loadingSkillRuns ? (
          <div className="p-6">
            <div className="animate-pulse space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-10 bg-gray-100 rounded" />
              ))}
            </div>
          </div>
        ) : recentRuns.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            No translation jobs yet.{' '}
            <Link to="/translation-jobs/new" className="text-blue-600 hover:text-blue-800">
              Create one
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Run Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Confidence
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Cost
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
                {recentRuns.map((run) => (
                  <tr key={run.id}>
                    <td className="px-4 py-3 text-sm text-gray-900 font-medium">
                      {getSkillRunName(run.skill_type, run.resource_names, run.resource_name)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-xs font-medium',
                          statusColors[run.status] || statusColors.queued
                        )}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {(run.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3 text-sm font-mono">
                      {formatCost(run.total_cost_usd)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDate(run.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        {run.status === 'complete' ? (
                          <Link
                            to={`/translation-jobs/${run.id}/results`}
                            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                          >
                            View Results
                          </Link>
                        ) : run.status === 'running' || run.status === 'queued' ? (
                          <Link
                            to={`/translation-jobs/${run.id}`}
                            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                          >
                            View Progress
                          </Link>
                        ) : (
                          <Link
                            to={`/translation-jobs/${run.id}/results`}
                            className="text-gray-600 hover:text-gray-800 text-sm font-medium"
                          >
                            View Details
                          </Link>
                        )}
                        <button
                          onClick={() => {
                            if (confirm('Delete this translation job?')) {
                              deleteSkillRun.mutate(run.id);
                            }
                          }}
                          className="text-red-500 hover:text-red-700 text-sm font-medium"
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
    </div>
  );
}
