import { Link } from 'react-router-dom';
import { useTranslationJobs, useDeleteTranslationJob } from '../api/hooks/useTranslationJobs';
import { formatDate, formatCost, getSkillRunName } from '../lib/utils';

function statusBadge(status: string) {
  const map: Record<string, string> = {
    queued:   'badge badge-neutral',
    running:  'badge badge-running',
    complete: 'badge badge-success',
    failed:   'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

export default function TranslationJobList() {
  const { data: skillRuns, isLoading } = useTranslationJobs();
  const deleteSkillRun = useDeleteTranslationJob();

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Translation Jobs</h1>
          <p className="page-subtitle">All translation jobs across migrations</p>
        </div>
        <Link to="/translation-jobs/new" className="btn btn-primary">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Translation Job
        </Link>
      </div>

      <div className="panel">
        {isLoading ? (
          <div className="panel-body space-y-2">
            {[...Array(5)].map((_, i) => <div key={i} className="skel h-10" />)}
          </div>
        ) : !skillRuns?.length ? (
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
                {skillRuns.map((run) => (
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
    </div>
  );
}
