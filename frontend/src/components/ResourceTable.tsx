import { Link } from 'react-router-dom';
import { formatDate, cn } from '../lib/utils';

export interface LatestSkillRunSummary {
  id: string;
  status: string;
  skill_type: string;
  confidence: number;
  completed_at: string | null;
}

export interface Resource {
  id: string;
  aws_type: string;
  aws_arn: string;
  name: string;
  status: string;
  created_at: string;
  raw_config?: Record<string, unknown>;
  migration_id?: string | null;
  migration_name?: string | null;
  latest_skill_run?: LatestSkillRunSummary | null;
}

interface Props {
  resources: Resource[];
  // Multi-select (batch mode)
  selectedIds?: Set<string>;
  onToggle?: (id: string) => void;
  onToggleAll?: () => void;
  // Single-select (detail mode — kept for backward compat)
  onSelect?: (resource: Resource) => void;
  selectedId?: string;
  filterType?: string;
  onDelete?: (resourceId: string) => void;
  onView?: (resource: Resource) => void;
}

const STATUS_COLORS: Record<string, string> = {
  discovered: 'bg-blue-100 text-blue-800',
  uploaded: 'bg-green-100 text-green-800',
  running: 'bg-blue-100 text-blue-700',
  migrated: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

const RUN_STATUS_COLORS: Record<string, string> = {
  queued:   'bg-gray-100 text-gray-700',
  running:  'bg-blue-100 text-blue-700',
  complete: 'bg-green-100 text-green-700',
  failed:   'bg-red-100 text-red-700',
};

function LatestRunLinkCell({ run }: { run: LatestSkillRunSummary | null | undefined }) {
  if (!run) return <span className="text-gray-400 text-sm">—</span>;
  return (
    <Link
      to={run.status === 'complete' ? `/translation-jobs/${run.id}/results` : `/translation-jobs/${run.id}`}
      onClick={(e) => e.stopPropagation()}
      className="text-xs text-blue-600 hover:text-blue-800 font-medium font-mono"
    >
      {run.skill_type}
    </Link>
  );
}

function RunStatusCell({ run }: { run: LatestSkillRunSummary | null | undefined }) {
  if (!run) return <span className="text-gray-400 text-sm">—</span>;
  return (
    <span className={cn('px-2 py-0.5 rounded text-xs font-medium', RUN_STATUS_COLORS[run.status] || 'bg-gray-100 text-gray-700')}>
      {run.status}
    </span>
  );
}

function ConfidenceCell({ run }: { run: LatestSkillRunSummary | null | undefined }) {
  if (!run || run.status !== 'complete') return <span className="text-gray-400 text-sm">—</span>;
  return <span className="text-sm text-gray-700">{Math.round(run.confidence * 100)}%</span>;
}

export default function ResourceTable({
  resources,
  selectedIds,
  onToggle,
  onToggleAll,
  onSelect,
  selectedId,
  filterType,
  onDelete,
  onView,
}: Props) {
  const filtered = filterType
    ? resources.filter((r) => r.aws_type === filterType)
    : resources;

  const batchMode = !!selectedIds && !!onToggle;
  const allSelected = batchMode && filtered.length > 0 && filtered.every((r) => selectedIds.has(r.id));
  const colCount = (batchMode ? 1 : 0) + 9 + (onDelete || onView ? 1 : 0);

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {batchMode && (
              <th className="px-4 py-3 w-10">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleAll}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  aria-label="Select all"
                />
              </th>
            )}
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ARN</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Latest Run</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Run Status</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Confidence</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Migration</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
            {(onDelete || onView) && (
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
            )}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {filtered.map((r) => {
            const isChecked = batchMode && selectedIds.has(r.id);
            const isSingleSelected = !batchMode && selectedId === r.id;
            return (
              <tr
                key={r.id}
                onClick={() => {
                  if (batchMode) onToggle?.(r.id);
                  else onSelect?.(r);
                }}
                role="row"
                className={cn(
                  'cursor-pointer hover:bg-gray-50 transition-colors',
                  isChecked && 'bg-blue-50 hover:bg-blue-50',
                  isSingleSelected && 'bg-blue-50 ring-2 ring-inset ring-blue-500',
                )}
              >
                {batchMode && (
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => onToggle?.(r.id)}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      aria-label={`Select ${r.name || r.id}`}
                    />
                  </td>
                )}
                <td className="px-4 py-3 text-sm font-medium">{r.name || '—'}</td>
                <td className="px-4 py-3 text-sm text-gray-600 font-mono">{r.aws_type}</td>
                <td className="px-4 py-3 text-sm text-gray-500 font-mono truncate max-w-xs">
                  {r.aws_arn || '—'}
                </td>
                <td className="px-4 py-3">
                  <span className={cn(
                    'px-2 py-0.5 rounded text-xs font-medium',
                    STATUS_COLORS[r.status] || 'bg-gray-100 text-gray-800'
                  )}>
                    {r.status}
                  </span>
                </td>
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  <LatestRunLinkCell run={r.latest_skill_run} />
                </td>
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  <RunStatusCell run={r.latest_skill_run} />
                </td>
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  <ConfidenceCell run={r.latest_skill_run} />
                </td>
                <td className="px-4 py-3 text-sm">
                  {r.migration_id && r.migration_name ? (
                    <Link to={`/migrations/${r.migration_id}`} className="text-blue-600 hover:text-blue-800" onClick={(e) => e.stopPropagation()}>
                      {r.migration_name}
                    </Link>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">{formatDate(r.created_at)}</td>
                {(onDelete || onView) && (
                  <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-2">
                      {onView && (
                        <button
                          onClick={() => onView(r)}
                          className="px-2 py-1 text-xs font-medium text-blue-600 border border-blue-300 rounded hover:bg-blue-50"
                        >
                          View
                        </button>
                      )}
                      {onDelete && (
                        <button
                          onClick={() => onDelete(r.id)}
                          className="px-2 py-1 text-xs font-medium text-red-600 border border-red-300 rounded hover:bg-red-50"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
          {filtered.length === 0 && (
            <tr>
              <td colSpan={colCount} className="px-4 py-8 text-center text-gray-500">
                No resources found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
