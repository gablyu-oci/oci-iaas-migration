import { useState, useEffect, useMemo, useCallback, useRef, type DragEvent } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useMigration, useUploadToMigration, useDeleteMigration } from '../api/hooks/useMigrations';
import { useResources, type Resource } from '../api/hooks/useResources';
import { useTranslationJobs } from '../api/hooks/useTranslationJobs';
import { formatDate, cn, getSkillRunName } from '../lib/utils';
import client from '../api/client';
import { synthesizeMigration, getLatestSynthesis } from '../api/plans';

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

// ── Component ─────────────────────────────────────────────────────────────────

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
          .filter((r: any) => scopedSet.has(r.id))
          .map((r: any) => ({ id: r.id, name: r.name || r.aws_arn || r.id, aws_type: r.aws_type || '' }));
        if (scoped.length === 0) { setExtractError('No resources found for this instance.'); return; }
        setExtractedResources(scoped);
        setAssignSelectedIds(new Set(scoped.map((r) => r.id)));
      } else {
        const resResponse = await client.get('/api/resources/unassigned');
        const unassigned: {id: string; name: string; aws_type: string}[] = resResponse.data.map(
          (r: any) => ({ id: r.id, name: r.name || r.aws_arn || r.id, aws_type: r.aws_type || '' })
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
      const res = await client.get('/api/aws/resources', { params: { type: 'AWS::EC2::Instance' } });
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
      <div className="space-y-4 animate-fade-in">
        {[...Array(4)].map((_, i) => <div key={i} className="skel h-20" />)}
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

  // ── Render ──

  return (
    <div className="space-y-6 animate-fade-in">
      {skillRunErrors.length > 0 && (
        <div className="alert alert-error">
          <p className="font-semibold mb-1">
            {skillRunErrors.length} translation job{skillRunErrors.length !== 1 ? 's' : ''} failed to start:
          </p>
          <ul className="space-y-0.5">
            {skillRunErrors.map((e, i) => (
              <li key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>{e}</li>
            ))}
          </ul>
          <button
            onClick={() => setSkillRunErrors([])}
            className="text-xs underline mt-2 opacity-70 hover:opacity-100"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Back */}
      <Link to="/dashboard" className="back-link">
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to Dashboard
      </Link>

      {/* Header */}
      <div className="panel">
        <div className="panel-body">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="page-title">{migration.name}</h1>
                <span className={migrationStatusBadge(migration.status)}>
                  <span className="badge-dot" />
                  {migration.status}
                </span>
              </div>
              <p className="page-subtitle">Created {formatDate(migration.created_at)}</p>
              {migration.aws_connection_id && (
                <p className="text-xs mt-0.5" style={{ color: '#475569' }}>
                  Connection: <span style={{ fontFamily: 'var(--font-mono)' }}>{migration.aws_connection_id}</span>
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={handleRunSkill}
                disabled={selectedIds.size === 0 || skillRunning}
                className={cn('btn', selectedIds.size > 0 ? 'btn-primary' : 'btn-secondary')}
              >
                {skillRunning ? (
                  <><span className="spinner" />Running…</>
                ) : (
                  `Run Translation Job${selectedIds.size > 0 ? ` (${selectedIds.size})` : ''}`
                )}
              </button>
              <button
                onClick={handleDeleteMigration}
                disabled={deleteMigration.isPending}
                className="btn btn-danger"
              >
                {deleteMigration.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Resource Discovery */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Resource Discovery</h2>
        </div>
        <div className="panel-body space-y-4">
          <p className="text-xs" style={{ color: '#64748b' }}>
            Discover AWS resources to include in this migration. Select a specific EC2 instance to scope discovery, or extract all resources at once.
          </p>

          {extractError && (
            <div className="alert alert-error" role="alert">
              {extractError}
              <button onClick={() => setExtractError(null)} className="ml-2 underline hover:no-underline text-xs">
                Dismiss
              </button>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            {/* Instance-based */}
            <button onClick={handleOpenInstanceModal} className="btn btn-secondary">
              Select Instance
            </button>
            {selectedInstance && (
              <span
                className="flex items-center gap-2 px-3 py-1.5 rounded text-xs"
                style={{
                  background: 'rgba(34,197,94,0.08)',
                  border: '1px solid rgba(34,197,94,0.2)',
                  color: '#16a34a',
                }}
              >
                <span className="truncate max-w-[180px]">
                  {selectedInstance.name || selectedInstance.aws_arn}
                </span>
                <button
                  onClick={() => setSelectedInstance(null)}
                  className="flex-shrink-0 opacity-60 hover:opacity-100"
                  aria-label="Clear instance"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            )}
            {selectedInstance && (
              <button
                onClick={handleExtractByInstance}
                disabled={extractingInstance}
                className="btn btn-success"
              >
                {extractingInstance ? <><span className="spinner" />Discovering…</> : 'Discover Resources'}
              </button>
            )}

            <div className="w-px h-6 flex-shrink-0" style={{ background: 'var(--color-fence)' }} aria-hidden="true" />

            <button onClick={handleExtractAll} disabled={extracting} className="btn btn-primary">
              {extracting ? <><span className="spinner" />Extracting…</> : 'Extract All Resources'}
            </button>

            <div className="w-px h-6 flex-shrink-0" style={{ background: 'var(--color-fence)' }} aria-hidden="true" />

            <button
              onClick={() => { setUploadFile(null); setUploadError(''); setShowUploadModal(true); }}
              className="btn btn-secondary"
            >
              Upload Resource File
            </button>
          </div>
        </div>
      </div>

      {/* Resources Table */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>
            Resources
            {allResources.length > 0 && (
              <span className="ml-2 font-normal" style={{ color: '#64748b' }}>
                {allResources.length} total
                {selectedIds.size > 0 && `, ${selectedIds.size} selected`}
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="field-input field-select"
              style={{ width: 'auto', fontSize: '0.75rem', padding: '0.3125rem 2rem 0.3125rem 0.625rem' }}
              aria-label="Filter by type"
            >
              <option value="">All Types</option>
              {uniqueTypes.map((t) => <option key={t} value={t}>{shortType(t)}</option>)}
            </select>
            <div className="relative">
              <svg
                className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5"
                style={{ color: '#475569' }}
                fill="none" stroke="currentColor" viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                className="field-input"
                style={{ paddingLeft: '2rem', width: '11rem', fontSize: '0.75rem', padding: '0.3125rem 0.625rem 0.3125rem 2rem' }}
                aria-label="Search resources"
              />
            </div>
          </div>
        </div>

        {/* Selection bar */}
        {selectedIds.size > 0 && (
          <div className="selection-bar">
            <p>
              {selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected
              {skillGroups.size > 1 && (
                <span className="opacity-70"> · {skillGroups.size} translation job types</span>
              )}
            </p>
            <button
              onClick={handleRunSkill}
              disabled={skillRunning}
              className="btn btn-primary btn-sm"
            >
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
        ) : allResources.length === 0 ? (
          <div className="empty-state">
            <svg className="w-10 h-10 mx-auto mb-3 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
            </svg>
            <p>No resources yet. Use discovery above or upload a CloudTrail / Flow Log file.</p>
          </div>
        ) : filteredResources.length === 0 ? (
          <div className="empty-state"><p>No resources match your filters.</p></div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="dt">
              <thead>
                <tr>
                  <th style={{ width: '2.5rem' }}>
                    <input
                      type="checkbox"
                      checked={allFilteredSelected}
                      onChange={toggleSelectAll}
                      className="cb"
                      aria-label="Select all"
                    />
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
                  <tr
                    key={r.id}
                    style={selectedIds.has(r.id) ? { background: 'rgba(249,115,22,0.05)' } : undefined}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(r.id)}
                        onChange={() => toggleSelect(r.id)}
                        className="cb"
                        aria-label={`Select ${r.name || r.aws_arn}`}
                      />
                    </td>
                    <td>
                      <span className={getTypeBadgeClass(r.aws_type)}>
                        {shortType(r.aws_type)}
                      </span>
                    </td>
                    <td>
                      <p className="text-sm font-medium" style={{ color: '#0f172a' }}>{r.name || 'Unnamed'}</p>
                      <p
                        className="text-xs truncate max-w-xs"
                        style={{ color: '#475569', fontFamily: 'var(--font-mono)' }}
                      >
                        {r.aws_arn}
                      </p>
                    </td>
                    <td>
                      <span className={resourceStatusBadge(r.status)}>
                        <span className="badge-dot" />
                        {r.status}
                      </span>
                    </td>
                    <td>
                      {r.latest_skill_run ? (
                        <Link
                          to={
                            r.latest_skill_run.status === 'complete'
                              ? `/translation-jobs/${r.latest_skill_run.id}/results`
                              : `/translation-jobs/${r.latest_skill_run.id}`
                          }
                          style={{ color: 'var(--color-ember)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}
                          onClick={(e) => e.stopPropagation()}
                          className="hover:opacity-80 transition-opacity"
                        >
                          {r.latest_skill_run.skill_type}
                        </Link>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>—</span>
                      )}
                    </td>
                    <td>
                      {r.latest_skill_run ? (
                        <span className={jobStatusBadge(r.latest_skill_run.status)}>
                          <span className="badge-dot" />
                          {r.latest_skill_run.status}
                        </span>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>—</span>
                      )}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                      {r.latest_skill_run?.status === 'complete'
                        ? `${Math.round(r.latest_skill_run.confidence * 100)}%`
                        : <span style={{ color: '#94a3b8' }}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Migration Plan */}
      <div className="panel">
        <div className="panel-header">
          <div>
            <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Migration Plan</h2>
            <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
              Combines all completed translation job results into unified Terraform files and a migration runbook.
            </p>
          </div>
          <button
            onClick={handleGeneratePlan}
            disabled={synthesizing || synthesisJob?.status === 'queued' || synthesisJob?.status === 'running'}
            className="btn btn-primary flex-shrink-0"
          >
            {synthesizing || synthesisJob?.status === 'queued' || synthesisJob?.status === 'running' ? (
              <><span className="spinner" />Generating…</>
            ) : synthesisJob?.status === 'complete' ? (
              'Regenerate Plan'
            ) : (
              'Generate Migration Plan'
            )}
          </button>
        </div>

        {synthesisError && (
          <div className="alert alert-error mx-4 mt-4">{synthesisError}</div>
        )}

        {loadingSynthesis ? (
          <div className="panel-body"><div className="skel h-10" /></div>
        ) : !synthesisJob ? (
          <div className="empty-state">
            <p>No plan yet. Run translation jobs on your resources, then click "Generate Migration Plan".</p>
          </div>
        ) : synthesisJob.status === 'queued' || synthesisJob.status === 'running' ? (
          <div className="panel-body flex items-center gap-3" style={{ color: '#2563eb' }}>
            <span className="spinner flex-shrink-0" />
            <span className="text-sm">
              Synthesizing migration plan
              {synthesisJob.current_phase ? ` — ${synthesisJob.current_phase}` : '…'}
            </span>
          </div>
        ) : synthesisJob.status === 'complete' ? (
          <div className="panel-body space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium" style={{ color: '#16a34a' }}>✓ Migration plan ready</p>
                <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
                  Confidence {Math.round(synthesisJob.confidence * 100)}% · Generated {formatDate(synthesisJob.completed_at || '')}
                </p>
              </div>
              <Link
                to={`/migrations/${id}/plan`}
                className="btn btn-success flex-shrink-0"
              >
                View & Download →
              </Link>
            </div>
            <p className="text-xs" style={{ color: '#475569', borderTop: '1px solid var(--color-rule)', paddingTop: '0.75rem' }}>
              Artifacts include: numbered Terraform files (apply in order),{' '}
              <code>iam-setup.md</code>, <code>migration-runbook.md</code>, <code>special-attention.md</code>
            </p>
          </div>
        ) : (
          <div className="panel-body">
            <div className="alert alert-error">
              Plan generation failed: {synthesisJob.errors?.error as string || 'Unknown error'}
            </div>
          </div>
        )}
      </div>

      {/* Translation Jobs for this migration */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Translation Jobs</h2>
          {migrationSkillRuns.length > 0 && (
            <span className="badge badge-neutral">{migrationSkillRuns.length}</span>
          )}
        </div>
        {migrationSkillRuns.length === 0 ? (
          <div className="empty-state"><p>No translation jobs for this migration yet.</p></div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="dt">
              <thead>
                <tr>
                  <th>Run Name</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {migrationSkillRuns.map((sr) => (
                  <tr key={sr.id}>
                    <td className="td-primary">
                      {getSkillRunName(sr.skill_type, sr.resource_names, sr.resource_name)}
                    </td>
                    <td>
                      <span className={jobStatusBadge(sr.status)}>
                        <span className="badge-dot" />
                        {sr.status}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                      {(sr.confidence * 100).toFixed(0)}%
                    </td>
                    <td>{formatDate(sr.created_at)}</td>
                    <td>
                      {sr.status === 'complete' ? (
                        <Link to={`/translation-jobs/${sr.id}/results`} className="btn btn-ghost btn-sm">
                          Results →
                        </Link>
                      ) : sr.status === 'running' || sr.status === 'queued' ? (
                        <Link to={`/translation-jobs/${sr.id}`} className="btn btn-ghost btn-sm">
                          Progress →
                        </Link>
                      ) : (
                        <Link to={`/translation-jobs/${sr.id}/results`} className="btn btn-ghost btn-sm">
                          Details →
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Upload Resource File"
        >
          <div className="modal">
            <div className="modal-header">
              <h3 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Upload Resource File</h3>
              <button onClick={() => setShowUploadModal(false)} className="btn btn-ghost btn-sm" aria-label="Close">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div>
                <label htmlFor="upload-file-type" className="field-label">File Type</label>
                <select
                  id="upload-file-type"
                  value={uploadFileType}
                  onChange={(e) => setUploadFileType(e.target.value)}
                  className="field-input field-select"
                >
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
                  background: isDragging
                    ? 'rgba(249,115,22,0.05)'
                    : uploadFile
                      ? 'rgba(34,197,94,0.05)'
                      : 'var(--color-well)',
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,.log,.csv"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) loadUploadFile(f); }}
                  className="hidden"
                  aria-hidden="true"
                />
                {uploadFile ? (
                  <div>
                    <p className="text-sm font-medium" style={{ color: '#16a34a' }}>{uploadFile.name}</p>
                    <p className="text-xs mt-1" style={{ color: '#475569' }}>Click to replace</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm" style={{ color: '#64748b' }}>Drop file here or click to browse</p>
                    <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>JSON, CSV, or LOG files (max 10 MB)</p>
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
              <button
                onClick={handleUploadSubmit}
                disabled={!uploadFile || uploadToMigration.isPending}
                className="btn btn-primary"
              >
                {uploadToMigration.isPending ? <><span className="spinner" />Uploading…</> : 'Upload'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Instance Selection Modal */}
      {showInstanceModal && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Select EC2 Instance"
        >
          <div className="modal modal-lg" style={{ maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <h3 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Select EC2 Instance</h3>
              <button onClick={() => setShowInstanceModal(false)} className="btn btn-ghost btn-sm" aria-label="Close">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="modal-body overflow-y-auto flex-1">
              {loadingInstances ? (
                <div className="space-y-2">
                  {[...Array(3)].map((_, i) => <div key={i} className="skel h-14" />)}
                </div>
              ) : instanceError ? (
                <div className="text-center py-4">
                  <p className="text-sm" style={{ color: '#dc2626' }}>{instanceError}</p>
                  <button onClick={handleOpenInstanceModal} className="btn btn-secondary btn-sm mt-3">Retry</button>
                </div>
              ) : instances.length === 0 ? (
                <div className="empty-state">
                  <p>No EC2 instances found. Ensure your AWS connection is configured.</p>
                </div>
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
                      onMouseEnter={(e) => {
                        if (selectedInstance?.id !== inst.id) {
                          (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-rail)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (selectedInstance?.id !== inst.id) {
                          (e.currentTarget as HTMLElement).style.borderColor = 'var(--color-fence)';
                        }
                      }}
                    >
                      <p className="text-sm font-medium" style={{ color: '#0f172a' }}>
                        {inst.name || 'Unnamed Instance'}
                      </p>
                      <p
                        className="text-xs truncate mt-0.5"
                        style={{ color: '#475569', fontFamily: 'var(--font-mono)' }}
                      >
                        {inst.aws_arn}
                      </p>
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
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm Translation Jobs"
        >
          <div className="modal modal-lg" style={{ maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Confirm Translation Jobs</h3>
                <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
                  {selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected.
                  CFN stacks run individually; other types batch into one job per type.
                </p>
              </div>
            </div>
            <div className="modal-body overflow-y-auto flex-1 space-y-3">
              {Array.from(skillGroups.entries()).map(([skillType, groupResources]) => {
                const isCfn = skillType === 'cfn_terraform';
                return (
                  <div
                    key={skillType}
                    className="rounded-lg p-4"
                    style={{ background: 'var(--color-well)', border: '1px solid var(--color-fence)' }}
                  >
                    <div className="flex items-center justify-between mb-3 gap-3">
                      <h4 className="text-xs font-semibold" style={{ color: '#0f172a' }}>
                        {SKILL_LABELS[skillType] || skillType}
                      </h4>
                      <span className="badge badge-neutral flex-shrink-0">
                        {isCfn
                          ? `${groupResources.length} job${groupResources.length !== 1 ? 's' : ''}`
                          : `${groupResources.length} res → 1 job`}
                      </span>
                    </div>
                    <ul className="space-y-1.5">
                      {groupResources.map((r) => (
                        <li key={r.id} className="flex items-center gap-2 text-xs" style={{ color: '#64748b' }}>
                          <span className={cn(getTypeBadgeClass(r.aws_type), 'flex-shrink-0')}>
                            {shortType(r.aws_type)}
                          </span>
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
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Assign Resources to Migration"
        >
          <div className="modal modal-lg" style={{ maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
            <div className="modal-header">
              <div>
                <h3 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Assign Resources to Migration</h3>
                <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>
                  {extractedResources.length} resource{extractedResources.length !== 1 ? 's' : ''} extracted. Select which to assign.
                </p>
              </div>
            </div>
            <div className="modal-body overflow-y-auto flex-1 space-y-2">
              <label
                className="flex items-center gap-2 text-xs font-medium pb-3 cursor-pointer"
                style={{ color: '#475569', borderBottom: '1px solid var(--color-rule)' }}
              >
                <input
                  type="checkbox"
                  className="cb"
                  checked={assignSelectedIds.size === extractedResources.length && extractedResources.length > 0}
                  onChange={() => {
                    if (assignSelectedIds.size === extractedResources.length) {
                      setAssignSelectedIds(new Set());
                    } else {
                      setAssignSelectedIds(new Set(extractedResources.map((r) => r.id)));
                    }
                  }}
                />
                Select All ({extractedResources.length})
              </label>
              {extractedResources.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-xs py-1 cursor-pointer" style={{ color: '#475569' }}>
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
                  {r.aws_type && (
                    <span className="opacity-50 flex-shrink-0">{r.aws_type}</span>
                  )}
                </label>
              ))}
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowAssignModal(false)} className="btn btn-secondary">Skip</button>
              <button
                onClick={handleAssignResources}
                disabled={assignSelectedIds.size === 0 || assigning}
                className="btn btn-primary"
              >
                {assigning
                  ? <><span className="spinner" />Assigning…</>
                  : `Assign Selected (${assignSelectedIds.size})`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
