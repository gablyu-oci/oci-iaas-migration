import { Link } from 'react-router-dom';
import { useTranslationJobs, useDeleteTranslationJob } from '../api/hooks/useTranslationJobs';
import { formatDate, formatCost, cn, getSkillRunName } from '../lib/utils';

const STATUS_COLORS: Record<string, string> = {
  queued:   'bg-gray-100 text-gray-800',
  running:  'bg-blue-100 text-blue-800',
  complete: 'bg-green-100 text-green-800',
  failed:   'bg-red-100 text-red-800',
};

export default function TranslationJobList() {
  const { data: skillRuns, isLoading } = useTranslationJobs();
  const deleteSkillRun = useDeleteTranslationJob();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Translation Jobs</h1>
          <p className="text-gray-500 text-sm mt-1">All translation jobs across migrations</p>
        </div>
        <Link
          to="/translation-jobs/new"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm"
        >
          New Translation Job
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow">
        {isLoading ? (
          <div className="p-6 space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="animate-pulse h-10 bg-gray-100 rounded" />
            ))}
          </div>
        ) : !skillRuns?.length ? (
          <div className="p-12 text-center text-gray-500">
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
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Run Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Confidence</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cost</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {skillRuns.map((run) => (
                  <tr key={run.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">
                      {getSkillRunName(run.skill_type, run.resource_names, run.resource_name)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn('px-2 py-0.5 rounded text-xs font-medium', STATUS_COLORS[run.status] || STATUS_COLORS.queued)}>
                        {run.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {run.status === 'complete' ? `${(run.confidence * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm font-mono text-gray-600">
                      {formatCost(run.total_cost_usd)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatDate(run.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        {run.status === 'complete' ? (
                          <Link to={`/translation-jobs/${run.id}/results`} className="text-blue-600 hover:text-blue-800 text-sm font-medium">
                            View Results
                          </Link>
                        ) : run.status === 'running' || run.status === 'queued' ? (
                          <Link to={`/translation-jobs/${run.id}`} className="text-blue-600 hover:text-blue-800 text-sm font-medium">
                            View Progress
                          </Link>
                        ) : (
                          <Link to={`/translation-jobs/${run.id}/results`} className="text-gray-600 hover:text-gray-800 text-sm font-medium">
                            View Details
                          </Link>
                        )}
                        <button
                          onClick={() => {
                            if (confirm('Delete this translation job?')) deleteSkillRun.mutate(run.id);
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
