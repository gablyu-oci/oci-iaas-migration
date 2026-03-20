import { useState, useMemo, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useResources, type Resource } from '../api/hooks/useResources';
import { useCreateTranslationJob, useResourceTranslationJobs, type TranslationJob } from '../api/hooks/useTranslationJobs';
import { useMigrations } from '../api/hooks/useMigrations';
import ResourceTable from '../components/ResourceTable';
import client from '../api/client';
import { formatDate } from '../lib/utils';

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
            <span className="text-xs truncate" style={{ color: '#64748b', fontFamily: 'var(--font-mono)' }}>
              {run.skill_type}
            </span>
            {run.status === 'complete' && (
              <span className="text-xs" style={{ color: '#94a3b8' }}>
                {Math.round(run.confidence * 100)}%
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 flex-shrink-0 ml-3">
            <span className="text-xs" style={{ color: '#475569' }}>{formatDate(run.created_at)}</span>
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

export default function Resources() {
  const navigate = useNavigate();
  const [migrationFilter, setMigrationFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [viewResource, setViewResource] = useState<Resource | null>(null);
  const [modalTab, setModalTab] = useState<'config' | 'runs'>('config');

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (migrationFilter) p.migration_id = migrationFilter;
    if (typeFilter) p.type = typeFilter;
    return Object.keys(p).length ? p : undefined;
  }, [migrationFilter, typeFilter]);

  const qc = useQueryClient();
  const { data: resources, isLoading, isError } = useResources(params);
  const { data: migrations } = useMigrations();
  const createSkillRun = useCreateTranslationJob();

  const resourceTypes = useMemo(() => {
    if (!resources) return [];
    return Array.from(new Set(resources.map((r) => r.aws_type))).sort();
  }, [resources]);

  const filtered = resources || [];
  const allSelected = filtered.length > 0 && filtered.every((r) => selectedIds.has(r.id));

  const handleToggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const handleToggleAll = useCallback(() => {
    if (allSelected) setSelectedIds(new Set());
    else setSelectedIds(new Set(filtered.map((r) => r.id)));
  }, [allSelected, filtered]);

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

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="page-title">Resources</h1>
        <p className="page-subtitle">Browse discovered AWS resources across your migrations.</p>
      </div>

      {/* Filters */}
      <div className="flex gap-4 flex-wrap">
        <div>
          <label htmlFor="migration-filter" className="field-label">Migration</label>
          <select
            id="migration-filter"
            value={migrationFilter}
            onChange={(e) => { setMigrationFilter(e.target.value); setSelectedIds(new Set()); }}
            className="field-input field-select"
            style={{ width: 'auto' }}
          >
            <option value="">All Migrations</option>
            {migrations?.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="type-filter" className="field-label">Resource Type</label>
          <select
            id="type-filter"
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setSelectedIds(new Set()); }}
            className="field-input field-select"
            style={{ width: 'auto' }}
          >
            <option value="">All Types</option>
            {resourceTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {/* Resource Table */}
      <div className="panel">
        {selectedIds.size > 0 && (
          <div className="selection-bar">
            <p>{selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected</p>
            <div className="flex items-center gap-2">
              <button
                onClick={handleBatchRunSkill}
                disabled={createSkillRun.isPending}
                className="btn btn-primary btn-sm"
              >
                {createSkillRun.isPending ? <><span className="spinner" />Launching…</> : 'Run Skills'}
              </button>
              <button onClick={handleBatchDelete} disabled={isDeleting} className="btn btn-danger btn-sm">
                {isDeleting ? 'Deleting…' : 'Delete Selected'}
              </button>
              <button onClick={() => setSelectedIds(new Set())} className="btn btn-ghost btn-sm">
                Clear
              </button>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="panel-body space-y-2">
            {[...Array(5)].map((_, i) => <div key={i} className="skel h-10" />)}
          </div>
        ) : isError ? (
          <div className="alert alert-error m-4">Failed to load resources. Please try again.</div>
        ) : (
          <ResourceTable
            resources={filtered}
            selectedIds={selectedIds}
            onToggle={handleToggle}
            onToggleAll={handleToggleAll}
            onView={(r) => {
              const match = filtered.find((res) => res.id === r.id);
              if (match) setViewResource(match);
            }}
          />
        )}
      </div>

      {/* Resource Detail Modal */}
      {viewResource && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Resource Details"
          onClick={(e) => { if (e.target === e.currentTarget) { setViewResource(null); setModalTab('config'); }}}
        >
          <div
            className="modal modal-lg"
            style={{ maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}
          >
            <div className="modal-header">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: '#0f172a' }}>
                  {viewResource.name || 'Unnamed Resource'}
                </h3>
                <p className="text-xs mt-0.5" style={{ color: '#64748b', fontFamily: 'var(--font-mono)' }}>
                  {viewResource.aws_type}
                </p>
              </div>
              <button
                onClick={() => { setViewResource(null); setModalTab('config'); }}
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
              {(['config', 'runs'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setModalTab(tab)}
                  className={`tab-btn ${modalTab === tab ? 'active' : ''}`}
                >
                  {tab === 'config' ? 'Raw Config' : 'Translation Jobs'}
                </button>
              ))}
            </div>

            <div className="modal-body overflow-y-auto flex-1 space-y-4">
              {modalTab === 'config' ? (
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
                            color: '#0f172a',
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
                        color: '#64748b',
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
