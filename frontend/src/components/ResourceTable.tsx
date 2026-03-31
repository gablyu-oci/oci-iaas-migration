import { Link } from 'react-router-dom';
import { formatDate } from '../lib/utils';

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

const STATUS_CLASS: Record<string, string> = {
  discovered: 'badge badge-info',
  uploaded:   'badge badge-success',
  running:    'badge badge-running',
  migrated:   'badge badge-success',
  failed:     'badge badge-error',
};

const RUN_STATUS_CLASS: Record<string, string> = {
  queued:   'badge badge-neutral',
  running:  'badge badge-running',
  complete: 'badge badge-success',
  failed:   'badge badge-error',
};

function LatestRunLinkCell({ run }: { run: LatestSkillRunSummary | null | undefined }) {
  if (!run) return <span style={{ color: 'var(--color-text-dim)' }}>—</span>;
  return (
    <Link
      to={run.status === 'complete' ? `/translation-jobs/${run.id}/results` : `/translation-jobs/${run.id}`}
      onClick={(e) => e.stopPropagation()}
      className="text-xs font-medium hover:underline"
      style={{ color: 'var(--color-ember)', fontFamily: 'var(--font-mono)' }}
    >
      {run.skill_type}
    </Link>
  );
}

function RunStatusCell({ run }: { run: LatestSkillRunSummary | null | undefined }) {
  if (!run) return <span style={{ color: 'var(--color-text-dim)' }}>—</span>;
  return (
    <span className={RUN_STATUS_CLASS[run.status] ?? 'badge badge-neutral'}>
      <span className="badge-dot" />
      {run.status}
    </span>
  );
}

function ConfidenceCell({ run }: { run: LatestSkillRunSummary | null | undefined }) {
  if (!run || run.status !== 'complete') return <span style={{ color: 'var(--color-text-dim)' }}>—</span>;
  return <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>{Math.round(run.confidence * 100)}%</span>;
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
      <table className="dt">
        <thead>
          <tr>
            {batchMode && (
              <th style={{ width: '2.5rem' }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={onToggleAll}
                  className="cb"
                  aria-label="Select all"
                />
              </th>
            )}
            <th>Name</th>
            <th>Type</th>
            <th>ARN</th>
            <th>Status</th>
            <th>Latest Run</th>
            <th>Run Status</th>
            <th>Confidence</th>
            <th>Migration</th>
            <th>Created</th>
            {(onDelete || onView) && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
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
                style={
                  isChecked
                    ? { background: 'rgba(249,115,22,0.06)' }
                    : isSingleSelected
                    ? { background: 'rgba(249,115,22,0.10)', outline: '2px solid rgba(249,115,22,0.3)', outlineOffset: '-2px' }
                    : undefined
                }
              >
                {batchMode && (
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => onToggle?.(r.id)}
                      className="cb"
                      aria-label={`Select ${r.name || r.id}`}
                    />
                  </td>
                )}
                <td style={{ color: 'var(--color-text-bright)', fontWeight: 500 }}>{r.name || '—'}</td>
                <td style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{r.aws_type}</td>
                <td
                  style={{
                    color: 'var(--color-text-dim)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.75rem',
                    maxWidth: '16rem',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {r.aws_arn || '—'}
                </td>
                <td>
                  <span className={STATUS_CLASS[r.status] ?? 'badge badge-neutral'}>
                    <span className="badge-dot" />
                    {r.status}
                  </span>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <LatestRunLinkCell run={r.latest_skill_run} />
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <RunStatusCell run={r.latest_skill_run} />
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <ConfidenceCell run={r.latest_skill_run} />
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  {r.migration_id && r.migration_name ? (
                    <Link
                      to={`/migrations/${r.migration_id}`}
                      className="text-xs hover:underline"
                      style={{ color: 'var(--color-ember)' }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {r.migration_name}
                    </Link>
                  ) : (
                    <span style={{ color: 'var(--color-text-dim)' }}>—</span>
                  )}
                </td>
                <td style={{ color: 'var(--color-text-dim)' }}>{formatDate(r.created_at)}</td>
                {(onDelete || onView) && (
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-2">
                      {onView && (
                        <button onClick={() => onView(r)} className="btn btn-ghost btn-sm">
                          View
                        </button>
                      )}
                      {onDelete && (
                        <button onClick={() => onDelete(r.id)} className="btn btn-danger btn-sm">
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
              <td colSpan={colCount} style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-dim)' }}>
                No resources found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
