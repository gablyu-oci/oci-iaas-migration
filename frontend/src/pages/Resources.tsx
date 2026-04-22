import { useState, useMemo, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useResources, type Resource } from '../api/hooks/useResources';
import { useCreateTranslationJob, useResourceTranslationJobs, type TranslationJob } from '../api/hooks/useTranslationJobs';
import { useMigrations } from '../api/hooks/useMigrations';
import client from '../api/client';
import { formatDate } from '../lib/utils';
import ResourceDetailPanel from '../components/ResourceDetailPanel';

const SKILL_FOR_TYPE: Record<string, string> = {
  'AWS::CloudFormation::Stack': 'cfn_terraform',
  'AWS::IAM::Policy': 'iam_translation',
  'AWS::IAM::Role': 'iam_translation',
  'AWS::EC2::VPC': 'network_translation',
  'AWS::EC2::Subnet': 'network_translation',
  'AWS::EC2::SecurityGroup': 'network_translation',
  'AWS::EC2::Instance': 'ec2_translation',
  'AWS::AutoScaling::AutoScalingGroup': 'ec2_translation',
  'AWS::RDS::DBInstance': 'database_translation',
  'AWS::RDS::DBCluster': 'database_translation',
  'AWS::ElasticLoadBalancingV2::LoadBalancer': 'loadbalancer_translation',
  CloudTrail: 'dependency_discovery',
  FlowLog: 'dependency_discovery',
};

function jobStatusBadge(status: string) {
  const map: Record<string, string> = {
    queued: 'badge badge-neutral',
    running: 'badge badge-running',
    complete: 'badge badge-success',
    failed: 'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

function resourceStatusBadge(status: string) {
  const map: Record<string, string> = {
    discovered: 'badge badge-neutral',
    extracted: 'badge badge-info',
    uploaded: 'badge badge-success',
    translated: 'badge badge-success',
    failed: 'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

function shortType(awsType: string): string {
  const parts = awsType.split('::');
  return parts.length >= 3 ? parts.slice(1).join('::') : awsType;
}

function typeService(awsType: string): string {
  // Returns the AWS service group, e.g. "EC2", "RDS", "IAM"
  const parts = awsType.split('::');
  return parts.length >= 2 ? parts[1] : awsType;
}

// ── Resource Translation Jobs Panel ───────────────────────────────────────────

function ResourceSkillRunsPanel({ resourceId }: { resourceId: string }) {
  const { data: runs, isLoading } = useResourceTranslationJobs(resourceId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => <div key={i} className="skel h-10" />)}
      </div>
    );
  }
  if (!runs || runs.length === 0) {
    return <div className="empty-state"><p>No translation jobs for this resource yet.</p></div>;
  }
  return (
    <div className="space-y-2">
      {runs.map((run: TranslationJob) => (
        <div
          key={run.id}
          className="flex items-center justify-between p-3 rounded-lg text-sm"
          style={{ background: 'var(--color-well)', border: '1px solid var(--color-fence)' }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <span className={jobStatusBadge(run.status)}>
              <span className="badge-dot" />
              {run.status}
            </span>
            <span className="text-xs truncate" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>
              {run.skill_type}
            </span>
            {run.status === 'complete' && (
              <span className="text-xs" style={{ color: 'var(--color-rail)' }}>
                {Math.round(run.confidence * 100)}%
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 flex-shrink-0 ml-3">
            <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>{formatDate(run.created_at)}</span>
            <Link
              to={run.status === 'complete' ? `/translation-jobs/${run.id}/results` : `/translation-jobs/${run.id}`}
              className="btn btn-ghost btn-sm"
            >
              {run.status === 'complete' ? 'Results' : 'View'} →
            </Link>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Resource Card ─────────────────────────────────────────────────────────────

function ResourceCard({
  resource,
  migrationName,
  selected,
  onToggle,
  onView,
}: {
  resource: Resource;
  migrationName?: string;
  selected: boolean;
  onToggle: () => void;
  onView: () => void;
}) {
  return (
    <div
      className="flex items-start gap-3 px-4 py-3 transition-colors cursor-pointer"
      style={{
        background: selected ? 'var(--color-ember-glow)' : 'transparent',
        borderBottom: '1px solid var(--color-rule)',
      }}
      onClick={onView}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onView(); }}
    >
      {/* Checkbox */}
      <div
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        role="checkbox"
        aria-checked={selected}
        tabIndex={-1}
        style={{ marginTop: '2px', flexShrink: 0 }}
      >
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          onClick={(e) => e.stopPropagation()}
          className="cb"
          aria-label={`Select ${resource.name || resource.aws_arn}`}
        />
      </div>

      {/* Type icon */}
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{ background: 'var(--color-ember-dim)', color: 'var(--color-ember)' }}
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: 'var(--color-text-bright)' }}>
              {resource.name || 'Unnamed Resource'}
            </p>
            <p
              className="text-xs truncate mt-0.5"
              style={{ color: 'var(--color-rail)', fontFamily: 'var(--font-mono)', maxWidth: '280px' }}
              title={resource.aws_arn}
            >
              {resource.aws_arn}
            </p>
          </div>
          <span className={`${resourceStatusBadge(resource.status)} flex-shrink-0`}>
            <span className="badge-dot" />
            {resource.status}
          </span>
        </div>
        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{ background: 'var(--color-well)', color: 'var(--color-text-dim)', border: '1px solid var(--color-rule)', fontFamily: 'var(--font-mono)', fontSize: '0.6875rem' }}
          >
            {shortType(resource.aws_type)}
          </span>
          {migrationName && (
            <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
              {migrationName}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Resources() {
  const navigate = useNavigate();
  const [migrationFilter, setMigrationFilter] = useState('');
  const [typeFilters, setTypeFilters] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [viewResource, setViewResource] = useState<Resource | null>(null);
  const [modalTab, setModalTab] = useState<'details' | 'config' | 'runs'>('details');

  const qc = useQueryClient();

  // Always fetch all resources and filter client-side for rich facet counts
  const { data: resources, isLoading, isError } = useResources(
    migrationFilter ? { migration_id: migrationFilter } : undefined
  );
  const { data: migrations } = useMigrations();
  const createSkillRun = useCreateTranslationJob();

  // Build migration id → name map
  const migrationMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const m of migrations || []) map[m.id] = m.name;
    return map;
  }, [migrations]);

  // All unique types from the current resource list
  const allTypes = useMemo(() => {
    if (!resources) return [];
    return Array.from(new Set(resources.map((r) => r.aws_type))).sort();
  }, [resources]);

  // Group types by AWS service for the checkbox tree
  const typesByService = useMemo(() => {
    const groups: Record<string, string[]> = {};
    for (const t of allTypes) {
      const svc = typeService(t);
      if (!groups[svc]) groups[svc] = [];
      groups[svc].push(t);
    }
    return Object.entries(groups).sort((a, b) => a[0].localeCompare(b[0]));
  }, [allTypes]);

  // Filtered resource list
  const filtered = useMemo(() => {
    let list = resources || [];
    if (typeFilters.size > 0) list = list.filter((r) => typeFilters.has(r.aws_type));
    if (statusFilter) list = list.filter((r) => r.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((r) =>
        r.name.toLowerCase().includes(q) ||
        r.aws_arn.toLowerCase().includes(q) ||
        r.aws_type.toLowerCase().includes(q)
      );
    }
    return list;
  }, [resources, typeFilters, statusFilter, search]);

  // Group filtered resources by type for section headers
  const groupedByType = useMemo(() => {
    const groups = new Map<string, Resource[]>();
    for (const r of filtered) {
      const list = groups.get(r.aws_type) || [];
      list.push(r);
      groups.set(r.aws_type, list);
    }
    return Array.from(groups.entries()).sort((a, b) => b[1].length - a[1].length);
  }, [filtered]);

  // Collapsible section state
  const [collapsedTypes, setCollapsedTypes] = useState<Set<string>>(new Set());
  const toggleCollapse = (t: string) => {
    setCollapsedTypes((prev) => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  };

  const handleToggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const handleBatchDelete = async () => {
    if (!window.confirm(`Delete ${selectedIds.size} resource${selectedIds.size !== 1 ? 's' : ''}?`)) return;
    setIsDeleting(true);
    const ids = Array.from(selectedIds);
    await Promise.allSettled(ids.map((id) => client.delete(`/api/aws/resources/${id}`)));
    setSelectedIds(new Set());
    await qc.invalidateQueries({ queryKey: ['resources'] });
    setIsDeleting(false);
  };

  const handleBatchRunSkill = async () => {
    const selected = filtered.filter((r) => selectedIds.has(r.id));
    const groups = new Map<string, Resource[]>();
    for (const r of selected) {
      const skill = SKILL_FOR_TYPE[r.aws_type] ?? 'cfn_terraform';
      const list = groups.get(skill) ?? [];
      list.push(r);
      groups.set(skill, list);
    }
    let lastRunId: string | null = null;
    for (const [skillType, groupResources] of groups.entries()) {
      try {
        const result = await createSkillRun.mutateAsync({
          skill_type: skillType,
          input_resource_id: groupResources[0].id,
          config: { resource_ids: groupResources.map((r) => r.id), max_iterations: 3 },
        });
        lastRunId = result.id;
      } catch { /* continue */ }
    }
    setSelectedIds(new Set());
    navigate(lastRunId ? `/translation-jobs/${lastRunId}` : '/dashboard');
  };

  const toggleTypeFilter = (t: string) => {
    setTypeFilters((prev) => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
    setSelectedIds(new Set());
  };

  const clearFilters = () => {
    setMigrationFilter('');
    setTypeFilters(new Set());
    setStatusFilter('');
    setSearch('');
    setSelectedIds(new Set());
  };

  const hasActiveFilters = migrationFilter || typeFilters.size > 0 || statusFilter || search.trim();

  // All unique statuses for status filter
  const allStatuses = useMemo(() => {
    if (!resources) return [];
    return Array.from(new Set(resources.map((r) => r.status))).sort();
  }, [resources]);

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

      {/* ── Page header + search bar ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="page-title" style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem' }}>Resources</h1>
          <p className="page-subtitle">
            Browse discovered AWS resources across your migrations
          </p>
        </div>

        {/* Search */}
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none"
            style={{ color: 'var(--color-rail)' }}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, ARN, or type…"
            className="field-input"
            style={{ paddingLeft: '2.25rem', width: '280px' }}
          />
        </div>
      </div>

      {/* ── Split view layout ── */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>

        {/* ── Left filter panel ── */}
        <aside
          style={{
            width: '280px',
            flexShrink: 0,
            position: 'sticky',
            top: '1.5rem',
          }}
        >
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}
          >
            {/* Filter header */}
            <div
              className="flex items-center justify-between px-4 py-3"
              style={{ borderBottom: '1px solid var(--color-rule)' }}
            >
              <span className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>Filters</span>
              {hasActiveFilters && (
                <button onClick={clearFilters} className="text-xs" style={{ color: 'var(--color-ember)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  Clear all
                </button>
              )}
            </div>

            {/* Migration filter */}
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <p className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-dim)' }}>Migration</p>
              <select
                value={migrationFilter}
                onChange={(e) => { setMigrationFilter(e.target.value); setSelectedIds(new Set()); }}
                className="field-input field-select w-full"
                style={{ fontSize: '0.75rem' }}
              >
                <option value="">All Migrations</option>
                {migrations?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>

            {/* Resource type checkbox tree */}
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--color-rule)', maxHeight: '320px', overflowY: 'auto' }}>
              <p className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-dim)' }}>AWS Resource Type</p>
              {typesByService.length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--color-rail)' }}>No types available</p>
              ) : (
                <div className="space-y-2">
                  {typesByService.map(([service, types]) => (
                    <div key={service}>
                      <p
                        className="text-xs font-semibold mb-1"
                        style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}
                      >
                        {service}
                      </p>
                      <div className="space-y-1 pl-2">
                        {types.map((t) => {
                          const count = (resources || []).filter((r) => r.aws_type === t).length;
                          return (
                            <label
                              key={t}
                              className="flex items-center gap-2 cursor-pointer"
                              style={{ color: 'var(--color-text-dim)' }}
                            >
                              <input
                                type="checkbox"
                                checked={typeFilters.has(t)}
                                onChange={() => toggleTypeFilter(t)}
                                className="cb"
                              />
                              <span className="text-xs flex-1 truncate">{shortType(t)}</span>
                              <span
                                className="text-xs flex-shrink-0"
                                style={{ color: 'var(--color-rail)' }}
                              >
                                {count}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Status filter */}
            <div className="px-4 py-3">
              <p className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-dim)' }}>Status</p>
              <div className="space-y-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="status-filter"
                    checked={statusFilter === ''}
                    onChange={() => { setStatusFilter(''); setSelectedIds(new Set()); }}
                    style={{ accentColor: 'var(--color-ember)' }}
                  />
                  <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>All statuses</span>
                </label>
                {allStatuses.map((s) => (
                  <label key={s} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="status-filter"
                      checked={statusFilter === s}
                      onChange={() => { setStatusFilter(s); setSelectedIds(new Set()); }}
                      style={{ accentColor: 'var(--color-ember)' }}
                    />
                    <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>{s}</span>
                    <span className="text-xs ml-auto" style={{ color: 'var(--color-rail)' }}>
                      {(resources || []).filter((r) => r.status === s).length}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </aside>

        {/* ── Right resource list panel ── */}
        <div className="flex-1 min-w-0">
          {/* Selection action bar */}
          {selectedIds.size > 0 && (
            <div className="selection-bar mb-2 rounded-xl">
              <p>{selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected</p>
              <div className="flex items-center gap-2">
                <button onClick={handleBatchRunSkill} disabled={createSkillRun.isPending} className="btn btn-primary btn-sm">
                  {createSkillRun.isPending ? <><span className="spinner" />Launching…</> : 'Run Skills'}
                </button>
                <button onClick={handleBatchDelete} disabled={isDeleting} className="btn btn-danger btn-sm">
                  {isDeleting ? 'Deleting…' : 'Delete Selected'}
                </button>
                <button onClick={() => setSelectedIds(new Set())} className="btn btn-ghost btn-sm">Clear</button>
              </div>
            </div>
          )}

          {/* Result meta */}
          <div className="flex items-center justify-between mb-2 px-1">
            <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
              {isLoading ? 'Loading…' : `${filtered.length} resource${filtered.length !== 1 ? 's' : ''} ${hasActiveFilters ? 'matching filters' : 'total'}`}
            </span>
            {typeFilters.size > 0 && (
              <span className="text-xs" style={{ color: 'var(--color-ember)' }}>
                {typeFilters.size} type filter{typeFilters.size !== 1 ? 's' : ''} active
              </span>
            )}
          </div>

          {/* Content */}
          {isLoading ? (
            <div
              className="rounded-xl overflow-hidden"
              style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)' }}
            >
              {[...Array(5)].map((_, i) => (
                <div key={i} className="px-4 py-3" style={{ borderBottom: '1px solid var(--color-rule)' }}>
                  <div className="skel h-10 rounded-lg" />
                </div>
              ))}
            </div>
          ) : isError ? (
            <div className="alert alert-error rounded-xl">Failed to load resources. Please try again.</div>
          ) : filtered.length === 0 ? (
            <div className="panel rounded-xl">
              <div className="empty-state">
                <svg className="w-10 h-10 mx-auto mb-3 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
                </svg>
                <p>No resources match the current filters.</p>
                {hasActiveFilters && (
                  <button onClick={clearFilters} className="btn btn-secondary btn-sm mt-3">Clear filters</button>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {groupedByType.map(([type, typeResources]) => {
                const collapsed = collapsedTypes.has(type);
                return (
                  <div
                    key={type}
                    className="rounded-xl overflow-hidden"
                    style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}
                  >
                    {/* Section header */}
                    <button
                      onClick={() => toggleCollapse(type)}
                      className="w-full flex items-center justify-between px-4 py-2.5 transition-colors text-left"
                      style={{ background: 'var(--color-raised)' }}
                    >
                      <div className="flex items-center gap-3">
                        <svg
                          className="w-3.5 h-3.5 transition-transform"
                          style={{ transform: collapsed ? 'rotate(0deg)' : 'rotate(90deg)', color: 'var(--color-rail)' }}
                          fill="none" stroke="currentColor" viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                        <span
                          className="text-xs font-semibold"
                          style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}
                        >
                          {shortType(type)}
                        </span>
                      </div>
                      <span
                        className="text-xs font-semibold px-2 py-0.5 rounded-full"
                        style={{ background: 'var(--color-ember-dim)', color: 'var(--color-ember)' }}
                      >
                        {typeResources.length}
                      </span>
                    </button>

                    {/* Resource cards */}
                    {!collapsed && (
                      <div>
                        {typeResources.map((r) => (
                          <ResourceCard
                            key={r.id}
                            resource={r}
                            migrationName={r.migration_id ? migrationMap[r.migration_id] : undefined}
                            selected={selectedIds.has(r.id)}
                            onToggle={() => handleToggle(r.id)}
                            onView={() => {
                              const match = filtered.find((res) => res.id === r.id);
                              if (match) setViewResource(match);
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Resource Detail Modal ── */}
      {viewResource && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Resource Details"
          onClick={(e) => { if (e.target === e.currentTarget) { setViewResource(null); setModalTab('details'); }}}
        >
          <div className="modal modal-lg" style={{ maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                  {viewResource.name || 'Unnamed Resource'}
                </h3>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>
                  {viewResource.aws_type}
                </p>
              </div>
              <button
                onClick={() => { setViewResource(null); setModalTab('details'); }}
                className="btn btn-ghost btn-sm"
                aria-label="Close modal"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Tabs */}
            <div className="tabs px-4">
              {(['details', 'config', 'runs'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setModalTab(tab)}
                  className={`tab-btn ${modalTab === tab ? 'active' : ''}`}
                >
                  {tab === 'details' ? 'Details' : tab === 'config' ? 'Raw Config' : 'Translation Jobs'}
                </button>
              ))}
            </div>

            <div className="modal-body overflow-y-auto flex-1 space-y-4">
              {modalTab === 'details' ? (
                <ResourceDetailPanel resourceId={viewResource.id} />
              ) : modalTab === 'config' ? (
                <>
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    {[
                      { label: 'Name', value: viewResource.name || '—' },
                      { label: 'Type', value: viewResource.aws_type, mono: true },
                      { label: 'ARN', value: viewResource.aws_arn || '—', mono: true, breakAll: true },
                      { label: 'Status', value: viewResource.status },
                    ].map(({ label, value, mono, breakAll }) => (
                      <div key={label}>
                        <p className="field-label">{label}</p>
                        <p
                          className="mt-1 text-xs"
                          style={{
                            color: 'var(--color-text-bright)',
                            fontFamily: mono ? 'var(--font-mono)' : undefined,
                            wordBreak: breakAll ? 'break-all' : undefined,
                          }}
                        >
                          {value}
                        </p>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <p className="field-label">Raw Configuration</p>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => navigator.clipboard.writeText(JSON.stringify(viewResource.raw_config, null, 2))}
                          className="btn btn-secondary btn-sm"
                        >
                          Copy
                        </button>
                        <button
                          onClick={() => {
                            const blob = new Blob([JSON.stringify(viewResource.raw_config, null, 2)], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `${viewResource.name || 'resource'}.json`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }}
                          className="btn btn-primary btn-sm"
                        >
                          Download
                        </button>
                      </div>
                    </div>
                    <pre
                      className="rounded-lg p-4 text-xs overflow-auto"
                      style={{
                        background: 'var(--color-well)',
                        border: '1px solid var(--color-fence)',
                        color: 'var(--color-text-dim)',
                        fontFamily: 'var(--font-mono)',
                        maxHeight: '20rem',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {JSON.stringify(viewResource.raw_config, null, 2)}
                    </pre>
                  </div>
                </>
              ) : (
                <ResourceSkillRunsPanel resourceId={viewResource.id} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
