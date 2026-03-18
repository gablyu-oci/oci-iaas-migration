import { useParams, useNavigate, Link } from 'react-router-dom';
import { useSkillRun } from '../api/hooks/useSkillRuns';
import SkillProgressTracker from '../components/SkillProgressTracker';

export default function SkillRunProgress() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: run, isLoading, isError } = useSkillRun(id || '');

  if (!id) {
    return (
      <div className="text-center py-12 text-gray-500">
        No skill run ID provided.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div
          className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"
          role="status"
          aria-label="Loading"
        />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 mb-4">Failed to load skill run.</p>
        <Link to="/dashboard" className="text-blue-600 hover:text-blue-800">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Skill Run Progress</h1>
        <p className="text-gray-600 mt-1">
          {run?.skill_type ? `Type: ${run.skill_type}` : 'Monitoring skill run...'}
        </p>
      </div>

      <SkillProgressTracker
        skillRunId={id}
        onComplete={() => navigate(`/skill-runs/${id}/results`)}
      />

      {run?.status === 'failed' && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h3 className="text-red-800 font-semibold mb-2">Skill Run Failed</h3>
          <p className="text-red-700 text-sm">
            {run.errors
              ? JSON.stringify(run.errors, null, 2)
              : 'An unexpected error occurred.'}
          </p>
          <div className="mt-4 flex gap-3">
            <Link
              to="/skill-runs/new"
              className="text-sm text-blue-600 hover:text-blue-800 font-medium"
            >
              Try Again
            </Link>
            <Link
              to="/dashboard"
              className="text-sm text-gray-600 hover:text-gray-800 font-medium"
            >
              Back to Dashboard
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
