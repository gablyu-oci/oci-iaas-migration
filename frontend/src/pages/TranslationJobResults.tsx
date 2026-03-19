import { useParams, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import {
  useTranslationJob,
  useTranslationJobArtifacts,
  useTranslationJobInteractions,
} from '../api/hooks/useTranslationJobs';
import { formatDate, formatCost, cn, getSkillRunName } from '../lib/utils';
import ArtifactViewer from '../components/ArtifactViewer';
import DependencyGraph from '../components/DependencyGraph';
import client from '../api/client';

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  return s > 0 ? `${h}h ${m}m ${s}s` : m > 0 ? `${h}h ${m}m` : `${h}h`;
}

const DECISION_STYLES: Record<string, string> = {
  APPROVED: 'text-green-600',
  APPROVED_WITH_NOTES: 'text-amber-600',
  NEEDS_FIXES: 'text-red-600',
};


type Tab = 'summary' | 'log' | 'artifacts';

export default function TranslationJobResults() {
  const { id } = useParams<{ id: string }>();
  const { data: run, isLoading, isError } = useTranslationJob(id || '');
  const { data: artifacts } = useTranslationJobArtifacts(id || '');
  const { data: interactions } = useTranslationJobInteractions(id || '');
  const [graphData, setGraphData] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('summary');

  useEffect(() => {
    if (
      run?.skill_type === 'dependency_discovery' &&
      artifacts &&
      artifacts.length > 0
    ) {
      const depArtifact = artifacts.find(
        (a) => a.file_type === 'dependency_json' || a.file_name.includes('dependency')
      );
      if (depArtifact) {
        client
          .get(`/api/artifacts/${depArtifact.id}/download`, { responseType: 'text' })
          .then((resp) => setGraphData(resp.data))
          .catch(() => {});
      }
    }
  }, [run?.skill_type, artifacts]);

  if (!id) return <div className="text-center py-12 text-gray-500">No translation job ID provided.</div>;
  if (isLoading) return (
    <div className="flex justify-center py-12">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
    </div>
  );
  if (isError || !run) return (
    <div className="text-center py-12">
      <p className="text-red-500 mb-4">Failed to load translation job results.</p>
      <Link to="/dashboard" className="text-blue-600 hover:text-blue-800">Back to Dashboard</Link>
    </div>
  );

  const confidencePercent = (run.confidence * 100).toFixed(0);
  const confidenceColor =
    run.confidence >= 0.8 ? 'text-green-600' : run.confidence >= 0.5 ? 'text-yellow-600' : 'text-red-600';

  const durationSecs =
    run.started_at && run.completed_at
      ? (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000
      : null;

  // Prefer output.iterations (set at completion), fall back to current_iteration
  const iterationCount =
    (run.output as Record<string, unknown> | null)?.iterations as number | undefined
    ?? run.current_iteration;

  const TABS: { key: Tab; label: string; count?: number }[] = [
    { key: 'summary', label: 'Summary' },
    { key: 'log', label: 'Agent Log', count: interactions?.length },
    { key: 'artifacts', label: 'Artifacts', count: artifacts?.length },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Translation Job Results</h1>
          <p className="text-gray-600 mt-1">
            {getSkillRunName(run.skill_type, run.resource_names, run.resource_name)} &middot; {run.status}
          </p>
        </div>
        <Link
          to="/dashboard"
          className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
        >
          Back to Dashboard
        </Link>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'py-3 px-1 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
                tab === t.key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              )}
            >
              {t.label}
              {t.count != null && (
                <span className={cn(
                  'ml-2 px-1.5 py-0.5 rounded-full text-xs',
                  tab === t.key ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-500'
                )}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Summary tab */}
      {tab === 'summary' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">Summary</h2>
            <div className="mb-4">
              <p className="text-sm text-gray-500">
                {run.resource_names && run.resource_names.length > 1 ? `Resources (${run.resource_names.length})` : 'Resource'}
              </p>
              {run.resource_names && run.resource_names.length > 1 ? (
                <ul className="mt-1 space-y-0.5">
                  {run.resource_names.map((name, i) => (
                    <li key={i} className="text-sm font-medium">{name || '—'}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm mt-1 font-medium">{run.resource_name || '—'}</p>
              )}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
              <div>
                <p className="text-sm text-gray-500">Skill Type</p>
                <p className="font-mono text-sm mt-1">{run.skill_type}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Confidence</p>
                <p className={cn('text-2xl font-bold mt-1', confidenceColor)}>{confidencePercent}%</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Total Cost</p>
                <p className="font-mono text-sm mt-1">{formatCost(run.total_cost_usd)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Iterations</p>
                <p className="text-sm mt-1">{iterationCount ?? '—'}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Duration</p>
                <p className="text-sm mt-1">{durationSecs != null ? formatDuration(durationSecs) : '—'}</p>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t grid grid-cols-2 gap-4 text-sm">
              <div><span className="text-gray-500">Started:</span> {formatDate(run.started_at)}</div>
              <div><span className="text-gray-500">Completed:</span> {formatDate(run.completed_at)}</div>
            </div>
          </div>

          {run.status === 'failed' && run.errors && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="text-red-800 font-semibold mb-2">Errors</h3>
              <pre className="text-red-700 text-sm whitespace-pre-wrap">
                {JSON.stringify(run.errors, null, 2)}
              </pre>
            </div>
          )}

          {run.skill_type === 'dependency_discovery' && graphData && (
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">Dependency Graph</h2>
              <DependencyGraph data={graphData} />
            </div>
          )}
        </div>
      )}

      {/* Log tab */}
      {tab === 'log' && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          {!interactions || interactions.length === 0 ? (
            <div className="p-8 text-center text-gray-400">No agent interactions recorded.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full font-mono text-xs">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium">Agent</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium">Model</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium">Iter</th>
                    <th className="px-4 py-3 text-left text-gray-500 font-medium">Decision</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">Conf</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">Tokens In</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">Tokens Out</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">Cost</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">Duration</th>
                    <th className="px-4 py-3 text-right text-gray-500 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {interactions.map((ix) => {
                    const decisionStyle = ix.decision
                      ? (DECISION_STYLES[ix.decision] ?? 'text-gray-600')
                      : 'text-gray-400';
                    return (
                      <tr key={ix.id} className="hover:bg-gray-50">
                        <td className="px-4 py-2 text-gray-700">{ix.agent_type ?? '—'}</td>
                        <td className="px-4 py-2 text-gray-500">{ix.model ?? '—'}</td>
                        <td className="px-4 py-2 text-gray-500 text-center">{ix.iteration ?? '—'}</td>
                        <td className={`px-4 py-2 font-medium ${decisionStyle}`}>{ix.decision ?? '—'}</td>
                        <td className="px-4 py-2 text-right text-gray-600">
                          {ix.confidence != null ? `${Math.round(ix.confidence * 100)}%` : '—'}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-500">
                          {ix.tokens_input?.toLocaleString() ?? '—'}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-500">
                          {ix.tokens_output?.toLocaleString() ?? '—'}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-500">
                          {ix.cost_usd != null ? `$${ix.cost_usd.toFixed(4)}` : '—'}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-400">
                          {ix.duration_seconds != null ? `${ix.duration_seconds.toFixed(1)}s` : '—'}
                        </td>
                        <td className="px-4 py-2 text-right text-gray-400">
                          {new Date(ix.created_at).toLocaleTimeString()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Artifacts tab */}
      {tab === 'artifacts' && (
        <div className="bg-white rounded-lg shadow p-6">
          <ArtifactViewer skillRunId={id} />
        </div>
      )}
    </div>
  );
}
