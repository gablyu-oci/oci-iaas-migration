import { useState, useEffect, useMemo, useCallback, useRef, type DragEvent } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useMigration, useUploadToMigration, useDeleteMigration } from '../api/hooks/useMigrations';
import { useResources, type Resource } from '../api/hooks/useResources';
import { useTranslationJobs } from '../api/hooks/useTranslationJobs';
import { formatDate, cn, getSkillRunName } from '../lib/utils';
import client from '../api/client';
import { synthesizeMigration, getLatestSynthesis } from '../api/plans';
import { useAssessments, useRunAssessment, useWorkloads } from '../api/hooks/useAssessments';
import ReadinessScoreBadge from '../components/ReadinessScoreBadge';
import WorkloadCard from '../components/WorkloadCard';
import ResourceMappingTable from '../components/ResourceMappingTable';

// ── Constants ──────────────────────────────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
  'AWS::EC2::VPC': 'badge badge-info',
  'AWS::EC2::Subnet': 'badge badge-info',
  'AWS::EC2::SecurityGroup': 'badge badge-info',
  'AWS::EC2::NetworkInterface': 'badge badge-info',
  'AWS::EC2::Instance': 'badge badge-success',
  'AWS::EC2::Volume': 'badge badge-success',
  'AWS::AutoScaling::AutoScalingGroup': 'badge badge-success',
  'AWS::RDS::DBInstance': 'badge badge-accent',
  'AWS::ElasticLoadBalancingV2::LoadBalancer': 'badge badge-running',
  'AWS::IAM::Policy': 'badge badge-error',
  'AWS::IAM::Role': 'badge badge-error',
  'AWS::CloudFormation::Stack': 'badge badge-neutral',
  'AWS::Lambda::Function': 'badge badge-warning',
  CloudTrail: 'badge badge-warning',
};

const SKILL_MAP: Record<string, string> = {
  'AWS::EC2::VPC': 'network_translation',
  'AWS::EC2::Subnet': 'network_translation',
  'AWS::EC2::SecurityGroup': 'network_translation',
  'AWS::EC2::NetworkInterface': 'network_translation',
  'AWS::EC2::Instance': 'ec2_translation',
  'AWS::EC2::Volume': 'storage_translation',
  'AWS::AutoScaling::AutoScalingGroup': 'ec2_translation',
  'AWS::RDS::DBInstance': 'database_translation',
  'AWS::RDS::DBCluster': 'database_translation',
  'AWS::ElasticLoadBalancingV2::LoadBalancer': 'loadbalancer_translation',
  'AWS::IAM::Policy': 'iam_translation',
  'AWS::IAM::Role': 'iam_translation',
  'AWS::CloudFormation::Stack': 'cfn_terraform',
  CloudTrail: 'dependency_discovery',
};

const SKILL_LABELS: Record<string, string> = {
  network_translation: 'Network Translation (VPC/Subnets/SGs/ENIs → OCI VCN)',
  ec2_translation: 'EC2 Translation (EC2/ASG → OCI Compute)',
  storage_translation: 'Storage Translation (EBS → OCI Block Volume)',
  database_translation: 'Database Translation (RDS → OCI DB System)',
  loadbalancer_translation: 'Load Balancer Translation (ALB/NLB → OCI LB)',
  iam_translation: 'IAM Translation (AWS IAM → OCI IAM)',
  cfn_terraform: 'CloudFormation to Terraform (CFN → HCL)',
  dependency_discovery: 'Dependency Discovery (CloudTrail → Graph)',
};

type ActiveStep = 'discover' | 'assess' | 'plan' | 'migrate';

function migrationStatusBadge(status: string) {
  const map: Record<string, string> = {
    created: 'badge badge-neutral',
    extracting: 'badge badge-info',
    extracted: 'badge badge-success',
    planning: 'badge badge-warning',
    complete: 'badge badge-success',
    failed: 'badge badge-error',
  };
  return map[status] || 'badge badge-neutral';
}

function discoveryStatusBadge(status: string) {
  const map: Record<string, string> = {
    pending: 'badge badge-neutral',
    discovering: 'badge badge-running',
    discovered: 'badge badge-success',
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

function jobStatusBadge(status: string) {
  const map: Record<string, string> = {
    complete: 'badge badge-success',
    running: 'badge badge-running',
    failed: 'badge badge-error',
    queued: 'badge badge-neutral',
  };
  return map[status] || 'badge badge-neutral';
}

function getTypeBadgeClass(awsType: string): string {
  return TYPE_COLORS[awsType] || 'badge badge-neutral';
}

function shortType(awsType: string): string {
  const parts = awsType.split('::');
  return parts.length >= 3 ? parts.slice(1).join('::') : awsType;
}

function groupResourcesBySkill(resources: Resource[], selectedIds: Set<string>): Map<string, Resource[]> {
  const groups = new Map<string, Resource[]>();
  for (const r of resources) {
    if (!selectedIds.has(r.id)) continue;
    const skill = SKILL_MAP[r.aws_type] || 'cfn_terraform';
    const list = groups.get(skill) || [];
    list.push(r);
    groups.set(skill, list);
  }
  return groups;
}

// ── Resource Type Icon ─────────────────────────────────────────────────────────

function ResourceTypeIcon({ awsType }: { awsType: string }) {
  if (awsType.includes('EC2::VPC') || awsType.includes('EC2::Subnet') || awsType.includes('EC2::SecurityGroup') || awsType.includes('NetworkInterface')) {
    return (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
      </svg>
    );
  }
  if (awsType.includes('EC2::Instance') || awsType.includes('AutoScaling')) {
    return (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V5a2 2 0 00-2-2h-4M9 3v4m0-4h6m0 4H9m6-4v4" />
      </svg>
    );
  }
  if (awsType.includes('RDS')) {
    return (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7c0-1.657 3.582-3 8-3s8 1.343 8 3v10c0 1.657-3.582 3-8 3s-8-1.343-8-3V7z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 12c0 1.657 3.582 3 8 3s8-1.343 8-3" />
      </svg>
    );
  }
  if (awsType.includes('IAM')) {
    return (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
      </svg>
    );
  }
  if (awsType.includes('LoadBalanc')) {
    return (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
      </svg>
    );
  }
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
    </svg>
  );
}

// ── Step: Discover ─────────────────────────────────────────────────────────────

function DiscoverStep({
  migration,
  allResources,
  filteredResources,
  selectedIds,
  typeFilter,
  search,
  uniqueTypes,
  loadingResources,
  resourcesError,
  extracting,
  extractingInstance,
  extractError,
  instances,
  loadingInstances,
  instanceError,
  selectedInstance,
  showResources,
  allFilteredSelected,
  skillGroups,
  skillRunning,
  onToggle,
  onToggleAll,
  onRunSkill,
  onSetTypeFilter,
  onSetSearch,
  onSetExtractError,
  onExtractAll,
  onOpenInstanceModal,
  onExtractByInstance,
  onSetSelectedInstance,
  onSetShowResources,
  onUploadClick,
}: {
  migration: { id: string; name: string; status: string; discovery_status?: string; aws_connection_id?: string | null; created_at: string; resource_count?: number | null };
  allResources: Resource[];
  filteredResources: Resource[];
  selectedIds: Set<string>;
  typeFilter: string;
  search: string;
  uniqueTypes: string[];
  loadingResources: boolean;
  resourcesError: unknown;
  extracting: boolean;
  extractingInstance: boolean;
  extractError: string | null;
  instances: Resource[];
  loadingInstances: boolean;
  instanceError: string | null;
  selectedInstance: Resource | null;
  showResources: boolean;
  allFilteredSelected: boolean;
  skillGroups: Map<string, Resource[]>;
  skillRunning: boolean;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  onRunSkill: () => void;
  onSetTypeFilter: (v: string) => void;
  onSetSearch: (v: string) => void;
  onSetExtractError: (v: string | null) => void;
  onExtractAll: () => void;
  onOpenInstanceModal: () => void;
  onExtractByInstance: () => void;
  onSetSelectedInstance: (r: Resource | null) => void;
  onSetShowResources: (v: boolean) => void;
  onUploadClick: () => void;
}) {
  // Group resources by type for the type breakdown
  const resourcesByType = useMemo(() => {
    const groups = new Map<string, Resource[]>();
    for (const r of allResources) {
      const list = groups.get(r.aws_type) || [];
      list.push(r);
      groups.set(r.aws_type, list);
    }
    return Array.from(groups.entries()).sort((a, b) => b[1].length - a[1].length);
  }, [allResources]);

  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());

  const toggleType = (t: string) => {
    setExpandedTypes((prev) => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  };

  const isPending = migration.discovery_status === 'discovering';
  const hasPendingDiscovery = migration.discovery_status === 'pending' && allResources.length === 0;

  return (
    <div className="space-y-5">
      {/* Discovery in progress banner */}
      {isPending && (
        <div
          className="rounded-xl p-4"
          style={{ background: 'rgba(184,74,28,0.06)', border: '1px solid rgba(184,74,28,0.2)' }}
        >
          <div className="flex items-center gap-3">
            <span className="spinner flex-shrink-0" />
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>
                Discovering AWS resources…
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                Auto-scanning your AWS environment. This usually takes 30–60 seconds.
              </p>
            </div>
          </div>
          <div className="mt-3 rounded-full overflow-hidden" style={{ height: '3px', background: 'var(--color-rule)' }}>
            <div
              className="h-full rounded-full"
              style={{ width: '60%', background: 'var(--color-ember)', animation: 'shimmer 1.8s ease-in-out infinite' }}
            />
          </div>
        </div>
      )}

      {/* Manual discovery panel (no connection) */}
      {hasPendingDiscovery && (
        <div className="panel">
          <div className="panel-header">
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Resource Discovery</h3>
          </div>
          <div className="panel-body space-y-4">
            <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
              No AWS connection linked. Discover resources manually or upload a resource file.
            </p>
            {extractError && (
              <div className="alert alert-error" role="alert">
                {extractError}
                <button onClick={() => onSetExtractError(null)} className="ml-2 underline hover:no-underline text-xs">Dismiss</button>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <button onClick={onOpenInstanceModal} className="btn btn-secondary">Select Instance</button>
              {selectedInstance && (
                <span className="flex items-center gap-2 px-3 py-1.5 rounded text-xs" style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', color: '#16a34a' }}>
                  <span className="truncate max-w-[180px]">{selectedInstance.name || selectedInstance.aws_arn}</span>
                  <button onClick={() => onSetSelectedInstance(null)} className="flex-shrink-0 opacity-60 hover:opacity-100" aria-label="Clear instance">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </span>
              )}
              {selectedInstance && (
                <button onClick={onExtractByInstance} disabled={extractingInstance} className="btn btn-success">
                  {extractingInstance ? <><span className="spinner" />Discovering…</> : 'Discover Resources'}
                </button>
              )}
              <div className="w-px h-6 flex-shrink-0" style={{ background: 'var(--color-fence)' }} aria-hidden="true" />
              <button onClick={onExtractAll} disabled={extracting} className="btn btn-primary">
                {extracting ? <><span className="spinner" />Extracting…</> : 'Extract All Resources'}
              </button>
              <div className="w-px h-6 flex-shrink-0" style={{ background: 'var(--color-fence)' }} aria-hidden="true" />
              <button onClick={onUploadClick} className="btn btn-secondary">Upload Resource File</button>
            </div>
          </div>
        </div>
      )}

      {/* Resource type breakdown (expandable sections) */}
      {allResources.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
              Resource Breakdown
              <span className="ml-2 font-normal" style={{ color: 'var(--color-text-dim)' }}>
                {allResources.length} total across {resourcesByType.length} type{resourcesByType.length !== 1 ? 's' : ''}
              </span>
            </h3>
            <div className="flex items-center gap-2">
              <button
                onClick={onExtractAll}
                disabled={extracting || isPending}
                className="btn btn-secondary btn-sm"
                title="Re-run discovery to refresh resources from AWS"
              >
                {extracting || isPending ? <><span className="spinner" />Refreshing…</> : 'Re-discover'}
              </button>
              <button
                onClick={() => onSetShowResources(!showResources)}
                className="btn btn-ghost btn-sm"
              >
                {showResources ? 'Hide list' : 'Show full list'}
              </button>
            </div>
          </div>

          {resourcesByType.map(([type, resources]) => {
            const expanded = expandedTypes.has(type);
            return (
              <div
                key={type}
                className="rounded-xl overflow-hidden"
                style={{ border: '1px solid var(--color-rule)' }}
              >
                <button
                  onClick={() => toggleType(type)}
                  className="w-full flex items-center justify-between px-4 py-3 transition-colors text-left"
                  style={{ background: expanded ? 'var(--color-raised)' : 'var(--color-surface)' }}
                >
                  <div className="flex items-center gap-3">
                    <span style={{ color: 'var(--color-ember)' }}>
                      <ResourceTypeIcon awsType={type} />
                    </span>
                    <span className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>
                      {shortType(type)}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-semibold"
                      style={{ background: 'var(--color-ember-dim)', color: 'var(--color-ember)' }}
                    >
                      {resources.length}
                    </span>
                  </div>
                  <svg
                    className="w-4 h-4 transition-transform"
                    style={{
                      transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                      color: 'var(--color-rail)',
                    }}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>

                {expanded && (
                  <div style={{ borderTop: '1px solid var(--color-rule)', background: 'var(--color-well)' }}>
                    {resources.slice(0, 20).map((r) => (
                      <div
                        key={r.id}
                        className="flex items-center justify-between px-4 py-2.5 text-xs"
                        style={{ borderBottom: '1px solid var(--color-rule)' }}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(r.id)}
                            onChange={() => onToggle(r.id)}
                            className="cb"
                            aria-label={`Select ${r.name || r.aws_arn}`}
                          />
                          <span className="truncate font-medium" style={{ color: 'var(--color-text-bright)' }}>
                            {r.name || 'Unnamed'}
                          </span>
                          <span
                            className="truncate max-w-[180px] hidden sm:block"
                            style={{ color: 'var(--color-rail)', fontFamily: 'var(--font-mono)' }}
                          >
                            {r.aws_arn}
                          </span>
                        </div>
                        <span className={resourceStatusBadge(r.status)}>
                          <span className="badge-dot" />
                          {r.status}
                        </span>
                      </div>
                    ))}
                    {resources.length > 20 && (
                      <div className="px-4 py-2 text-xs" style={{ color: 'var(--color-text-dim)' }}>
                        +{resources.length - 20} more resources
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Full resource table (collapsible) */}
      {allResources.length > 0 && showResources && (
        <div className="panel">
          <div className="panel-header">
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
              All Resources
              <span className="ml-2 font-normal" style={{ color: 'var(--color-text-dim)' }}>
                {allResources.length} total{selectedIds.size > 0 && `, ${selectedIds.size} selected`}
              </span>
            </h3>
            <div className="flex items-center gap-2">
              <select
                value={typeFilter}
                onChange={(e) => onSetTypeFilter(e.target.value)}
                className="field-input field-select"
                style={{ width: 'auto', fontSize: '0.75rem', padding: '0.3125rem 2rem 0.3125rem 0.625rem' }}
                aria-label="Filter by type"
              >
                <option value="">All Types</option>
                {uniqueTypes.map((t) => <option key={t} value={t}>{shortType(t)}</option>)}
              </select>
              <div className="relative">
                <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--color-text-dim)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="text"
                  value={search}
                  onChange={(e) => onSetSearch(e.target.value)}
                  placeholder="Search…"
                  className="field-input"
                  style={{ paddingLeft: '2rem', width: '11rem', fontSize: '0.75rem', padding: '0.3125rem 0.625rem 0.3125rem 2rem' }}
                />
              </div>
            </div>
          </div>

          {selectedIds.size > 0 && (
            <div className="selection-bar">
              <p>
                {selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected
                {skillGroups.size > 1 && (
                  <span className="opacity-70"> · {skillGroups.size} translation job types</span>
                )}
              </p>
              <button onClick={onRunSkill} disabled={skillRunning} className="btn btn-primary btn-sm">
                {skillRunning ? <><span className="spinner" />Starting…</> : 'Run Translation Jobs'}
              </button>
            </div>
          )}

          {loadingResources ? (
            <div className="panel-body space-y-2">
              {[...Array(5)].map((_, i) => <div key={i} className="skel h-10" />)}
            </div>
          ) : resourcesError ? (
            <div className="alert alert-error m-4">Failed to load resources. Please try again.</div>
          ) : filteredResources.length === 0 ? (
            <div className="empty-state"><p>No resources match your filters.</p></div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="dt">
                <thead>
                  <tr>
                    <th style={{ width: '2.5rem' }}>
                      <input type="checkbox" checked={allFilteredSelected} onChange={onToggleAll} className="cb" aria-label="Select all" />
                    </th>
                    <th>Type</th>
                    <th>Name / ID</th>
                    <th>Status</th>
                    <th>Latest Run</th>
                    <th>Run Status</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredResources.map((r) => (
                    <tr key={r.id} style={selectedIds.has(r.id) ? { background: 'rgba(249,115,22,0.05)' } : undefined}>
                      <td>
                        <input type="checkbox" checked={selectedIds.has(r.id)} onChange={() => onToggle(r.id)} className="cb" aria-label={`Select ${r.name || r.aws_arn}`} />
                      </td>
                      <td><span className={getTypeBadgeClass(r.aws_type)}>{shortType(r.aws_type)}</span></td>
                      <td>
                        <p className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>{r.name || 'Unnamed'}</p>
                        <p className="text-xs truncate max-w-xs" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>{r.aws_arn}</p>
                      </td>
                      <td>
                        <span className={resourceStatusBadge(r.status)}><span className="badge-dot" />{r.status}</span>
                      </td>
                      <td>
                        {r.latest_skill_run ? (
                          <Link
                            to={r.latest_skill_run.status === 'complete' ? `/translation-jobs/${r.latest_skill_run.id}/results` : `/translation-jobs/${r.latest_skill_run.id}`}
                            style={{ color: 'var(--color-ember)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {r.latest_skill_run.skill_type}
                          </Link>
                        ) : <span style={{ color: 'var(--color-rail)' }}>—</span>}
                      </td>
                      <td>
                        {r.latest_skill_run ? (
                          <span className={jobStatusBadge(r.latest_skill_run.status)}><span className="badge-dot" />{r.latest_skill_run.status}</span>
                        ) : <span style={{ color: 'var(--color-rail)' }}>—</span>}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                        {r.latest_skill_run?.status === 'complete' ? `${Math.round(r.latest_skill_run.confidence * 100)}%` : <span style={{ color: 'var(--color-rail)' }}>—</span>}
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
  );
}

// ── Plan Results Display ─────────────────────────────────────────────────────

function PlanResults({ results }: { results: { resource_mapping?: Array<Record<string, unknown>>; artifacts?: Record<string, string>; skills_ran?: string[] } }) {
  const [activeTab, setActiveTab] = useState<string>('mapping');

  const mapping = results.resource_mapping || [];
  const artifacts = results.artifacts || {};

  // Build tabs from available artifacts
  const tabs: { id: string; label: string }[] = [
    { id: 'mapping', label: 'Resource Mapping' },
  ];

  // Group artifacts by category
  const synthesisArtifacts: Record<string, string> = {};
  const skillTfArtifacts: Record<string, string> = {};
  const dataMigArtifacts: Record<string, string> = {};
  const runbookArtifacts: Record<string, string> = {};

  for (const [key, content] of Object.entries(artifacts)) {
    if (key.startsWith('synthesis/')) {
      synthesisArtifacts[key.replace('synthesis/', '')] = content;
    } else if (key.startsWith('data_migration/')) {
      dataMigArtifacts[key.replace('data_migration/', '')] = content;
    } else if (key.startsWith('workload_planning/')) {
      runbookArtifacts[key.replace('workload_planning/', '')] = content;
    } else if (key !== 'resource-mapping.json') {
      // Individual skill outputs (ec2_translation/main.tf, etc.)
      skillTfArtifacts[key] = content;
    }
  }

  // Use synthesis if available, otherwise fall back to individual skill TF files
  const terraformArtifacts = Object.keys(synthesisArtifacts).length > 0
    ? synthesisArtifacts
    : skillTfArtifacts;

  if (Object.keys(terraformArtifacts).length > 0) tabs.push({ id: 'terraform', label: 'Terraform' });
  if (Object.keys(dataMigArtifacts).length > 0) tabs.push({ id: 'data', label: 'Data Migration' });
  if (Object.keys(runbookArtifacts).length > 0) tabs.push({ id: 'runbook', label: 'Runbook & Risks' });

  const currentTab = tabs.find(t => t.id === activeTab) ? activeTab : tabs[0]?.id;

  return (
    <div className="space-y-4">
      {/* Skills ran badge bar */}
      {results.skills_ran && results.skills_ran.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {results.skills_ran.map(s => (
            <span key={s} className="badge badge-success" style={{ fontSize: '0.5625rem' }}>
              {s.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-rule)', background: 'var(--color-surface)' }}>
        <div className="flex gap-0 px-2 pt-2" style={{ borderBottom: '1px solid var(--color-rule)' }}>
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className="px-4 py-2 text-xs font-medium transition-colors"
              style={{
                color: currentTab === tab.id ? 'var(--color-ember)' : 'var(--color-text-dim)',
                borderBottom: `2px solid ${currentTab === tab.id ? 'var(--color-ember)' : 'transparent'}`,
                background: 'transparent',
                border: 'none',
                borderBottomWidth: '2px',
                borderBottomStyle: 'solid',
                borderBottomColor: currentTab === tab.id ? 'var(--color-ember)' : 'transparent',
                cursor: 'pointer',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-4">
          {currentTab === 'mapping' && (
            <PlanMappingTable mapping={mapping} />
          )}
          {currentTab === 'terraform' && (
            <ArtifactList artifacts={terraformArtifacts} showDownloadAll downloadPrefix="terraform" />
          )}
          {currentTab === 'data' && (
            <ArtifactList artifacts={dataMigArtifacts} />
          )}
          {currentTab === 'runbook' && (
            <ArtifactList artifacts={runbookArtifacts} />
          )}
        </div>
      </div>
    </div>
  );
}

function PlanMappingTable({ mapping }: { mapping: Array<Record<string, unknown>> }) {
  const [detailIdx, setDetailIdx] = useState<number | null>(null);
  if (mapping.length === 0) return <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>No mapping data</p>;

  const detail = detailIdx !== null ? mapping[detailIdx] : null;

  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <th className="text-left px-3 py-2" style={{ color: 'var(--color-text-dim)' }}>AWS Resource</th>
              <th className="text-left px-1 py-2" />
              <th className="text-left px-3 py-2" style={{ color: 'var(--color-text-dim)' }}>OCI Target</th>
              <th className="text-center px-3 py-2" style={{ color: 'var(--color-text-dim)' }}>Confidence</th>
              <th className="text-center px-3 py-2" style={{ color: 'var(--color-text-dim)' }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {mapping.map((m, i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--color-rule)' }}>
                <td className="px-3 py-2">
                  <span className="font-medium" style={{ color: 'var(--color-text-bright)' }}>{String(m.aws_name || '')}</span>
                  <br />
                  <span style={{ color: 'var(--color-text-dim)', fontSize: '0.625rem' }}>{String(m.aws_config_summary || '')}</span>
                </td>
                <td className="px-1" style={{ color: 'var(--color-ember)' }}>→</td>
                <td className="px-3 py-2">
                  <span className="font-medium" style={{ color: '#F80000' }}>{String(m.oci_resource_type || '')}</span>
                  <br />
                  <span style={{ color: 'var(--color-text-dim)', fontSize: '0.625rem' }}>{String(m.oci_config_summary || '').slice(0, 60)}{String(m.oci_config_summary || '').length > 60 ? '…' : ''}</span>
                </td>
                <td className="px-3 py-2 text-center">
                  <span className="badge" style={{
                    fontSize: '0.5625rem',
                    background: m.mapping_confidence === 'high' ? 'rgba(22,163,74,0.1)' : m.mapping_confidence === 'medium' ? 'rgba(217,119,6,0.1)' : 'rgba(220,38,38,0.1)',
                    color: m.mapping_confidence === 'high' ? '#16a34a' : m.mapping_confidence === 'medium' ? '#d97706' : '#dc2626',
                  }}>
                    {String(m.mapping_confidence || 'low')}
                  </span>
                </td>
                <td className="px-3 py-2 text-center">
                  <button
                    onClick={() => setDetailIdx(i)}
                    className="text-xs font-medium"
                    style={{ color: 'var(--color-ember)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', fontFamily: 'inherit' }}
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detail popup */}
      {detail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }} onClick={() => setDetailIdx(null)}>
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', maxWidth: '640px', width: '90vw', maxHeight: '85vh', boxShadow: '0 25px 50px rgba(0,0,0,0.5)' }} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Resource Mapping Detail</h3>
              <button onClick={() => setDetailIdx(null)} style={{ background: 'var(--color-well)', border: 'none', cursor: 'pointer', borderRadius: '8px', width: '2rem', height: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-dim)' }}>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-5 py-4 overflow-auto" style={{ maxHeight: 'calc(85vh - 56px)' }}>
              {/* AWS side */}
              <div className="mb-4">
                <p className="text-xs font-semibold mb-1" style={{ color: 'var(--color-text-dim)' }}>AWS Source</p>
                <p className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>{String(detail.aws_name || '')}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>{String(detail.aws_type || '')}</p>
                {detail.aws_config_summary && (
                  <div className="mt-2 rounded-lg p-3" style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}>
                    <p className="text-xs" style={{ color: 'var(--color-text)', fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap' }}>{String(detail.aws_config_summary)}</p>
                  </div>
                )}
              </div>
              {/* Arrow */}
              <div className="flex items-center gap-2 mb-4">
                <div style={{ flex: 1, height: '1px', background: 'var(--color-rule)' }} />
                <span style={{ color: 'var(--color-ember)', fontWeight: 700, fontSize: '0.875rem' }}>→ OCI</span>
                <div style={{ flex: 1, height: '1px', background: 'var(--color-rule)' }} />
              </div>
              {/* OCI side */}
              <div className="mb-4">
                <p className="text-xs font-semibold mb-1" style={{ color: 'var(--color-text-dim)' }}>OCI Target</p>
                <p className="text-sm font-medium" style={{ color: '#F80000' }}>{String(detail.oci_resource_type || '')}</p>
                {detail.oci_shape && <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>{String(detail.oci_shape)}</p>}
                {detail.oci_config_summary && (
                  <div className="mt-2 rounded-lg p-3" style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}>
                    <p className="text-xs" style={{ color: 'var(--color-text)', lineHeight: 1.6 }}>{String(detail.oci_config_summary)}</p>
                  </div>
                )}
              </div>
              {/* Cost */}
              {(detail.aws_monthly_cost || detail.oci_monthly_cost) && (
                <div className="flex gap-4 mb-4 text-xs">
                  {detail.aws_monthly_cost && <span><span style={{ color: 'var(--color-text-dim)' }}>AWS: </span><span style={{ color: '#FF9900', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>${Number(detail.aws_monthly_cost).toFixed(2)}/mo</span></span>}
                  {detail.oci_monthly_cost && <span><span style={{ color: 'var(--color-text-dim)' }}>OCI: </span><span style={{ color: '#F80000', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>${Number(detail.oci_monthly_cost).toFixed(2)}/mo</span></span>}
                </div>
              )}
              {/* Notes */}
              {(detail.notes as string[] || []).length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-semibold mb-1.5" style={{ color: 'var(--color-success)' }}>Notes</p>
                  {(detail.notes as string[]).map((n, j) => (
                    <div key={j} className="text-xs mb-1 pl-3" style={{ color: 'var(--color-text)', borderLeft: '2px solid var(--color-success)', lineHeight: 1.5 }}>{n}</div>
                  ))}
                </div>
              )}
              {/* Gaps */}
              {(detail.gaps as string[] || []).length > 0 && (
                <div>
                  <p className="text-xs font-semibold mb-1.5" style={{ color: 'var(--color-warning)' }}>Gaps & Risks</p>
                  {(detail.gaps as string[]).map((g, j) => (
                    <div key={j} className="text-xs mb-1 pl-3" style={{ color: 'var(--color-text)', borderLeft: '2px solid var(--color-warning)', lineHeight: 1.5 }}>{g}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function _downloadFile(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function _downloadAll(artifacts: Record<string, string>, prefix: string) {
  // Download as individual files (simple approach)
  for (const [key, content] of Object.entries(artifacts)) {
    const name = key.split('/').pop() || key;
    _downloadFile(`${prefix}-${name}`, content);
  }
}

function _simpleMarkdown(md: string): string {
  // Minimal markdown → HTML for readable rendering
  return md
    .replace(/^### (.+)$/gm, '<h3 style="font-size:1rem;font-weight:700;margin:1.2em 0 0.5em;color:var(--color-text-bright)">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:1.15rem;font-weight:700;margin:1.5em 0 0.5em;color:var(--color-text-bright)">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="font-size:1.35rem;font-weight:700;margin:1.5em 0 0.5em;color:var(--color-text-bright)">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong style="color:var(--color-text-bright)">$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="background:var(--color-well);padding:1px 5px;border-radius:3px;font-size:0.8em;font-family:var(--font-mono)">$1</code>')
    .replace(/^```(\w*)\n([\s\S]*?)^```/gm, '<pre style="background:#0d1221;border:1px solid var(--color-fence);border-radius:8px;padding:12px;margin:8px 0;overflow-x:auto;font-size:0.75rem;font-family:var(--font-mono);color:#e2e8f0;line-height:1.5">$2</pre>')
    .replace(/^- \[x\] (.+)$/gm, '<div style="margin:2px 0">✅ $1</div>')
    .replace(/^- \[ \] (.+)$/gm, '<div style="margin:2px 0">☐ $1</div>')
    .replace(/^- (.+)$/gm, '<div style="margin:2px 0;padding-left:1em">• $1</div>')
    .replace(/^\d+\. (.+)$/gm, '<div style="margin:2px 0;padding-left:1em">$&</div>')
    .replace(/\n{2,}/g, '<br/><br/>')
    .replace(/\n/g, '<br/>');
}

function ArtifactList({ artifacts, showDownloadAll, downloadPrefix }: { artifacts: Record<string, string>; showDownloadAll?: boolean; downloadPrefix?: string }) {
  const [viewingFile, setViewingFile] = useState<{ name: string; content: string } | null>(null);
  const entries = Object.entries(artifacts);
  if (entries.length === 0) return <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>No artifacts</p>;

  return (
    <>
      {showDownloadAll && entries.length > 1 && (
        <div className="flex justify-end mb-2">
          <button onClick={() => _downloadAll(artifacts, downloadPrefix || 'plan')} className="btn btn-secondary btn-sm">
            <svg className="w-3.5 h-3.5 mr-1.5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            Download All
          </button>
        </div>
      )}
      <div className="space-y-1.5">
        {entries.map(([key, content]) => {
          const name = key.split('/').pop() || key;
          const isMd = name.endsWith('.md');
          return (
            <div key={key} className="flex items-center justify-between px-3 py-2.5 rounded-lg" style={{ border: '1px solid var(--color-rule)', background: 'var(--color-surface)' }}>
              <span className="flex items-center gap-2">
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-ember)', fontSize: '0.75rem' }}>{name}</span>
                <span style={{ color: 'var(--color-text-dim)', fontSize: '0.625rem' }}>
                  {content.length > 1000 ? `${(content.length / 1024).toFixed(1)} KB` : `${content.length} chars`}
                </span>
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setViewingFile({ name, content })}
                  className="text-xs font-medium"
                  style={{ color: 'var(--color-ember)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                >
                  View
                </button>
                <button
                  onClick={() => _downloadFile(name, content)}
                  className="text-xs font-medium"
                  style={{ color: 'var(--color-text-dim)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
                >
                  Download
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* File viewer modal */}
      {viewingFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }} onClick={() => setViewingFile(null)}>
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', maxWidth: '900px', width: '95vw', maxHeight: '90vh', boxShadow: '0 25px 50px rgba(0,0,0,0.5)' }} onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-ember)', fontSize: '0.875rem', fontWeight: 600 }}>{viewingFile.name}</span>
              <div className="flex items-center gap-2">
                <button onClick={() => _downloadFile(viewingFile.name, viewingFile.content)} className="btn btn-secondary btn-sm">Download</button>
                <button onClick={() => setViewingFile(null)} style={{ background: 'var(--color-well)', border: 'none', cursor: 'pointer', borderRadius: '8px', width: '2rem', height: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-dim)' }}>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
            </div>
            {/* Content */}
            <div className="overflow-auto" style={{ maxHeight: 'calc(90vh - 56px)' }}>
              {viewingFile.name.endsWith('.md') ? (
                <div
                  className="px-6 py-5"
                  style={{ color: 'var(--color-text)', fontSize: '0.8125rem', lineHeight: 1.7, fontFamily: 'var(--font-sans)' }}
                  dangerouslySetInnerHTML={{ __html: _simpleMarkdown(viewingFile.content) }}
                />
              ) : (
                <pre className="px-5 py-4 text-xs" style={{ background: '#0d1221', color: '#e2e8f0', fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.5 }}>
                  {viewingFile.content}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ── Step: Assess ──────────────────────────────────────────────────────────────

function AssessStep({
  migrationId,
  workloads,
  loadingWorkloads,
  latestAssessment,
  loadingAssessments,
  runAssessment,
  onPlanWorkload,
}: {
  migrationId: string;
  workloads: Array<{
    id?: string;
    name: string;
    workload_type?: string;
    resource_count?: number;
    resources: Array<{ id: string; aws_type: string; name?: string }>;
    readiness_score?: number;
    sixr_strategy?: string;
    total_aws_cost_usd?: number;
    total_oci_cost_usd?: number;
    grouping_method?: string;
  }> | undefined;
  loadingWorkloads: boolean;
  latestAssessment: {
    id: string;
    status: string;
    avg_readiness_score: number;
    resources_assessed: number;
    aws_monthly_cost: number;
    oci_projected_cost: number;
    current_step?: string | null;
    dependency_artifacts?: {
      workload_graphs?: Record<string, string>;
      cloudtrail_event_count?: number;
      has_flowlogs?: boolean;
    } | null;
  } | null;
  loadingAssessments: boolean;
  runAssessment: { mutate: (id: string) => void; isPending: boolean };
  onPlanWorkload: (workloadId: string) => void;
}) {
  const namedWorkloads = (workloads || []).filter((w) => w.name && !w.name.startsWith('ungrouped-'));
  const ungrouped = (workloads || []).filter((w) => w.name?.startsWith('ungrouped-'));

  return (
    <div className="space-y-5">
      {/* Assessment status bar */}
      <div
        className="rounded-xl p-4 flex items-start justify-between gap-4"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}
      >
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Migration Assessment</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
            Analyze readiness, cost comparison, and OS compatibility across all workloads
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => runAssessment.mutate(migrationId)}
            disabled={runAssessment.isPending || latestAssessment?.status === 'pending' || latestAssessment?.status === 'running'}
            className="btn btn-primary"
          >
            {runAssessment.isPending || latestAssessment?.status === 'pending' || latestAssessment?.status === 'running'
              ? <><span className="spinner" />Running…</>
              : latestAssessment?.status === 'complete'
                ? 'Re-run Assessment'
                : 'Run Assessment'}
          </button>
          {latestAssessment?.status === 'complete' && (
            <Link to={`/assessments/${latestAssessment.id}`} className="btn btn-secondary">
              Full Report →
            </Link>
          )}
        </div>
      </div>

      {/* Assessment summary */}
      {loadingAssessments ? (
        <div className="skel h-16 rounded-xl" />
      ) : latestAssessment?.status === 'running' || latestAssessment?.status === 'pending' ? (
        <div className="rounded-xl p-4" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)' }}>
          {(() => {
            const STEPS = [
              { key: 'collecting_metrics',   label: 'Collecting Metrics' },
              { key: 'collecting_inventory', label: 'Collecting Inventory' },
              { key: 'rightsizing',          label: 'Rightsizing' },
              { key: 'os_compatibility',     label: 'OS Compatibility' },
              { key: 'dependency_mapping',   label: 'Dependency Discovery' },
              { key: 'grouping',             label: 'Grouping' },
              { key: 'classifying',          label: 'Classifying' },
              { key: 'scoring',              label: 'Scoring' },
              { key: 'tco',                  label: 'TCO Calculation' },
            ];
            const currentIdx = STEPS.findIndex(s => s.key === latestAssessment.current_step);
            return (
              <>
                <div className="flex items-center gap-2 mb-3">
                  <span className="spinner flex-shrink-0" />
                  <span className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>
                    Assessment in progress
                  </span>
                  {latestAssessment.current_step && (
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--color-ember-dim)', color: 'var(--color-ember)' }}>
                      {STEPS.find(s => s.key === latestAssessment.current_step)?.label ?? latestAssessment.current_step}
                    </span>
                  )}
                </div>
                <div className="flex gap-1">
                  {STEPS.map((step, i) => {
                    const done = currentIdx >= 0 && i < currentIdx;
                    const active = i === currentIdx;
                    return (
                      <div key={step.key} className="flex-1 group relative">
                        <div
                          className="h-1.5 rounded-full"
                          style={{
                            background: done ? 'var(--color-ember)' : active ? 'var(--color-ember)' : 'var(--color-rule)',
                            opacity: active ? 1 : done ? 0.7 : 0.3,
                            animation: active ? 'shimmer 1.5s ease-in-out infinite' : undefined,
                          }}
                        />
                        <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                          <span className="text-xs px-2 py-1 rounded whitespace-nowrap" style={{ background: 'var(--color-raised)', color: 'var(--color-text-dim)', border: '1px solid var(--color-rule)' }}>
                            {step.label}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            );
          })()}
        </div>
      ) : latestAssessment?.status === 'complete' ? (
        <div
          className="grid gap-3 rounded-xl p-4"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', gridTemplateColumns: 'repeat(3, 1fr)' }}
        >
          <div className="text-center">
            <p className="text-xs mb-1" style={{ color: 'var(--color-text-dim)' }}>Readiness Score</p>
            <ReadinessScoreBadge score={Math.round(latestAssessment.avg_readiness_score)} />
          </div>
          <div className="text-center">
            <p className="text-xs mb-1" style={{ color: 'var(--color-text-dim)' }}>Resources Assessed</p>
            <p className="text-lg font-bold" style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-display)' }}>
              {latestAssessment.resources_assessed}
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs mb-1" style={{ color: 'var(--color-text-dim)' }}>Est. Cost Savings</p>
            <p className="text-lg font-bold" style={{ color: 'var(--color-success)', fontFamily: 'var(--font-display)' }}>
              {latestAssessment.aws_monthly_cost > 0
                ? `${Math.round(((latestAssessment.aws_monthly_cost - latestAssessment.oci_projected_cost) / latestAssessment.aws_monthly_cost) * 100)}%`
                : '—'}
            </p>
          </div>
        </div>
      ) : null}

      {/* Workload cards grid */}
      <div>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-bright)' }}>
          Detected Workloads
          {namedWorkloads.length > 0 && (
            <span className="ml-2 font-normal" style={{ color: 'var(--color-text-dim)' }}>
              {namedWorkloads.length} workload{namedWorkloads.length !== 1 ? 's' : ''}
            </span>
          )}
        </h3>

        {loadingWorkloads ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => <div key={i} className="skel rounded-xl" style={{ height: '200px' }} />)}
          </div>
        ) : namedWorkloads.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {namedWorkloads.map((w, i) => (
              <WorkloadCard
                key={w.id || i}
                name={w.name}
                workloadType={w.workload_type ?? 'web_api'}
                resourceCount={w.resource_count ?? 0}
                resources={w.resources}
                readinessScore={w.readiness_score}
                sixrStrategy={w.sixr_strategy}
                totalAwsCost={w.total_aws_cost_usd}
                totalOciCost={w.total_oci_cost_usd}
                groupingMethod={w.grouping_method}
                graphSvg={latestAssessment?.dependency_artifacts?.workload_graphs?.[w.name] || undefined}
                onClick={() => onPlanWorkload(w.id || w.name)}
              />
            ))}
          </div>
        ) : (
          <div className="panel">
            <div className="empty-state">
              <p>No workloads detected yet. Resources will be auto-grouped after discovery.</p>
            </div>
          </div>
        )}

        {/* Ungrouped */}
        {ungrouped.length > 0 && (
          <details className="panel mt-4" style={{ overflow: 'hidden' }}>
            <summary className="panel-body flex items-center gap-2 cursor-pointer" style={{ listStyle: 'none' }}>
              <svg className="w-3.5 h-3.5" style={{ color: 'var(--color-text-dim)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span className="text-sm font-medium" style={{ color: 'var(--color-text-dim)' }}>
                {ungrouped.length} ungrouped resource{ungrouped.length !== 1 ? 's' : ''}
              </span>
            </summary>
            <div className="panel-body pt-0 space-y-1.5" style={{ borderTop: '1px solid var(--color-rule)' }}>
              {ungrouped.map((w) =>
                w.resources.map((r) => (
                  <div key={r.id} className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-dim)' }}>
                    <span className="badge badge-neutral" style={{ fontSize: '0.5625rem' }}>{shortType(r.aws_type)}</span>
                    <span className="truncate">{r.name || r.id}</span>
                  </div>
                ))
              )}
            </div>
          </details>
        )}
      </div>

      {/* Translation jobs table */}
    </div>
  );
}

// ── Step: Plan ────────────────────────────────────────────────────────────────

function PlanStep({
  migrationId,
  workloads,
  latestAssessment,
  migrationSkillRuns,
  selectedWorkloadId,
  planStatus,
  planStartedAt,
  planMaxIterations,
}: {
  migrationId: string;
  workloads: Array<{
    id?: string;
    name: string;
    workload_type?: string;
    resource_count?: number;
    resources: Array<{ id: string; aws_type: string; name?: string }>;
    readiness_score?: number;
    sixr_strategy?: string;
  }> | undefined;
  latestAssessment: {
    id: string;
    status: string;
  } | null;
  migrationSkillRuns: Array<{
    id: string;
    status: string;
    skill_type: string;
    confidence: number;
    created_at: string;
    resource_names?: string[] | null;
    resource_name?: string | null;
    migration_id?: string | null;
  }>;
  selectedWorkloadId: string | null;
  planStatus?: string | null;
  planStartedAt?: string | null;
  planMaxIterations?: number | null;
}) {
  type PlanViewState = 'configure' | 'running' | 'results';

  const [maxIterations, setMaxIterations] = useState(3);
  const [viewState, setViewState] = useState<PlanViewState>(
    planStatus === 'running' ? 'running' : planStatus === 'completed' ? 'results' : 'configure'
  );
  const [planError, setPlanError] = useState<string | null>(null);
  const [planResults, setPlanResults] = useState<{
    status: string;
    current_step?: string;
    elapsed_seconds?: number;
    max_iterations?: number;
    logs?: string[];
    resource_mapping?: Array<Record<string, unknown>>;
    artifacts?: Record<string, string>;
    skills_ran?: string[];
    completed_at?: string;
  } | null>(null);
  const [elapsed, setElapsed] = useState(0);

  const namedWorkloads = (workloads || []).filter((w) => w.name && !w.name.startsWith('ungrouped-'));
  let selected = namedWorkloads.find(w => w.id === selectedWorkloadId || w.name === selectedWorkloadId);

  // Auto-select: if no workload selected but only one exists, pick it
  if (!selected && namedWorkloads.length === 1) {
    selected = namedWorkloads[0];
  }

  // Check for existing plan results when we have a selected workload
  useEffect(() => {
    if (!selected?.id) return;
    client.get(`/api/app-groups/${selected.id}/plan-results`)
      .then(res => {
        if (res.data?.status === 'completed') { setPlanResults(res.data); setViewState('results'); }
        else if (res.data?.status === 'running') { setPlanResults(res.data); setViewState('running'); }
      })
      .catch(() => {});
  }, [selected?.id]);

  // Poll while running
  useEffect(() => {
    if (viewState !== 'running' || !selected?.id) return;
    const interval = setInterval(async () => {
      try {
        const res = await client.get(`/api/app-groups/${selected.id}/plan-results`);
        setPlanResults(res.data);
        if (res.data?.status === 'completed') setViewState('results');
        else if (res.data?.status === 'failed') { setPlanError(res.data?.error || 'Failed'); setViewState('configure'); }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [viewState, selected?.id]);

  // Simple timer: compute elapsed from start time every second
  useEffect(() => {
    if (viewState !== 'running') return;
    const startMs = planStartedAt ? new Date(planStartedAt).getTime() : Date.now();
    const tick = () => setElapsed(Math.round((Date.now() - startMs) / 1000));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [viewState, planStartedAt]);

  const handleGeneratePlan = async () => {
    if (!latestAssessment || !selected?.id) return;
    setElapsed(0);
    setViewState('running');
    setPlanError(null);
    setPlanResults(null);
    try {
      await client.post(`/api/migrations/${migrationId}/plan-from-assessment`, {
        assessment_id: latestAssessment.id,
        app_group_ids: [selected.id],
        max_iterations: maxIterations,
      });
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : 'Failed to start');
      setViewState('configure');
    }
  };

  const fmtElapsed = (s: number) => { const total = Math.round(s); const m = Math.floor(total / 60); const sec = total % 60; return m > 0 ? `${m}m ${sec}s` : `${sec}s`; };

  // Workloads still loading
  if (!workloads && selectedWorkloadId) {
    return (
      <div className="flex items-center justify-center p-12">
        <span className="spinner" />
      </div>
    );
  }

  // No workload selected
  if (!selected) {
    return (
      <div className="rounded-xl p-8 text-center" style={{ background: 'var(--color-well)', border: '1px dashed var(--color-fence)' }}>
        <svg className="w-12 h-12 mx-auto mb-4" style={{ color: 'var(--color-rail)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 17l-5-5m0 0l5-5m-5 5h12" />
        </svg>
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>No workload selected</p>
        <p className="text-xs mt-1" style={{ color: 'var(--color-text-dim)' }}>Go to the Assess step and click "Plan Migration" on a workload.</p>
      </div>
    );
  }

  // ── CONFIGURE ───────────────────────────────────────────────────────
  if (viewState === 'configure') return (
    <div className="space-y-5">
      <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text-bright)' }}>{selected.name}</h3>
        <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
          {selected.resource_count || selected.resources.length} resources · {selected.workload_type?.replace('_', '/') || 'web/api'}
          {selected.sixr_strategy ? ` · ${selected.sixr_strategy}` : ''}
        </p>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {selected.resources.map(r => (
            <span key={r.id} className="badge badge-neutral" style={{ fontSize: '0.5625rem' }}>
              {r.aws_type.replace('AWS::', '').split('::').pop()} {r.name ? `· ${r.name}` : ''}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
        <h4 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-bright)' }}>Plan Configuration</h4>
        <div className="mb-4">
          <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--color-text-dim)' }}>LLM Debate Rounds (per skill)</label>
          <div className="flex items-center gap-3">
            <input type="range" min={1} max={5} value={maxIterations} onChange={e => setMaxIterations(Number(e.target.value))} className="flex-1" style={{ accentColor: 'var(--color-ember)' }} />
            <span className="text-sm font-bold w-6 text-center" style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}>{maxIterations}</span>
          </div>
          <p className="text-xs mt-1" style={{ color: 'var(--color-rail)' }}>
            {maxIterations === 1 ? 'Single pass — fastest, good for simple workloads' : maxIterations === 2 ? 'Enhancement + one review — good balance' : maxIterations === 3 ? 'Default — Enhancement → Review → Fix (recommended)' : maxIterations === 4 ? 'Extra refinement — catches edge cases' : 'Maximum quality — thorough but slower'}
          </p>
        </div>
        <div className="rounded-lg p-3 mb-4" style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}>
          <p className="text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-dim)' }}>Pipeline will run:</p>
          <div className="flex flex-wrap gap-1.5">
            {['Resource Mapping', 'Terraform Translation', 'Data Migration Plan', 'Migration Runbook', 'Risk Analysis', 'Synthesis'].map(s => (
              <span key={s} className="badge badge-neutral" style={{ fontSize: '0.5625rem' }}>{s}</span>
            ))}
          </div>
          <p className="text-xs mt-2" style={{ color: 'var(--color-rail)' }}>
            Estimated: {maxIterations <= 2 ? '2–4' : maxIterations <= 3 ? '4–8' : '8–15'} minutes
          </p>
        </div>
        {planError && <div className="alert alert-error mb-3">{planError}</div>}
        <button onClick={handleGeneratePlan} disabled={!latestAssessment} className="btn btn-primary">Generate Migration Plan</button>
      </div>
    </div>
  );

  // ── RUNNING ─────────────────────────────────────────────────────────
  if (viewState === 'running') {
    const currentStep = planResults?.current_step || 'init';
    const logs = planResults?.logs || [];
    const PIPELINE_STEPS = [
      { key: 'resource_mapping', label: 'Resource Mapping' },
      { key: 'ec2_translation', label: 'EC2 Translation' },
      { key: 'storage_translation', label: 'Storage Translation' },
      { key: 'cfn_terraform', label: 'CloudFormation → Terraform' },
      { key: 'data_migration', label: 'Data Migration' },
      { key: 'workload_planning', label: 'Runbook & Risk Analysis' },
      { key: 'synthesis', label: 'Merge Terraform' },
    ];
    const PIPELINE = PIPELINE_STEPS.map(s => s.key);
    const stepIdx = PIPELINE.indexOf(currentStep);

    return (
      <div className="space-y-5">
        <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <span className="spinner flex-shrink-0" />
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Generating plan for {selected.name}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                  {currentStep.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())} · {planMaxIterations ?? planResults?.max_iterations ?? maxIterations} round{(planMaxIterations ?? planResults?.max_iterations ?? maxIterations) > 1 ? 's' : ''} per skill
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-lg font-bold" style={{ color: 'var(--color-ember)', fontFamily: 'var(--font-mono)' }}>{fmtElapsed(elapsed)}</p>
                <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>elapsed</p>
              </div>
              <button
                onClick={async () => {
                  if (!selected?.id) return;
                  try {
                    await client.post(`/api/app-groups/${selected.id}/cancel-plan`);
                  } catch { /* ignore */ }
                  setPlanResults(null);
                  setViewState('configure');
                }}
                className="btn btn-secondary btn-sm"
                style={{ color: 'var(--color-error)' }}
              >
                Cancel
              </button>
            </div>
          </div>
          <div className="flex gap-1">
            {PIPELINE_STEPS.map((step, i) => (
              <div key={step.key} className="flex-1 group relative">
                <div className="h-2 rounded-full transition-all" style={{
                  background: i <= stepIdx ? 'var(--color-ember)' : 'var(--color-rule)',
                  opacity: i < stepIdx ? 0.7 : i === stepIdx ? 1 : 0.3,
                  animation: i === stepIdx ? 'shimmer 1.5s ease-in-out infinite' : undefined,
                }} />
                <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                  <span className="text-xs px-2 py-1 rounded whitespace-nowrap" style={{ background: 'var(--color-raised)', color: 'var(--color-text-dim)', border: '1px solid var(--color-rule)' }}>
                    {step.label}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-rule)' }}>
          <div className="px-4 py-2.5 flex items-center justify-between" style={{ background: 'var(--color-raised)', borderBottom: '1px solid var(--color-rule)' }}>
            <span className="text-xs font-semibold" style={{ color: 'var(--color-text-dim)' }}>Live Logs</span>
            <span className="text-xs" style={{ color: 'var(--color-rail)', fontFamily: 'var(--font-mono)' }}>{logs.length} entries</span>
          </div>
          <div className="p-3 overflow-auto" style={{ maxHeight: '300px', background: '#0d1221', fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', lineHeight: 1.6 }}>
            {logs.length === 0
              ? <p style={{ color: 'var(--color-rail)' }}>Waiting for logs…</p>
              : logs.map((line, i) => (
                  <div key={i} style={{ color: line.includes('complete') || line.includes('Complete') ? '#16a34a' : line.includes('failed') || line.includes('Failed') ? '#dc2626' : '#94a3b8' }}>{line}</div>
                ))}
          </div>
        </div>
      </div>
    );
  }

  // ── RESULTS ─────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <svg className="w-5 h-5" style={{ color: '#16a34a' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>{selected.name} — Plan Ready</h3>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
              {planResults?.skills_ran?.length || 0} skills · {planResults?.elapsed_seconds ? fmtElapsed(Math.round(planResults.elapsed_seconds)) : ''} · {planResults?.completed_at ? formatDate(planResults.completed_at) : ''}
            </p>
          </div>
          <button onClick={() => { setViewState('configure'); setPlanResults(null); }} className="btn btn-secondary">Regenerate</button>
        </div>
      </div>
      {planResults && <PlanResults results={planResults} />}
    </div>
  );
}

// ── Step: Migrate ────────────────────────────────────────────────────────────

function MigrateStep({ migrationId, migration }: {
  migrationId: string;
  migration?: { migrate_status?: string | null; migrate_workload_name?: string | null; migrate_started_at?: string | null; migrate_current_step?: string | null; migrate_terraform_plan?: string | null; migrate_logs?: string[] | null; plan_status?: string | null; plan_workload_id?: string | null; plan_workload_name?: string | null } | null;
}) {
  const [ociConnections, setOciConnections] = useState<Array<{id: string; name: string; region: string; compartment_id?: string}>>([]);
  const [selectedOciConn, setSelectedOciConn] = useState('');
  const [variableOverrides, setVariableOverrides] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [showPreview, setShowPreview] = useState(false);
  const [previewFiles, setPreviewFiles] = useState<Record<string, string>>({});

  const status = migration?.migrate_status;
  const logs = migration?.migrate_logs || [];
  const tfPlan = migration?.migrate_terraform_plan;
  const currentStep = migration?.migrate_current_step;

  // Load OCI connections
  useEffect(() => {
    client.get('/api/oci-connections').then(res => setOciConnections(res.data)).catch(() => {});
  }, []);

  // Elapsed timer
  useEffect(() => {
    if (!migration?.migrate_started_at || !status || ['completed', 'failed', 'rolled_back', 'rejected'].includes(status)) return;
    const startMs = new Date(migration.migrate_started_at).getTime();
    const tick = () => setElapsed(Math.round((Date.now() - startMs) / 1000));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [status, migration?.migrate_started_at]);

  const fmtElapsed = (s: number) => { const m = Math.floor(s / 60); const sec = s % 60; return m > 0 ? `${m}m ${sec}s` : `${sec}s`; };

  const handlePreview = async () => {
    if (!selectedOciConn) { setError('Select an OCI connection'); return; }
    setError(null);
    // Load the plan artifacts to show .tf files
    try {
      const wName = migration?.plan_workload_name || '';
      const res = await client.get(`/api/app-groups/${migration?.plan_workload_id || ''}/plan-results`);
      const artifacts = res.data?.artifacts || {};
      // Extract only synthesis .tf files, or fall back to individual skill .tf files
      const tfFiles: Record<string, string> = {};
      const hasSynthesis = Object.keys(artifacts).some(k => k.startsWith('synthesis/') && k.endsWith('.tf'));
      for (const [key, content] of Object.entries(artifacts)) {
        if (typeof content !== 'string') continue;
        if (hasSynthesis) {
          if (key.startsWith('synthesis/') && key.endsWith('.tf')) {
            tfFiles[key.replace('synthesis/', '')] = content;
          }
        } else if (key.endsWith('.tf')) {
          tfFiles[key] = content;
        }
      }
      setPreviewFiles(tfFiles);
      setShowPreview(true);
    } catch {
      setError('Failed to load plan artifacts for preview');
    }
  };

  const handleConfirmStart = async () => {
    setError(null);
    try {
      await client.post(`/api/migrations/${migrationId}/execute`, {
        workload_name: migration?.plan_workload_name || '',
        oci_connection_id: selectedOciConn,
        variable_overrides: variableOverrides,
      });
    } catch (err: unknown) {
      setError((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to start');
    }
  };

  const handleApprove = async () => {
    try { await client.post(`/api/migrations/${migrationId}/approve-plan`); } catch { setError('Failed to approve'); }
  };

  const handleReject = async () => {
    try { await client.post(`/api/migrations/${migrationId}/reject-plan`); } catch { setError('Failed to reject'); }
  };

  const handleRollback = async () => {
    if (!confirm('This will run terraform destroy and delete all created OCI resources. Continue?')) return;
    try { await client.post(`/api/migrations/${migrationId}/rollback`); } catch { setError('Failed to rollback'); }
  };

  // No plan completed
  if (!migration?.plan_status || migration.plan_status !== 'completed') {
    return (
      <div className="rounded-xl p-8 text-center" style={{ background: 'var(--color-well)', border: '1px dashed var(--color-fence)' }}>
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>Plan not ready</p>
        <p className="text-xs mt-1" style={{ color: 'var(--color-text-dim)' }}>Complete the Plan step first before migrating.</p>
      </div>
    );
  }

  // ── CONFIGURE (or PREVIEW if showPreview is set) ─────────────────────
  if (showPreview && (!status || status === 'rejected')) {
    const fileEntries = Object.entries(previewFiles).sort(([a], [b]) => a.localeCompare(b));
    return (
      <div className="space-y-5">
        <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Review Terraform Files</h3>
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                These {fileEntries.length} files will be applied to your OCI tenancy. Review before proceeding.
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowPreview(false)} className="btn btn-secondary">Back</button>
              <button onClick={handleConfirmStart} className="btn btn-primary">Confirm & Run Terraform</button>
            </div>
          </div>
          {error && <div className="alert alert-error mb-4">{error}</div>}
          <div className="space-y-3">
            {fileEntries.map(([name, content]) => (
              <details key={name} className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-rule)' }}>
                <summary className="flex items-center justify-between px-3 py-2.5 cursor-pointer" style={{ background: 'var(--color-raised)' }}>
                  <span className="flex items-center gap-2">
                    <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-ember)', fontSize: '0.75rem', fontWeight: 600 }}>{name}</span>
                    <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>{(content.length / 1024).toFixed(1)} KB</span>
                  </span>
                </summary>
                <pre className="px-3 py-3 overflow-auto text-xs" style={{
                  maxHeight: '400px', background: '#0d1221', color: '#e2e8f0',
                  fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.5,
                }}>{content}</pre>
              </details>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!status || status === 'rejected') {
    return (
      <div className="space-y-5">
        <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
          <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text-bright)' }}>Execute Migration</h3>
          <p className="text-xs mb-4" style={{ color: 'var(--color-text-dim)' }}>
            Apply the generated Terraform to create resources in OCI for workload: <strong>{migration.plan_workload_name}</strong>
          </p>

          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--color-text-dim)' }}>OCI Connection</label>
              {ociConnections.length === 0 ? (
                <p className="text-xs" style={{ color: 'var(--color-warning)' }}>
                  No OCI connections found. <a href="/connections" style={{ color: 'var(--color-ember)', textDecoration: 'underline' }}>Add one</a> first.
                </p>
              ) : (
                <select value={selectedOciConn} onChange={e => setSelectedOciConn(e.target.value)} className="field-input field-select">
                  <option value="">Select connection…</option>
                  {ociConnections.map(c => <option key={c.id} value={c.id}>{c.name} ({c.region})</option>)}
                </select>
              )}
            </div>

            <div>
              <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--color-text-dim)' }}>Variable Overrides <span style={{ color: 'var(--color-rail)' }}>(optional)</span></label>
              <div className="grid grid-cols-2 gap-2">
                {['compartment_id', 'ssh_public_key', 'availability_domain'].map(key => (
                  <div key={key}>
                    <label className="text-xs" style={{ color: 'var(--color-rail)', fontFamily: 'var(--font-mono)' }}>{key}</label>
                    <input
                      type="text"
                      value={variableOverrides[key] || ''}
                      onChange={e => setVariableOverrides(prev => ({ ...prev, [key]: e.target.value }))}
                      placeholder={key === 'compartment_id' ? 'ocid1.compartment...' : key === 'ssh_public_key' ? 'ssh-rsa AAAA...' : 'AD-1'}
                      className="field-input"
                      style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          {error && <div className="alert alert-error mt-3">{error}</div>}

          <button onClick={handlePreview} disabled={!selectedOciConn} className="btn btn-primary mt-4">
            Preview & Start Migration
          </button>
        </div>
      </div>
    );
  }

  // ── REVIEW (terraform plan) ─────────────────────────────────────────
  if (status === 'review') {
    return (
      <div className="space-y-5">
        <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
          <div className="flex items-center gap-2 mb-3">
            <svg className="w-5 h-5" style={{ color: '#d97706' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Review Terraform Plan</h3>
          </div>
          <p className="text-xs mb-4" style={{ color: 'var(--color-text-dim)' }}>
            Review the resources that will be created in OCI. Approve to proceed with apply, or reject to go back.
          </p>

          {/* Terraform plan output */}
          <div className="rounded-lg overflow-hidden mb-4" style={{ border: '1px solid var(--color-rule)' }}>
            <div className="px-3 py-2" style={{ background: 'var(--color-raised)', borderBottom: '1px solid var(--color-rule)' }}>
              <span className="text-xs font-semibold" style={{ color: 'var(--color-text-dim)' }}>terraform plan</span>
            </div>
            <pre className="p-3 overflow-auto text-xs" style={{
              maxHeight: '500px', background: '#0d1221', color: '#e2e8f0',
              fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.5,
            }}>
              {(tfPlan || '').split('\n').map((line, i) => (
                <div key={i} style={{
                  color: line.startsWith('+') ? '#16a34a' : line.startsWith('-') ? '#dc2626' : line.startsWith('~') ? '#d97706' : '#94a3b8',
                }}>{line}</div>
              ))}
            </pre>
          </div>

          <div className="flex gap-3">
            <button onClick={handleApprove} className="btn btn-primary">
              Approve & Apply
            </button>
            <button onClick={handleReject} className="btn btn-secondary">
              Reject
            </button>
          </div>
          {error && <div className="alert alert-error mt-3">{error}</div>}
        </div>
      </div>
    );
  }

  // ── RUNNING / APPLYING ──────────────────────────────────────────────
  if (['running', 'approved', 'applying'].includes(status || '')) {
    const STEPS = ['preflight', 'workspace', 'init', 'plan', 'review', 'apply', 'complete'];
    const stepIdx = STEPS.indexOf(currentStep || 'preflight');

    return (
      <div className="space-y-5">
        <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <span className="spinner flex-shrink-0" />
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                  {status === 'applying' ? 'Applying Terraform' : 'Running Migration'}
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                  {(currentStep || 'starting').replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())}
                </p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-lg font-bold" style={{ color: '#7c3aed', fontFamily: 'var(--font-mono)' }}>{fmtElapsed(elapsed)}</p>
              <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>elapsed</p>
            </div>
          </div>

          <div className="flex gap-1">
            {STEPS.map((step, i) => (
              <div key={step} className="flex-1 group relative">
                <div className="h-2 rounded-full transition-all" style={{
                  background: i <= stepIdx ? '#7c3aed' : 'var(--color-rule)',
                  opacity: i < stepIdx ? 0.7 : i === stepIdx ? 1 : 0.3,
                  animation: i === stepIdx ? 'shimmer 1.5s ease-in-out infinite' : undefined,
                }} />
                <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-10">
                  <span className="text-xs px-2 py-1 rounded whitespace-nowrap" style={{ background: 'var(--color-raised)', color: 'var(--color-text-dim)', border: '1px solid var(--color-rule)' }}>
                    {step}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Live logs */}
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-rule)' }}>
          <div className="px-4 py-2.5 flex items-center justify-between" style={{ background: 'var(--color-raised)', borderBottom: '1px solid var(--color-rule)' }}>
            <span className="text-xs font-semibold" style={{ color: 'var(--color-text-dim)' }}>Terminal Output</span>
            <span className="text-xs" style={{ color: 'var(--color-rail)', fontFamily: 'var(--font-mono)' }}>{logs.length} lines</span>
          </div>
          <div className="p-3 overflow-auto" style={{ maxHeight: '400px', background: '#0d1221', fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', lineHeight: 1.6 }}>
            {logs.length === 0 ? <p style={{ color: 'var(--color-rail)' }}>Waiting…</p> : logs.map((line, i) => (
              <div key={i} style={{ color: line.includes('✓') || line.includes('complete') ? '#16a34a' : line.includes('failed') || line.includes('FATAL') ? '#dc2626' : '#94a3b8' }}>{line}</div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── COMPLETED ───────────────────────────────────────────────────────
  if (status === 'completed') {
    return (
      <div className="space-y-5">
        <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2">
              <svg className="w-6 h-6" style={{ color: '#16a34a' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Migration Complete</h3>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                  Resources created in OCI for {migration.migrate_workload_name}
                </p>
              </div>
            </div>
            <button onClick={handleRollback} className="btn btn-secondary btn-sm" style={{ color: 'var(--color-error)' }}>
              Rollback (Destroy)
            </button>
          </div>
        </div>

        {/* Logs */}
        <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-rule)' }}>
          <div className="px-4 py-2.5" style={{ background: 'var(--color-raised)', borderBottom: '1px solid var(--color-rule)' }}>
            <span className="text-xs font-semibold" style={{ color: 'var(--color-text-dim)' }}>Execution Log</span>
          </div>
          <div className="p-3 overflow-auto" style={{ maxHeight: '300px', background: '#0d1221', fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', lineHeight: 1.6 }}>
            {logs.map((line, i) => (
              <div key={i} style={{ color: line.includes('complete') || line.includes('✓') ? '#16a34a' : line.includes('failed') ? '#dc2626' : '#94a3b8' }}>{line}</div>
            ))}
          </div>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
      </div>
    );
  }

  // ── FAILED / ROLLING BACK ──────────────────────────────────────────
  return (
    <div className="space-y-5">
      <div className="rounded-xl p-5" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <svg className="w-6 h-6" style={{ color: status === 'rolling_back' ? '#d97706' : '#dc2626' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                {status === 'rolling_back' ? 'Rolling Back…' : status === 'rolled_back' ? 'Rolled Back' : 'Migration Failed'}
              </h3>
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>{migration.migrate_workload_name}</p>
            </div>
          </div>
          <div className="flex gap-2">
            {status === 'failed' && (
              <>
                <button onClick={handlePreview} className="btn btn-primary btn-sm">Retry</button>
                <button onClick={handleRollback} className="btn btn-secondary btn-sm" style={{ color: 'var(--color-error)' }}>Rollback</button>
              </>
            )}
            {status === 'rolling_back' && <span className="spinner" />}
          </div>
        </div>
      </div>

      <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-rule)' }}>
        <div className="px-4 py-2.5" style={{ background: 'var(--color-raised)', borderBottom: '1px solid var(--color-rule)' }}>
          <span className="text-xs font-semibold" style={{ color: 'var(--color-text-dim)' }}>Execution Log</span>
        </div>
        <div className="p-3 overflow-auto" style={{ maxHeight: '300px', background: '#0d1221', fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', lineHeight: 1.6 }}>
          {logs.map((line, i) => (
            <div key={i} style={{ color: line.includes('complete') ? '#16a34a' : line.includes('failed') || line.includes('FATAL') ? '#dc2626' : '#94a3b8' }}>{line}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export default function MigrationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: migration, isLoading: loadingMigration, error: migrationError } = useMigration(id || '');
  const { data: resources, isLoading: loadingResources, error: resourcesError } = useResources({ migration_id: id });

  const [skillRunErrors, setSkillRunErrors] = useState<string[]>([]);
  const [skillRunning, setSkillRunning] = useState(false);
  const uploadToMigration = useUploadToMigration();
  const deleteMigration = useDeleteMigration();

  const { data: assessments, isLoading: loadingAssessments } = useAssessments(id || '');
  const runAssessment = useRunAssessment();
  const latestAssessment = assessments?.length ? assessments[0] : null;

  const { data: workloads, isLoading: loadingWorkloads } = useWorkloads(
    migration?.discovery_status === 'discovered' ? (id || '') : ''
  );

  // Invalidate workloads whenever the latest assessment transitions to completed
  const prevAssessmentStatus = useRef<string | null>(null);
  useEffect(() => {
    const status = latestAssessment?.status ?? null;
    if (prevAssessmentStatus.current !== null &&
        prevAssessmentStatus.current !== 'completed' &&
        status === 'completed') {
      queryClient.invalidateQueries({ queryKey: ['workloads', id] });
    }
    prevAssessmentStatus.current = status;
  }, [latestAssessment?.status, id, queryClient]);

  const { data: allSkillRuns } = useTranslationJobs();
  const migrationSkillRuns = useMemo(
    () => (allSkillRuns || []).filter((sr) => sr.migration_id === id),
    [allSkillRuns, id]
  );

  type SynthesisJob = { id: string; status: string; confidence: number; current_phase?: string | null; created_at?: string; completed_at?: string | null; errors?: Record<string, unknown> | null };
  const [synthesisJob, setSynthesisJob] = useState<SynthesisJob | null>(null);
  const [loadingSynthesis, setLoadingSynthesis] = useState(true);
  const [synthesizing, setSynthesizing] = useState(false);
  const [synthesisError, setSynthesisError] = useState<string | null>(null);

  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignSelectedIds, setAssignSelectedIds] = useState<Set<string>>(new Set());
  const [extractedResources, setExtractedResources] = useState<{id: string; name: string; aws_type: string}[]>([]);
  const [assigning, setAssigning] = useState(false);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [extractingInstance, setExtractingInstance] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [showResources, setShowResources] = useState(false);

  const [showInstanceModal, setShowInstanceModal] = useState(false);
  const [instances, setInstances] = useState<Resource[]>([]);
  const [loadingInstances, setLoadingInstances] = useState(false);
  const [instanceError, setInstanceError] = useState<string | null>(null);
  const [selectedInstance, setSelectedInstance] = useState<Resource | null>(null);

  const [showSkillModal, setShowSkillModal] = useState(false);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadFileType, setUploadFileType] = useState('CloudTrail');
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sidebar step state — persisted in URL search params
  const [searchParams, setSearchParams] = useSearchParams();
  const activeStep = (searchParams.get('step') as ActiveStep) || 'discover';
  const planSelectedWorkload = searchParams.get('workload');

  const setActiveStep = useCallback((step: ActiveStep) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('step', step);
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const setPlanSelectedWorkload = useCallback((wid: string | null) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (wid) next.set('workload', wid);
      else next.delete('workload');
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const fetchSynthesis = useCallback(async () => {
    if (!id) return;
    try {
      const job = await getLatestSynthesis(id);
      setSynthesisJob(job);
    } catch {
      setSynthesisJob(null);
    } finally {
      setLoadingSynthesis(false);
    }
  }, [id]);

  useEffect(() => { fetchSynthesis(); }, [fetchSynthesis]);

  useEffect(() => {
    if (!synthesisJob || synthesisJob.status === 'complete' || synthesisJob.status === 'failed') return;
    const interval = setInterval(fetchSynthesis, 3000);
    return () => clearInterval(interval);
  }, [synthesisJob?.status, fetchSynthesis]);

  const handleGeneratePlan = async () => {
    if (!id) return;
    setSynthesizing(true);
    setSynthesisError(null);
    try {
      const result = await synthesizeMigration(id);
      setSynthesisJob({ id: result.translation_job_id, status: 'queued', confidence: 0 });
      queryClient.invalidateQueries({ queryKey: ['translation-jobs'] });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to generate migration plan';
      setSynthesisError(msg);
    } finally {
      setSynthesizing(false);
    }
  };

  const allResources = resources || [];
  const uniqueTypes = useMemo(() => {
    const types = new Set<string>();
    for (const r of allResources) types.add(r.aws_type);
    return Array.from(types).sort();
  }, [allResources]);

  const filteredResources = useMemo(() => {
    let list = allResources;
    if (typeFilter) list = list.filter((r) => r.aws_type === typeFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((r) =>
        r.name.toLowerCase().includes(q) ||
        r.aws_arn.toLowerCase().includes(q) ||
        r.aws_type.toLowerCase().includes(q)
      );
    }
    return list;
  }, [allResources, typeFilter, search]);

  const allFilteredSelected = useMemo(
    () => filteredResources.length > 0 && filteredResources.every((r) => selectedIds.has(r.id)),
    [filteredResources, selectedIds]
  );

  const skillGroups = useMemo(
    () => groupResourcesBySkill(allResources, selectedIds),
    [allResources, selectedIds]
  );

  const toggleSelect = useCallback((resourceId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(resourceId)) next.delete(resourceId); else next.add(resourceId);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (allFilteredSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const r of filteredResources) next.delete(r.id);
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const r of filteredResources) next.add(r.id);
        return next;
      });
    }
  }, [allFilteredSelected, filteredResources]);

  const openAssignModal = async (scopedIds: string[]) => {
    try {
      if (scopedIds.length > 0) {
        const resResponse = await client.get('/api/aws/resources');
        const scopedSet = new Set(scopedIds);
        const scoped: {id: string; name: string; aws_type: string}[] = resResponse.data
          .filter((r: { id: string }) => scopedSet.has(r.id))
          .map((r: { id: string; name?: string; aws_arn?: string; aws_type?: string }) => ({ id: r.id, name: r.name || r.aws_arn || r.id, aws_type: r.aws_type || '' }));
        if (scoped.length === 0) { setExtractError('No resources found for this instance.'); return; }
        setExtractedResources(scoped);
        setAssignSelectedIds(new Set(scoped.map((r) => r.id)));
      } else {
        const resResponse = await client.get('/api/resources/unassigned');
        const unassigned: {id: string; name: string; aws_type: string}[] = resResponse.data.map(
          (r: { id: string; name?: string; aws_arn?: string; aws_type?: string }) => ({ id: r.id, name: r.name || r.aws_arn || r.id, aws_type: r.aws_type || '' })
        );
        if (unassigned.length === 0) { setExtractError('No unassigned resources found.'); return; }
        setExtractedResources(unassigned);
        setAssignSelectedIds(new Set(unassigned.map((r) => r.id)));
      }
      setShowAssignModal(true);
    } catch {
      setExtractError('Failed to load resources.');
    }
  };

  const handleExtractAll = async () => {
    if (!id) return;
    setExtracting(true);
    setExtractError(null);
    try {
      const response = await client.post(`/api/migrations/${id}/extract`);
      await queryClient.invalidateQueries({ queryKey: ['resources'] });
      await openAssignModal(response.data.resource_ids ?? []);
    } catch (err: unknown) {
      setExtractError(err instanceof Error ? err.message : 'Failed to extract resources');
    } finally {
      setExtracting(false);
    }
  };

  const handleExtractByInstance = async () => {
    if (!id || !selectedInstance) return;
    setExtractingInstance(true);
    setExtractError(null);
    try {
      const response = await client.post(`/api/migrations/${id}/extract/instance?resource_id=${selectedInstance.id}`);
      await queryClient.invalidateQueries({ queryKey: ['resources'] });
      await openAssignModal(response.data.resource_ids ?? []);
    } catch (err: unknown) {
      setExtractError(err instanceof Error ? err.message : 'Failed to extract resources');
    } finally {
      setExtractingInstance(false);
    }
  };

  const handleOpenInstanceModal = async () => {
    setShowInstanceModal(true);
    setLoadingInstances(true);
    setInstanceError(null);
    try {
      let res = await client.get('/api/aws/resources', { params: { type: 'AWS::EC2::Instance' } });
      if (res.data.length === 0 && migration?.aws_connection_id) {
        await client.post(`/api/migrations/${id}/extract`);
        res = await client.get('/api/aws/resources', { params: { type: 'AWS::EC2::Instance' } });
      }
      setInstances(res.data);
    } catch (err: unknown) {
      setInstanceError(err instanceof Error ? err.message : 'Failed to fetch instances');
      setInstances([]);
    } finally {
      setLoadingInstances(false);
    }
  };

  const handleRunSkill = () => { if (selectedIds.size === 0) return; setShowSkillModal(true); };

  const handleConfirmSkillRun = async () => {
    const requests: Array<{ skillType: string; label: string; payload: object }> = [];
    for (const [skillType, groupResources] of skillGroups.entries()) {
      if (skillType === 'cfn_terraform') {
        for (const r of groupResources) {
          requests.push({
            skillType,
            label: `${skillType}:${r.name || r.id}`,
            payload: { skill_type: skillType, migration_id: id, input_resource_id: r.id, config: { resource_ids: [r.id], max_iterations: 3 } },
          });
        }
      } else {
        requests.push({
          skillType,
          label: skillType,
          payload: { skill_type: skillType, migration_id: id, input_resource_id: groupResources[0].id, config: { resource_ids: groupResources.map((r) => r.id), max_iterations: 3 } },
        });
      }
    }

    setShowSkillModal(false);
    setSkillRunErrors([]);
    setSkillRunning(true);

    const results = await Promise.allSettled(
      requests.map(({ payload }) => client.post('/api/translation-jobs', payload).then((r) => r.data))
    );

    setSkillRunning(false);
    queryClient.invalidateQueries({ queryKey: ['translation-jobs'] });
    queryClient.invalidateQueries({ queryKey: ['resources'] });

    const errors: string[] = [];
    let lastRunId: string | null = null;
    results.forEach((result, i) => {
      if (result.status === 'fulfilled') {
        lastRunId = result.value.id;
      } else {
        const label = requests[i].label;
        const detail = (result.reason as { response?: { data?: { detail?: string } } })?.response?.data?.detail || result.reason?.message || 'Unknown error';
        errors.push(`${label}: ${detail}`);
      }
    });

    if (errors.length > 0) {
      setSkillRunErrors(errors);
    } else if (lastRunId) {
      navigate(`/translation-jobs/${lastRunId}`);
    } else {
      navigate('/dashboard');
    }
  };

  const handleAssignResources = async () => {
    if (!id || assignSelectedIds.size === 0) return;
    setAssigning(true);
    try {
      await client.post(`/api/migrations/${id}/resources`, { resource_ids: Array.from(assignSelectedIds) });
      await queryClient.invalidateQueries({ queryKey: ['resources'] });
      setShowAssignModal(false);
    } catch {
      // silently close
    } finally {
      setAssigning(false);
    }
  };

  const handleDeleteMigration = async () => {
    if (!id) return;
    if (!confirm(`Delete migration "${migration?.name}"? All associated resources and jobs will be permanently deleted.`)) return;
    deleteMigration.mutate(id, { onSuccess: () => navigate('/dashboard') });
  };

  const loadUploadFile = (file: File) => {
    setUploadError('');
    if (file.size > 10 * 1024 * 1024) { setUploadError('File is too large. Max size is 10 MB.'); return; }
    setUploadFile(file);
    const name = file.name.toLowerCase();
    if (name.includes('cloudtrail') || name.endsWith('.json')) setUploadFileType('CloudTrail');
    else if (name.includes('flow') || name.endsWith('.log')) setUploadFileType('FlowLog');
    else setUploadFileType('Upload');
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) loadUploadFile(file);
  };

  const handleUploadSubmit = () => {
    if (!id || !uploadFile) return;
    uploadToMigration.mutate(
      { migrationId: id, file: uploadFile, fileType: uploadFileType },
      {
        onSuccess: () => {
          setUploadFile(null);
          setUploadError('');
          setShowUploadModal(false);
          queryClient.invalidateQueries({ queryKey: ['resources'] });
        },
      }
    );
  };

  // ── Loading ──

  if (loadingMigration) {
    return (
      <div style={{ display: 'flex', gap: '1.5rem' }}>
        <div className="skel rounded-xl" style={{ width: '240px', flexShrink: 0, height: '400px' }} />
        <div className="flex-1 space-y-4">
          {[...Array(3)].map((_, i) => <div key={i} className="skel h-24 rounded-xl" />)}
        </div>
      </div>
    );
  }

  if (migrationError || !migration) {
    return (
      <div className="space-y-4">
        <Link to="/dashboard" className="back-link">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Dashboard
        </Link>
        <div className="alert alert-error">
          {migrationError ? 'Failed to load migration. Please try again.' : 'Migration not found.'}
        </div>
      </div>
    );
  }

  // Step completion status derived from data
  const stepStatus = {
    discover: allResources.length > 0 || migration.discovery_status === 'discovered',
    assess: !!latestAssessment,
    plan: synthesisJob?.status === 'complete',
  };

  const STEPS: { id: ActiveStep; label: string; sublabel: string }[] = [
    { id: 'discover', label: 'Discover', sublabel: allResources.length > 0 ? `${allResources.length} resources` : 'Scan AWS resources' },
    { id: 'assess', label: 'Assess', sublabel: latestAssessment?.status === 'complete' ? `Score ${Math.round(latestAssessment.avg_readiness_score)}%` : 'Workload analysis' },
    { id: 'plan', label: 'Plan', sublabel: migration?.plan_status === 'completed' ? 'Ready' : 'Generate Terraform' },
  ];

  // ── Render ──

  return (
    <div className="animate-fade-in">
      {/* Error banner */}
      {skillRunErrors.length > 0 && (
        <div className="alert alert-error mb-4">
          <p className="font-semibold mb-1">
            {skillRunErrors.length} translation job{skillRunErrors.length !== 1 ? 's' : ''} failed to start:
          </p>
          <ul className="space-y-0.5">
            {skillRunErrors.map((e, i) => (
              <li key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{e}</li>
            ))}
          </ul>
          <button onClick={() => setSkillRunErrors([])} className="text-xs underline mt-2 opacity-70 hover:opacity-100">Dismiss</button>
        </div>
      )}

      {/* Back link */}
      <Link to="/migrations" className="back-link" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem', marginBottom: '1.25rem', fontSize: '0.75rem', color: 'var(--color-text-dim)', textDecoration: 'none' }}>
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        All Migrations
      </Link>

      {/* Phase pipeline */}
      {(() => {
        const isMigrateStep = activeStep === 'migrate';
        const isPhase1 = ['discover', 'assess', 'plan'].includes(activeStep);
        const phases = [
          { num: 1, title: 'Discover & Assess', desc: 'Scan resources, analyze dependencies, assess readiness', accent: '#1d4ed8', active: isPhase1,      done: !!migration?.plan_status,                    live: true,  onClick: () => setActiveStep('discover') },
          { num: 2, title: 'Migrate',            desc: 'Execute Terraform and apply migration to OCI',           accent: '#7c3aed', active: isMigrateStep, done: migration?.migrate_status === 'completed',    live: !!migration?.plan_status, onClick: () => setActiveStep('migrate') },
          { num: 3, title: 'Validate',           desc: 'Post-migration testing and verification',                accent: '#059669', active: false,         done: false,                                        live: false, onClick: () => {} },
        ];
        return (
          <div
            className="flex items-stretch gap-0 mb-5"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', borderRadius: 10, boxShadow: 'var(--shadow-card)', overflow: 'hidden' }}
          >
            {phases.map((phase, idx) => (
              <div
                key={phase.num}
                className="flex-1 relative"
                onClick={phase.live ? phase.onClick : undefined}
                style={{
                  padding: '16px 20px',
                  borderRight: idx < 2 ? '1px solid var(--color-rule)' : 'none',
                  opacity: phase.active || phase.done ? 1 : 0.45,
                  cursor: phase.live ? 'pointer' : 'default',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => { if (phase.live) (e.currentTarget as HTMLElement).style.background = 'var(--color-well)'; }}
                onMouseLeave={(e) => { if (phase.live) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
              >
                {(phase.active || phase.done) && (
                  <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: phase.accent }} />
                )}
                <div className="flex items-start gap-3">
                  <div style={{
                    width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontFamily: 'var(--font-display)', fontSize: '0.875rem', fontWeight: 700, fontStyle: 'italic',
                    color: phase.active || phase.done ? '#fff' : 'var(--color-rail)',
                    background: phase.active || phase.done ? phase.accent : 'var(--color-well)',
                    border: `1.5px solid ${phase.active || phase.done ? phase.accent : 'var(--color-rule)'}`,
                  }}>
                    {phase.done ? (
                      <svg style={{ width: 12, height: 12 }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    ) : phase.num}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="flex items-center gap-2">
                      <h3 style={{ fontFamily: 'var(--font-display)', fontSize: '0.875rem', fontWeight: 600, margin: 0, lineHeight: 1.3, color: phase.active || phase.done ? 'var(--color-text-bright)' : 'var(--color-rail)' }}>
                        {phase.title}
                      </h3>
                      {!phase.live && (
                        <span style={{ fontSize: '0.5rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--color-rail)', background: 'var(--color-well)', padding: '1px 5px', borderRadius: 2, border: '1px solid var(--color-rule)' }}>
                          Soon
                        </span>
                      )}
                    </div>
                    <p style={{ fontSize: '0.6875rem', color: 'var(--color-text-dim)', margin: '3px 0 0', lineHeight: 1.4 }}>
                      {phase.desc}
                    </p>
                  </div>
                </div>
                {idx < 2 && (
                  <div style={{
                    position: 'absolute', right: -9, top: '50%', transform: 'translateY(-50%)', zIndex: 1,
                    width: 18, height: 18, background: 'var(--color-surface)',
                    border: '1px solid var(--color-rule)', borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <svg width="10" height="10" fill="none" stroke="var(--color-rail)" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      })()}

      {/* Phase 2 Migrate — full width, no sidebar */}
      {activeStep === 'migrate' && (
        <MigrateStep migrationId={id || ''} migration={migration} />
      )}

      {/* Phase 1 — Two-column layout: sidebar + main */}
      {activeStep !== 'migrate' && (
      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>

        {/* ── Left sidebar ── */}
        <aside
          style={{
            width: '240px',
            flexShrink: 0,
            position: 'sticky',
            top: '1.5rem',
          }}
        >
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}
          >
            {/* Migration identity */}
            <div className="p-4" style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <h1
                className="text-base font-bold leading-tight mb-2"
                style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-display)', wordBreak: 'break-word' }}
              >
                {migration.name}
              </h1>
              <div className="flex flex-wrap gap-1.5 mb-3">
                <span className={migrationStatusBadge(migration.status)}>
                  <span className="badge-dot" />
                  {migration.status}
                </span>
                {migration.discovery_status && migration.discovery_status !== 'pending' && (
                  <span className={discoveryStatusBadge(migration.discovery_status)}>
                    <span className="badge-dot" />
                    {migration.discovery_status === 'discovering' ? 'Discovering…' : migration.discovery_status}
                  </span>
                )}
              </div>
              <p className="text-xs" style={{ color: 'var(--color-rail)' }}>
                Created {formatDate(migration.created_at)}
              </p>
            </div>

            {/* Key stats */}
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>Resources</span>
                  <span className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                    {allResources.length || migration.resource_count || 0}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>Assessments</span>
                  <span className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                    {assessments?.length || 0}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>Trans. Jobs</span>
                  <span className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                    {migrationSkillRuns.length}
                  </span>
                </div>
              </div>
            </div>

            {/* Vertical step list */}
            <div className="p-3">
              {STEPS.map((step, idx) => {
                const isActive = activeStep === step.id;
                const isDone = stepStatus[step.id];
                return (
                  <div key={step.id} className="relative">
                    {/* Connector line */}
                    {idx < STEPS.length - 1 && (
                      <div
                        style={{
                          position: 'absolute',
                          left: '19px',
                          top: '36px',
                          bottom: '-4px',
                          width: '2px',
                          background: isDone ? 'var(--color-ember)' : 'var(--color-rule)',
                          zIndex: 0,
                        }}
                      />
                    )}
                    <button
                      onClick={() => setActiveStep(step.id)}
                      className="relative w-full flex items-start gap-3 p-2 rounded-lg text-left transition-colors"
                      style={{
                        background: isActive ? 'var(--color-ember-dim)' : 'transparent',
                        marginBottom: idx < STEPS.length - 1 ? '4px' : 0,
                        zIndex: 1,
                      }}
                    >
                      {/* Step indicator */}
                      <div
                        className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
                        style={{
                          background: isDone ? 'var(--color-ember)' : isActive ? 'var(--color-surface)' : 'var(--color-well)',
                          border: isActive ? '2px solid var(--color-ember)' : isDone ? 'none' : '2px solid var(--color-fence)',
                          color: isDone ? 'white' : isActive ? 'var(--color-ember)' : 'var(--color-rail)',
                          fontSize: '0.625rem',
                          fontWeight: 700,
                        }}
                      >
                        {isDone ? (
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          idx + 1
                        )}
                      </div>
                      <div className="min-w-0">
                        <p
                          className="text-xs font-semibold"
                          style={{ color: isActive ? 'var(--color-ember)' : 'var(--color-text-bright)' }}
                        >
                          {step.label}
                        </p>
                        <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--color-text-dim)' }}>
                          {step.sublabel}
                        </p>
                      </div>
                    </button>
                  </div>
                );
              })}
            </div>

            {/* Actions */}
            <div className="p-3 pt-0 space-y-2">
              {selectedIds.size > 0 && (
                <button
                  onClick={handleRunSkill}
                  disabled={skillRunning}
                  className="btn btn-primary w-full text-xs"
                >
                  {skillRunning
                    ? <><span className="spinner" />Running…</>
                    : `Run Translation Jobs (${selectedIds.size})`}
                </button>
              )}
              <button
                onClick={handleDeleteMigration}
                disabled={deleteMigration.isPending}
                className="btn btn-danger btn-sm w-full text-xs"
              >
                {deleteMigration.isPending ? 'Deleting…' : 'Delete Migration'}
              </button>
            </div>
          </div>
        </aside>

        {/* ── Main content area ── */}
        <main className="flex-1 min-w-0">
          {activeStep === 'discover' && (
            <DiscoverStep
              migration={migration}
              allResources={allResources}
              filteredResources={filteredResources}
              selectedIds={selectedIds}
              typeFilter={typeFilter}
              search={search}
              uniqueTypes={uniqueTypes}
              loadingResources={loadingResources}
              resourcesError={resourcesError}
              extracting={extracting}
              extractingInstance={extractingInstance}
              extractError={extractError}
              instances={instances}
              loadingInstances={loadingInstances}
              instanceError={instanceError}
              selectedInstance={selectedInstance}
              showResources={showResources}
              allFilteredSelected={allFilteredSelected}
              skillGroups={skillGroups}
              skillRunning={skillRunning}
              onToggle={toggleSelect}
              onToggleAll={toggleSelectAll}
              onRunSkill={handleRunSkill}
              onSetTypeFilter={setTypeFilter}
              onSetSearch={setSearch}
              onSetExtractError={setExtractError}
              onExtractAll={handleExtractAll}
              onOpenInstanceModal={handleOpenInstanceModal}
              onExtractByInstance={handleExtractByInstance}
              onSetSelectedInstance={setSelectedInstance}
              onSetShowResources={setShowResources}
              onUploadClick={() => { setUploadFile(null); setUploadError(''); setShowUploadModal(true); }}
            />
          )}

          {activeStep === 'assess' && (
            <AssessStep
              migrationId={id || ''}
              workloads={workloads}
              loadingWorkloads={loadingWorkloads}
              latestAssessment={latestAssessment}
              loadingAssessments={loadingAssessments}
              runAssessment={{ mutate: (mid: string) => runAssessment.mutate(mid), isPending: runAssessment.isPending }}
              onPlanWorkload={(wid) => {
                setSearchParams({ step: 'plan', workload: wid }, { replace: true });
              }}
            />
          )}

          {activeStep === 'plan' && (
            <PlanStep
              migrationId={id || ''}
              workloads={workloads}
              latestAssessment={latestAssessment ? { id: latestAssessment.id, status: latestAssessment.status } : null}
              migrationSkillRuns={migrationSkillRuns}
              selectedWorkloadId={planSelectedWorkload || migration?.plan_workload_id || null}
              planStatus={migration?.plan_status}
              planStartedAt={migration?.plan_started_at}
              planMaxIterations={migration?.plan_max_iterations}
            />
          )}

        </main>
      </div>
      )}

      {/* ── Modals (unchanged functionality) ── */}

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Upload Resource File">
          <div className="modal">
            <div className="modal-header">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Upload Resource File</h3>
              <button onClick={() => setShowUploadModal(false)} className="btn btn-ghost btn-sm" aria-label="Close">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div>
                <label htmlFor="upload-file-type" className="field-label">File Type</label>
                <select id="upload-file-type" value={uploadFileType} onChange={(e) => setUploadFileType(e.target.value)} className="field-input field-select">
                  <option value="CloudTrail">CloudTrail</option>
                  <option value="FlowLog">VPC Flow Log</option>
                  <option value="Upload">Other</option>
                </select>
              </div>
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                aria-label="Upload file drop zone"
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click(); }}
                className="rounded-lg p-6 text-center cursor-pointer transition-colors"
                style={{
                  border: `2px dashed ${isDragging ? 'var(--color-ember)' : uploadFile ? 'rgba(34,197,94,0.4)' : 'var(--color-fence)'}`,
                  background: isDragging ? 'rgba(249,115,22,0.05)' : uploadFile ? 'rgba(34,197,94,0.05)' : 'var(--color-well)',
                }}
              >
                <input ref={fileInputRef} type="file" accept=".json,.log,.csv" onChange={(e) => { const f = e.target.files?.[0]; if (f) loadUploadFile(f); }} className="hidden" aria-hidden="true" />
                {uploadFile ? (
                  <div>
                    <p className="text-sm font-medium" style={{ color: '#16a34a' }}>{uploadFile.name}</p>
                    <p className="text-xs mt-1" style={{ color: 'var(--color-text-dim)' }}>Click to replace</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm" style={{ color: 'var(--color-text-dim)' }}>Drop file here or click to browse</p>
                    <p className="text-xs mt-1" style={{ color: 'var(--color-rail)' }}>JSON, CSV, or LOG files (max 10 MB)</p>
                  </div>
                )}
              </div>
              {uploadError && <p className="text-xs" style={{ color: '#dc2626' }}>{uploadError}</p>}
              {uploadToMigration.isError && (
                <p className="text-xs" style={{ color: '#dc2626' }}>
                  {(uploadToMigration.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Upload failed.'}
                </p>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowUploadModal(false)} className="btn btn-secondary">Cancel</button>
              <button onClick={handleUploadSubmit} disabled={!uploadFile || uploadToMigration.isPending} className="btn btn-primary">
                {uploadToMigration.isPending ? <><span className="spinner" />Uploading…</> : 'Upload'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Instance Selection Modal */}
      {showInstanceModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Select EC2 Instance">
          <div className="modal modal-lg" style={{ maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Select EC2 Instance</h3>
              <button onClick={() => setShowInstanceModal(false)} className="btn btn-ghost btn-sm" aria-label="Close">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="modal-body overflow-y-auto flex-1">
              {loadingInstances ? (
                <div className="space-y-2">{[...Array(3)].map((_, i) => <div key={i} className="skel h-14" />)}</div>
              ) : instanceError ? (
                <div className="text-center py-4">
                  <p className="text-sm" style={{ color: '#dc2626' }}>{instanceError}</p>
                  <button onClick={handleOpenInstanceModal} className="btn btn-secondary btn-sm mt-3">Retry</button>
                </div>
              ) : instances.length === 0 ? (
                <div className="empty-state"><p>No EC2 instances found. Ensure your AWS connection is configured.</p></div>
              ) : (
                <div className="space-y-2">
                  {instances.map((inst) => (
                    <button
                      key={inst.id}
                      onClick={() => { setSelectedInstance(inst); setShowInstanceModal(false); }}
                      className="w-full text-left p-3 rounded-lg transition-colors"
                      style={{
                        background: selectedInstance?.id === inst.id ? 'rgba(249,115,22,0.08)' : 'var(--color-well)',
                        border: `1px solid ${selectedInstance?.id === inst.id ? 'rgba(249,115,22,0.3)' : 'var(--color-fence)'}`,
                      }}
                      onMouseEnter={(e) => { if (selectedInstance?.id !== inst.id) (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-rail)'; }}
                      onMouseLeave={(e) => { if (selectedInstance?.id !== inst.id) (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-fence)'; }}
                    >
                      <p className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>{inst.name || 'Unnamed Instance'}</p>
                      <p className="text-xs truncate mt-0.5" style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}>{inst.aws_arn}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Translation Job Confirmation Modal */}
      {showSkillModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Confirm Translation Jobs">
          <div className="modal modal-lg" style={{ maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Confirm Translation Jobs</h3>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                  {selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected. CFN stacks run individually; other types batch into one job per type.
                </p>
              </div>
            </div>
            <div className="modal-body overflow-y-auto flex-1 space-y-3">
              {Array.from(skillGroups.entries()).map(([skillType, groupResources]) => {
                const isCfn = skillType === 'cfn_terraform';
                return (
                  <div key={skillType} className="rounded-lg p-4" style={{ background: 'var(--color-well)', border: '1px solid var(--color-fence)' }}>
                    <div className="flex items-center justify-between mb-3 gap-3">
                      <h4 className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                        {SKILL_LABELS[skillType] || skillType}
                      </h4>
                      <span className="badge badge-neutral flex-shrink-0">
                        {isCfn ? `${groupResources.length} job${groupResources.length !== 1 ? 's' : ''}` : `${groupResources.length} res → 1 job`}
                      </span>
                    </div>
                    <ul className="space-y-1.5">
                      {groupResources.map((r) => (
                        <li key={r.id} className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-dim)' }}>
                          <span className={cn(getTypeBadgeClass(r.aws_type), 'flex-shrink-0')}>{shortType(r.aws_type)}</span>
                          <span className="truncate">{r.name || r.aws_arn}</span>
                          {isCfn && <span className="ml-auto flex-shrink-0 opacity-50">→ 1 job</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowSkillModal(false)} className="btn btn-secondary">Cancel</button>
              <button onClick={handleConfirmSkillRun} disabled={skillRunning} className="btn btn-primary">
                {skillRunning ? <><span className="spinner" />Starting…</> : 'Run Translation Jobs'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Assign Resources Modal */}
      {showAssignModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Assign Resources to Migration">
          <div className="modal modal-lg" style={{ maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>Assign Resources to Migration</h3>
                <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                  {extractedResources.length} resource{extractedResources.length !== 1 ? 's' : ''} extracted. Select which to assign.
                </p>
              </div>
            </div>
            <div className="modal-body overflow-y-auto flex-1 space-y-2">
              <label
                className="flex items-center gap-2 text-xs font-medium pb-3 cursor-pointer"
                style={{ color: 'var(--color-text-dim)', borderBottom: '1px solid var(--color-rule)' }}
              >
                <input
                  type="checkbox"
                  className="cb"
                  checked={assignSelectedIds.size === extractedResources.length && extractedResources.length > 0}
                  onChange={() => {
                    if (assignSelectedIds.size === extractedResources.length) setAssignSelectedIds(new Set());
                    else setAssignSelectedIds(new Set(extractedResources.map((r) => r.id)));
                  }}
                />
                Select All ({extractedResources.length})
              </label>
              {extractedResources.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-xs py-1 cursor-pointer" style={{ color: 'var(--color-text-dim)' }}>
                  <input
                    type="checkbox"
                    className="cb"
                    checked={assignSelectedIds.has(r.id)}
                    onChange={() => {
                      setAssignSelectedIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(r.id)) next.delete(r.id); else next.add(r.id);
                        return next;
                      });
                    }}
                  />
                  <span className="truncate flex-1">{r.name}</span>
                  {r.aws_type && <span className="opacity-50 flex-shrink-0">{r.aws_type}</span>}
                </label>
              ))}
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowAssignModal(false)} className="btn btn-secondary">Skip</button>
              <button onClick={handleAssignResources} disabled={assignSelectedIds.size === 0 || assigning} className="btn btn-primary">
                {assigning ? <><span className="spinner" />Assigning…</> : `Assign Selected (${assignSelectedIds.size})`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
