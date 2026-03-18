import { Link } from 'react-router-dom';
import { useResources } from '../api/hooks/useResources';
import { useSkillRuns } from '../api/hooks/useSkillRuns';
import { useMigrations } from '../api/hooks/useMigrations';
import { formatDate, formatCost, cn } from '../lib/utils';

export default function Dashboard() {
  const { data: resources, isLoading: loadingResources } = useResources();
  const { data: skillRuns, isLoading: loadingSkillRuns } = useSkillRuns();
  const { data: migrations, isLoading: loadingMigrations } = useMigrations();

  const recentRuns = (skillRuns || []).slice(0, 10);

  const statusColors: Record<string, string> = {
    queued: 'bg-gray-100 text-gray-800',
    running: 'bg-blue-100 text-blue-800',
    complete: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
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
      label: 'Skill Runs',
      count: skillRuns?.length ?? 0,
      loading: loadingSkillRuns,
      icon: (
        <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      link: '/skill-runs/new',
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
          to="/skill-runs/new"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
        >
          New Skill Run
        </Link>
        <Link
          to="/settings"
          className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
        >
          Manage Connections
        </Link>
      </div>

      {/* Recent Skill Runs */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <h2 className="text-lg font-semibold">Recent Skill Runs</h2>
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
            No skill runs yet.{' '}
            <Link to="/skill-runs/new" className="text-blue-600 hover:text-blue-800">
              Create one
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Skill Type
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
                    <td className="px-4 py-3 text-sm font-mono">
                      {run.skill_type}
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
                      {run.status === 'complete' ? (
                        <Link
                          to={`/skill-runs/${run.id}/results`}
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          View Results
                        </Link>
                      ) : run.status === 'running' || run.status === 'queued' ? (
                        <Link
                          to={`/skill-runs/${run.id}`}
                          className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                          View Progress
                        </Link>
                      ) : (
                        <Link
                          to={`/skill-runs/${run.id}/results`}
                          className="text-gray-600 hover:text-gray-800 text-sm font-medium"
                        >
                          View Details
                        </Link>
                      )}
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
