import { useState, useMemo, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useResources, type Resource } from '../api/hooks/useResources';
import { useCreateTranslationJob, useResourceTranslationJobs, type TranslationJob } from '../api/hooks/useTranslationJobs';
import { useMigrations } from '../api/hooks/useMigrations';
import ResourceTable from '../components/ResourceTable';
import client from '../api/client';
import { cn, formatDate } from '../lib/utils';

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
  'CloudTrail': 'dependency_discovery',
  'FlowLog': 'dependency_discovery',
};

const RUN_STATUS_COLORS: Record<string, string> = {
  queued:   'bg-gray-100 text-gray-700',
  running:  'bg-blue-100 text-blue-700',
  complete: 'bg-green-100 text-green-700',
  failed:   'bg-red-100 text-red-700',
};

function ResourceSkillRunsPanel({ resourceId }: { resourceId: string }) {
  const { data: runs, isLoading } = useResourceTranslationJobs(resourceId);

  if (isLoading) {
    return <div className="animate-pulse space-y-2">{[...Array(3)].map((_, i) => <div key={i} className="h-10 bg-gray-100 rounded" />)}</div>;
  }
  if (!runs || runs.length === 0) {
    return <p className="text-sm text-gray-500 py-4 text-center">No translation jobs for this resource yet.</p>;
  }
  return (
    <div className="space-y-2">
      {runs.map((run: TranslationJob) => (
        <div key={run.id} className="flex items-center justify-between p-3 border border-gray-200 rounded-lg text-sm">
          <div className="flex items-center gap-3 min-w-0">
            <span className={cn('px-2 py-0.5 rounded text-xs font-medium flex-shrink-0', RUN_STATUS_COLORS[run.status] || 'bg-gray-100 text-gray-700')}>
              {run.status}
            </span>
            <span className="text-gray-600 font-mono text-xs truncate">{run.skill_type}</span>
            {run.status === 'complete' && (
              <span className="text-gray-500 text-xs">{Math.round(run.confidence * 100)}%</span>
            )}
          </div>
          <div className="flex items-center gap-3 flex-shrink-0 ml-3">
            <span className="text-xs text-gray-400">{formatDate(run.created_at)}</span>
            <Link
              to={run.status === 'complete' ? `/translation-jobs/${run.id}/results` : `/translation-jobs/${run.id}`}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
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
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((r) => r.id)));
    }
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
    // Group by skill type
    const groups = new Map<string, Resource[]>();
    for (const r of selected) {
      const skill = SKILL_FOR_TYPE[r.aws_type] ?? 'cfn_terraform';
      const list = groups.get(skill) ?? [];
      list.push(r);
      groups.set(skill, list);
    }
    // Launch one skill run per group
    let lastRunId: string | null = null;
    for (const [skillType, groupResources] of groups.entries()) {
      try {
        const result = await createSkillRun.mutateAsync({
          skill_type: skillType,
          input_resource_id: groupResources[0].id,
          config: { resource_ids: groupResources.map((r) => r.id), max_iterations: 3 },
        });
        lastRunId = result.id;
      } catch {
        // continue
      }
    }
    setSelectedIds(new Set());
    navigate(lastRunId ? `/translation-jobs/${lastRunId}` : '/dashboard');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center text-sm text-gray-500 hover:text-gray-700 mb-2"
        >
          ← Back
        </button>
        <h1 className="text-2xl font-bold">Resources</h1>
        <p className="text-gray-600 mt-1">Browse discovered AWS resources across your migrations.</p>
      </div>

      {/* Filters */}
      <div className="flex gap-4 flex-wrap">
        <div>
          <label htmlFor="migration-filter" className="block text-sm font-medium text-gray-700 mb-1">
            Migration
          </label>
          <select
            id="migration-filter"
            value={migrationFilter}
            onChange={(e) => { setMigrationFilter(e.target.value); setSelectedIds(new Set()); }}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          >
            <option value="">All Migrations</option>
            {migrations?.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="type-filter" className="block text-sm font-medium text-gray-700 mb-1">
            Resource Type
          </label>
          <select
            id="type-filter"
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setSelectedIds(new Set()); }}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          >
            <option value="">All Types</option>
            {resourceTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Resource Table */}
      <div className="bg-white rounded-lg shadow">
        {/* Batch action bar */}
        {selectedIds.size > 0 && (
          <div className="px-4 py-3 bg-blue-50 border-b flex items-center justify-between gap-4">
            <p className="text-sm text-blue-700 font-medium">
              {selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={handleBatchRunSkill}
                disabled={createSkillRun.isPending}
                className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
              >
                {createSkillRun.isPending ? 'Launching…' : 'Run Skills'}
              </button>
              <button
                onClick={handleBatchDelete}
                disabled={isDeleting}
                className="px-3 py-1.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 font-medium"
              >
                {isDeleting ? 'Deleting…' : 'Delete Selected'}
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="p-6">
            <div className="animate-pulse space-y-3">
              {[...Array(5)].map((_, i) => <div key={i} className="h-10 bg-gray-100 rounded" />)}
            </div>
          </div>
        ) : isError ? (
          <div className="p-6 text-center text-red-500">Failed to load resources. Please try again.</div>
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
          className="fixed inset-0 z-50 flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-label="Resource Details"
        >
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => setViewResource(null)}
            aria-hidden="true"
          />
          <div className="relative bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col">
            <div className="p-6 border-b flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold">{viewResource.name || 'Unnamed Resource'}</h3>
                <p className="text-sm text-gray-500 mt-0.5">{viewResource.aws_type}</p>
              </div>
              <button
                onClick={() => { setViewResource(null); setModalTab('config'); }}
                className="text-gray-400 hover:text-gray-600"
                aria-label="Close modal"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b px-6">
              {(['config', 'runs'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setModalTab(tab)}
                  className={cn(
                    'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
                    modalTab === tab
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  )}
                >
                  {tab === 'config' ? 'Raw Config' : 'Translation Jobs'}
                </button>
              ))}
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {modalTab === 'config' ? (
                <>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-500">Name</span>
                      <p className="font-medium">{viewResource.name || '\u2014'}</p>
                    </div>
                    <div>
                      <span className="text-gray-500">Type</span>
                      <p className="font-medium">{viewResource.aws_type}</p>
                    </div>
                    <div>
                      <span className="text-gray-500">ARN</span>
                      <p className="font-mono text-xs break-all">{viewResource.aws_arn || '\u2014'}</p>
                    </div>
                    <div>
                      <span className="text-gray-500">Status</span>
                      <p className="font-medium">{viewResource.status}</p>
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-700">Raw Configuration</span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(JSON.stringify(viewResource.raw_config, null, 2));
                          }}
                          className="px-3 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 font-medium"
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
                          className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 font-medium"
                        >
                          Download
                        </button>
                      </div>
                    </div>
                    <pre className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-xs font-mono overflow-auto max-h-96 whitespace-pre-wrap">
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
