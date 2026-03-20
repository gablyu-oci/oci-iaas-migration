import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslationJob } from '../api/hooks/useTranslationJobs';
import SkillProgressTracker from '../components/SkillProgressTracker';

export default function TranslationJobProgress() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: run, isLoading, isError } = useTranslationJob(id || '');

  if (!id) {
    return (
      <div className="empty-state">
        <p>No translation job ID provided.</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <span className="spinner spinner-lg" role="status" aria-label="Loading" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <Link to="/dashboard" className="back-link">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Dashboard
        </Link>
        <div className="alert alert-error">Failed to load translation job.</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <div>
        <Link to="/translation-jobs" className="back-link">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Translation Jobs
        </Link>
        <h1 className="page-title">Translation Job Progress</h1>
        <p className="page-subtitle">
          {run?.skill_type ? `Type: ${run.skill_type}` : 'Monitoring translation job…'}
        </p>
      </div>

      <SkillProgressTracker
        skillRunId={id}
        onComplete={() => navigate(`/translation-jobs/${id}/results`)}
      />

      {run?.status === 'failed' && (
        <div className="panel">
          <div className="panel-header">
            <h3 className="text-sm font-semibold" style={{ color: '#dc2626' }}>Translation Job Failed</h3>
          </div>
          <div className="panel-body space-y-4">
            {run.errors && (
              <pre
                className="text-xs p-3 rounded overflow-x-auto"
                style={{
                  background: 'var(--color-well)',
                  color: '#dc2626',
                  fontFamily: 'var(--font-mono)',
                  border: '1px solid rgba(239,68,68,0.2)',
                }}
              >
                {JSON.stringify(run.errors, null, 2)}
              </pre>
            )}
            <div className="flex items-center gap-3">
              <Link to="/translation-jobs/new" className="btn btn-secondary">
                Try Again
              </Link>
              <Link to="/dashboard" className="btn btn-ghost">
                Back to Dashboard
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
