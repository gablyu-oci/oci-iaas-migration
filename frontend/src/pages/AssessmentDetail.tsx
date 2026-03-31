import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  useAssessment,
  useResourceAssessments,
  useAppGroups,
  useTCOReport,
  useDependencies,
  useRunAssessment,
} from '../api/hooks/useAssessments';
import { useMigration } from '../api/hooks/useMigrations';
import ReadinessScoreBadge from '../components/ReadinessScoreBadge';
import OSCompatBadge from '../components/OSCompatBadge';
import SixRBadge from '../components/SixRBadge';
import CostComparisonChart from '../components/CostComparisonChart';
import DependencyGraph from '../components/DependencyGraph';
import { formatDate } from '../lib/utils';

type TabId = 'overview' | 'workloads' | 'resources' | 'dependencies' | 'os-compat';

type SortKey = 'name' | 'aws_type' | 'readiness_score' | 'oci_shape' | 'aws_monthly_cost' | 'oci_monthly_cost' | 'os_compat_status';

function assessmentStatusBadge(status: string): string {
  const map: Record<string, string> = {
    pending: 'badge badge-neutral',
    running: 'badge badge-running',
    complete: 'badge badge-success',
    failed: 'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

function formatMoney(val: number): string {
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function AssessmentDetail() {
  const { assessmentId } = useParams<{ assessmentId: string }>();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [sortAsc, setSortAsc] = useState(true);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const { data: assessment, isLoading: loadingAssessment } = useAssessment(assessmentId || '');
  const { data: migration } = useMigration(assessment?.migration_id || '');
  const { data: resourceAssessments, isLoading: loadingResources } = useResourceAssessments(assessmentId || '');
  const { data: appGroups, isLoading: loadingApps } = useAppGroups(assessmentId || '');
  const { data: tcoReport, isLoading: loadingTCO } = useTCOReport(assessmentId || '');
  const { data: dependencies, isLoading: loadingDeps } = useDependencies(assessmentId || '');
  const runAssessment = useRunAssessment();

  const isRunning = assessment?.status === 'pending' || assessment?.status === 'running';

  const sortedResources = useMemo(() => {
    if (!resourceAssessments) return [];
    const sorted = [...resourceAssessments];
    sorted.sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortAsc ? aVal - bVal : bVal - aVal;
      }
      const aStr = String(aVal || '');
      const bStr = String(bVal || '');
      return sortAsc ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
    });
    return sorted;
  }, [resourceAssessments, sortKey, sortAsc]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  const handleRerun = () => {
    if (assessment?.migration_id) {
      runAssessment.mutate(assessment.migration_id);
    }
  };

  const savingsPct = assessment
    ? assessment.aws_monthly_cost > 0
      ? Math.round(((assessment.aws_monthly_cost - assessment.oci_projected_cost) / assessment.aws_monthly_cost) * 100)
      : 0
    : 0;

  const dependencyJson = useMemo(() => {
    if (!dependencies) return '';
    return JSON.stringify(dependencies);
  }, [dependencies]);

  const TABS: { id: TabId; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'resources', label: 'Resources' },
    { id: 'workloads', label: 'Workloads' },
    { id: 'dependencies', label: 'Dependencies' },
    { id: 'os-compat', label: 'OS Compatibility' },
  ];

  if (loadingAssessment) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="skel h-8 w-48" />
        <div className="skel h-40" />
        <div className="skel h-64" />
      </div>
    );
  }

  if (!assessment) {
    return (
      <div className="space-y-6 animate-fade-in">
        <Link to="/migrations" className="back-link">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Migrations
        </Link>
        <div className="empty-state">
          <p>Assessment not found.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Back link */}
      <Link
        to={assessment.migration_id ? `/migrations/${assessment.migration_id}` : '/migrations'}
        className="back-link"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to Migration
      </Link>

      {/* Header */}
      <div className="panel">
        <div className="panel-body">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h1 className="page-title">Assessment</h1>
                <span className={assessmentStatusBadge(assessment.status)}>
                  <span className="badge-dot" />
                  {assessment.status}
                </span>
              </div>
              {migration && (
                <p className="page-subtitle">
                  Migration: {migration.name}
                </p>
              )}
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                Created {formatDate(assessment.created_at)}
                {assessment.completed_at && ` \u00B7 Completed ${formatDate(assessment.completed_at)}`}
              </p>
            </div>
            <button
              onClick={handleRerun}
              disabled={isRunning || runAssessment.isPending}
              className="btn btn-primary flex-shrink-0"
            >
              {isRunning || runAssessment.isPending ? (
                <><span className="spinner" />Running...</>
              ) : (
                'Re-run Assessment'
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Progress indicator when running */}
      {isRunning && (
        <div className="panel">
          <div className="panel-body flex items-center gap-3" style={{ color: '#2563eb' }}>
            <span className="spinner flex-shrink-0" />
            <span className="text-sm">
              Assessment in progress
              {assessment.current_step ? ` \u2014 ${assessment.current_step}` : '...'}
            </span>
          </div>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="panel p-5">
          <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>Resources Assessed</p>
          <p className="text-2xl font-bold mt-1" style={{ color: 'var(--color-text-bright)' }}>
            {assessment.resources_assessed}
          </p>
        </div>
        <div className="panel p-5">
          <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>Avg Readiness Score</p>
          <div className="mt-1">
            <ReadinessScoreBadge score={Math.round(assessment.avg_readiness_score)} />
          </div>
        </div>
        <div className="panel p-5">
          <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>AWS Monthly Cost</p>
          <p className="text-2xl font-bold mt-1" style={{ color: '#FF9900' }}>
            {formatMoney(assessment.aws_monthly_cost)}
          </p>
        </div>
        <div className="panel p-5">
          <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>OCI Projected Cost</p>
          <p className="text-2xl font-bold mt-1" style={{ color: '#F80000' }}>
            {formatMoney(assessment.oci_projected_cost)}
          </p>
          {savingsPct > 0 && (
            <p className="text-xs mt-0.5" style={{ color: '#22c55e', fontWeight: 600 }}>
              {savingsPct}% savings
            </p>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="panel">
        <div className="tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
              {tab.id === 'resources' && resourceAssessments && (
                <span className="tab-count">{resourceAssessments.length}</span>
              )}
              {tab.id === 'workloads' && appGroups && (
                <span className="tab-count">{appGroups.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="panel-body space-y-6">
            {loadingTCO ? (
              <div className="space-y-3">
                <div className="skel h-8 w-48" />
                <div className="skel h-40" />
              </div>
            ) : tcoReport ? (
              <>
                <div>
                  <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-bright)' }}>
                    Cost Comparison by Category
                  </h3>
                  <CostComparisonChart breakdown={tcoReport.breakdown} />
                </div>

                <hr className="divider" />

                <div>
                  <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-bright)' }}>
                    Monthly Savings Summary
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div
                      className="p-4 rounded-lg"
                      style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}
                    >
                      <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>AWS Monthly</p>
                      <p className="text-lg font-bold mt-0.5" style={{ color: '#FF9900' }}>
                        {formatMoney(tcoReport.aws_monthly)}
                      </p>
                    </div>
                    <div
                      className="p-4 rounded-lg"
                      style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}
                    >
                      <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>OCI Monthly</p>
                      <p className="text-lg font-bold mt-0.5" style={{ color: '#F80000' }}>
                        {formatMoney(tcoReport.oci_monthly)}
                      </p>
                    </div>
                    <div
                      className="p-4 rounded-lg"
                      style={{ background: 'rgba(34,197,94,0.04)', border: '1px solid rgba(34,197,94,0.2)' }}
                    >
                      <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>Monthly Savings</p>
                      <p className="text-lg font-bold mt-0.5" style={{ color: '#22c55e' }}>
                        {tcoReport.savings_pct}%
                      </p>
                    </div>
                  </div>
                </div>

                <hr className="divider" />

                <div>
                  <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-bright)' }}>
                    3-Year TCO Comparison
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div
                      className="p-4 rounded-lg"
                      style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}
                    >
                      <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>3-Year AWS TCO</p>
                      <p className="text-lg font-bold mt-0.5" style={{ color: '#FF9900' }}>
                        {formatMoney(tcoReport.three_year_aws)}
                      </p>
                    </div>
                    <div
                      className="p-4 rounded-lg"
                      style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}
                    >
                      <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>3-Year OCI TCO</p>
                      <p className="text-lg font-bold mt-0.5" style={{ color: '#F80000' }}>
                        {formatMoney(tcoReport.three_year_oci)}
                      </p>
                    </div>
                    <div
                      className="p-4 rounded-lg"
                      style={{ background: 'rgba(34,197,94,0.04)', border: '1px solid rgba(34,197,94,0.2)' }}
                    >
                      <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>3-Year Savings</p>
                      <p className="text-lg font-bold mt-0.5" style={{ color: '#22c55e' }}>
                        {formatMoney(tcoReport.three_year_savings)}
                      </p>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="empty-state">
                <p>No TCO data available. Run the assessment to generate cost analysis.</p>
              </div>
            )}
          </div>
        )}

        {/* Resources Tab */}
        {activeTab === 'resources' && (
          <div>
            {loadingResources ? (
              <div className="panel-body space-y-2">
                {[...Array(5)].map((_, i) => <div key={i} className="skel h-10" />)}
              </div>
            ) : !sortedResources.length ? (
              <div className="empty-state">
                <p>No resource assessments available.</p>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="dt">
                  <thead>
                    <tr>
                      <SortableHeader label="Name" sortKey="name" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                      <SortableHeader label="Type" sortKey="aws_type" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                      <SortableHeader label="Readiness" sortKey="readiness_score" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                      <SortableHeader label="OCI Shape" sortKey="oci_shape" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                      <SortableHeader label="AWS Cost" sortKey="aws_monthly_cost" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                      <SortableHeader label="OCI Cost" sortKey="oci_monthly_cost" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                      <SortableHeader label="OS Status" sortKey="os_compat_status" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedResources.map((r) => (
                      <tr key={r.id}>
                        <td className="td-primary">{r.name}</td>
                        <td>
                          <span className="badge badge-neutral" style={{ fontSize: '0.625rem' }}>
                            {shortType(r.aws_type)}
                          </span>
                        </td>
                        <td><ReadinessScoreBadge score={r.readiness_score} /></td>
                        <td>
                          <code style={{ fontSize: '0.6875rem' }}>{r.oci_shape || '\u2014'}</code>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                          {formatMoney(r.aws_monthly_cost)}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                          {formatMoney(r.oci_monthly_cost)}
                        </td>
                        <td><OSCompatBadge status={r.os_compat_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Workloads Tab */}
        {activeTab === 'workloads' && (
          <div className="panel-body space-y-3">
            {loadingApps ? (
              <div className="space-y-2">
                {[...Array(3)].map((_, i) => <div key={i} className="skel h-16" />)}
              </div>
            ) : !appGroups?.length ? (
              <div className="empty-state">
                <p>No application groups discovered.</p>
              </div>
            ) : (
              appGroups.map((group) => {
                const isExpanded = expandedGroups.has(group.id);
                return (
                  <div
                    key={group.id}
                    className="rounded-lg"
                    style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}
                  >
                    <button
                      onClick={() => toggleGroup(group.id)}
                      className="w-full flex items-center justify-between gap-3 p-4 text-left"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                      aria-expanded={isExpanded}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <svg
                          className="w-3.5 h-3.5 flex-shrink-0 transition-transform"
                          style={{
                            transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                            color: 'var(--color-text-dim)',
                          }}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                        <span className="text-sm font-medium truncate" style={{ color: 'var(--color-text-bright)' }}>
                          {group.name}
                        </span>
                        {group.workload_type && (
                          <span
                            className="badge"
                            style={{
                              fontSize: '0.5625rem',
                              background: 'rgba(37,99,235,0.08)',
                              color: '#2563eb',
                              borderColor: 'rgba(37,99,235,0.2)',
                            }}
                          >
                            {group.workload_type.replace('_', '/')}
                          </span>
                        )}
                        <SixRBadge strategy={group.six_r_strategy} confidence={group.six_r_confidence} />
                      </div>
                      <span className="badge badge-neutral flex-shrink-0">
                        {group.resource_count} resource{group.resource_count !== 1 ? 's' : ''}
                      </span>
                    </button>
                    {isExpanded && (
                      <div
                        className="px-4 pb-4 space-y-1.5"
                        style={{ borderTop: '1px solid var(--color-rule)', paddingTop: '0.75rem', marginLeft: '1.5rem' }}
                      >
                        {group.members.map((member) => (
                          <div
                            key={member.resource_id}
                            className="flex items-center gap-2 text-xs"
                            style={{ color: 'var(--color-text-dim)' }}
                          >
                            <span className="badge badge-neutral" style={{ fontSize: '0.5625rem' }}>
                              {shortType(member.aws_type)}
                            </span>
                            <span className="truncate">{member.name}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Dependencies Tab */}
        {activeTab === 'dependencies' && (
          <div className="panel-body">
            {loadingDeps ? (
              <div className="skel h-64" />
            ) : dependencyJson ? (
              <DependencyGraph data={dependencyJson} />
            ) : (
              <div className="empty-state">
                <p>No dependency data available.</p>
              </div>
            )}
          </div>
        )}

        {/* OS Compatibility Tab */}
        {activeTab === 'os-compat' && (
          <div>
            {loadingResources ? (
              <div className="panel-body space-y-2">
                {[...Array(5)].map((_, i) => <div key={i} className="skel h-10" />)}
              </div>
            ) : !resourceAssessments?.length ? (
              <div className="empty-state">
                <p>No OS compatibility data available.</p>
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="dt">
                  <thead>
                    <tr>
                      <th>Resource Name</th>
                      <th>AWS Type</th>
                      <th>OS Name</th>
                      <th>OS Version</th>
                      <th>Compatibility</th>
                      <th>Remediation Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resourceAssessments.map((r) => (
                      <tr key={r.id}>
                        <td className="td-primary">{r.name}</td>
                        <td>
                          <span className="badge badge-neutral" style={{ fontSize: '0.625rem' }}>
                            {shortType(r.aws_type)}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.8125rem' }}>{r.os_name || '\u2014'}</td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                          {r.os_version || '\u2014'}
                        </td>
                        <td><OSCompatBadge status={r.os_compat_status} /></td>
                        <td style={{ fontSize: '0.75rem', color: 'var(--color-text-dim)', maxWidth: '16rem' }}>
                          <span className="truncate block">{r.remediation_notes || '\u2014'}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Helper components ────────────────────────────────────────────────────────

function SortableHeader({
  label,
  sortKey: key,
  currentKey,
  asc,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  currentKey: SortKey;
  asc: boolean;
  onSort: (key: SortKey) => void;
}) {
  const isActive = currentKey === key;
  return (
    <th
      onClick={() => onSort(key)}
      style={{ cursor: 'pointer', userSelect: 'none' }}
      aria-sort={isActive ? (asc ? 'ascending' : 'descending') : 'none'}
    >
      {label}
      {isActive && (
        <span style={{ marginLeft: '0.25rem', fontSize: '0.625rem' }}>
          {asc ? '\u25B2' : '\u25BC'}
        </span>
      )}
    </th>
  );
}

function shortType(awsType: string): string {
  const parts = awsType.split('::');
  return parts.length >= 3 ? parts.slice(1).join('::') : awsType;
}
