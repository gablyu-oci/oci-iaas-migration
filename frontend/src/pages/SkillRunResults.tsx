import { useParams, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { useSkillRun, useSkillRunArtifacts } from '../api/hooks/useSkillRuns';
import { formatDate, formatCost, cn } from '../lib/utils';
import ArtifactViewer from '../components/ArtifactViewer';
import DependencyGraph from '../components/DependencyGraph';
import client from '../api/client';

export default function SkillRunResults() {
  const { id } = useParams<{ id: string }>();
  const { data: run, isLoading, isError } = useSkillRun(id || '');
  const { data: artifacts } = useSkillRunArtifacts(id || '');
  const [graphData, setGraphData] = useState<string | null>(null);

  // Load dependency graph data if this is a dependency_discovery run
  useEffect(() => {
    if (
      run?.skill_type === 'dependency_discovery' &&
      artifacts &&
      artifacts.length > 0
    ) {
      const depArtifact = artifacts.find(
        (a) =>
          a.file_type === 'dependency_json' ||
          a.file_name.includes('dependency')
      );
      if (depArtifact) {
        client
          .get(`/api/artifacts/${depArtifact.id}/download`, {
            responseType: 'text',
          })
          .then((resp) => setGraphData(resp.data))
          .catch(() => {
            // ignore load errors
          });
      }
    }
  }, [run?.skill_type, artifacts]);

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

  if (isError || !run) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 mb-4">Failed to load skill run results.</p>
        <Link to="/dashboard" className="text-blue-600 hover:text-blue-800">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const confidencePercent = (run.confidence * 100).toFixed(0);
  const confidenceColor =
    run.confidence >= 0.8
      ? 'text-green-600'
      : run.confidence >= 0.5
        ? 'text-yellow-600'
        : 'text-red-600';

  const duration =
    run.started_at && run.completed_at
      ? (
          (new Date(run.completed_at).getTime() -
            new Date(run.started_at).getTime()) /
          1000
        ).toFixed(1)
      : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Skill Run Results</h1>
          <p className="text-gray-600 mt-1">
            {run.skill_type} &middot; {run.status}
          </p>
        </div>
        <Link
          to="/dashboard"
          className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
        >
          Back to Dashboard
        </Link>
      </div>

      {/* Summary Card */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Summary</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
          <div>
            <p className="text-sm text-gray-500">Skill Type</p>
            <p className="font-mono text-sm mt-1">{run.skill_type}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Confidence</p>
            <p className={cn('text-2xl font-bold mt-1', confidenceColor)}>
              {confidencePercent}%
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Total Cost</p>
            <p className="font-mono text-sm mt-1">
              {formatCost(run.total_cost_usd)}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Iterations</p>
            <p className="text-sm mt-1">{run.current_iteration}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Duration</p>
            <p className="text-sm mt-1">{duration ? `${duration}s` : '\u2014'}</p>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Started:</span>{' '}
            {formatDate(run.started_at)}
          </div>
          <div>
            <span className="text-gray-500">Completed:</span>{' '}
            {formatDate(run.completed_at)}
          </div>
        </div>
      </div>

      {/* Errors */}
      {run.status === 'failed' && run.errors && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <h3 className="text-red-800 font-semibold mb-2">Errors</h3>
          <pre className="text-red-700 text-sm whitespace-pre-wrap">
            {JSON.stringify(run.errors, null, 2)}
          </pre>
        </div>
      )}

      {/* Dependency Graph (only for dependency_discovery) */}
      {run.skill_type === 'dependency_discovery' && graphData && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Dependency Graph</h2>
          <DependencyGraph data={graphData} />
        </div>
      )}

      {/* Artifacts */}
      <div className="bg-white rounded-lg shadow p-6">
        <ArtifactViewer skillRunId={id} />
      </div>
    </div>
  );
}
