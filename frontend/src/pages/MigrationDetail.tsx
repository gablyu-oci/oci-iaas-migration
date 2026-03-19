import { useState, useEffect, useMemo, useCallback, useRef, type DragEvent } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useMigration, useUploadToMigration, useDeleteMigration } from '../api/hooks/useMigrations';
import { useResources, type Resource } from '../api/hooks/useResources';
import { useTranslationJobs } from '../api/hooks/useTranslationJobs';
import { formatDate, cn, getSkillRunName } from '../lib/utils';
import client from '../api/client';
import { useDeletePlan } from '../api/plans';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TYPE_COLORS: Record<string, string> = {
  'AWS::EC2::VPC': 'bg-blue-100 text-blue-800',
  'AWS::EC2::Subnet': 'bg-blue-100 text-blue-800',
  'AWS::EC2::SecurityGroup': 'bg-blue-100 text-blue-800',
  'AWS::EC2::NetworkInterface': 'bg-blue-100 text-blue-800',
  'AWS::EC2::Instance': 'bg-green-100 text-green-800',
  'AWS::EC2::Volume': 'bg-green-100 text-green-800',
  'AWS::AutoScaling::AutoScalingGroup': 'bg-green-100 text-green-800',
  'AWS::RDS::DBInstance': 'bg-orange-100 text-orange-800',
  'AWS::ElasticLoadBalancingV2::LoadBalancer': 'bg-indigo-100 text-indigo-800',
  'AWS::IAM::Policy': 'bg-red-100 text-red-800',
  'AWS::IAM::Role': 'bg-red-100 text-red-800',
  'AWS::CloudFormation::Stack': 'bg-purple-100 text-purple-800',
  'AWS::Lambda::Function': 'bg-yellow-100 text-yellow-800',
  CloudTrail: 'bg-yellow-100 text-yellow-800',
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
  network_translation: 'Network Translation (VPC/Subnets/SGs/ENIs -> OCI VCN)',
  ec2_translation: 'EC2 Translation (EC2/ASG -> OCI Compute)',
  storage_translation: 'Storage Translation (EBS -> OCI Block Volume)',
  database_translation: 'Database Translation (RDS -> OCI DB System)',
  loadbalancer_translation: 'Load Balancer Translation (ALB/NLB -> OCI LB)',
  iam_translation: 'IAM Translation (AWS IAM -> OCI IAM)',
  cfn_terraform: 'CloudFormation to Terraform (CFN -> HCL)',
  dependency_discovery: 'Dependency Discovery (CloudTrail -> Graph)',
};

const STATUS_COLORS: Record<string, string> = {
  created: 'bg-gray-100 text-gray-800',
  extracting: 'bg-blue-100 text-blue-800',
  extracted: 'bg-green-100 text-green-800',
  planning: 'bg-yellow-100 text-yellow-800',
  complete: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

const RESOURCE_STATUS_COLORS: Record<string, string> = {
  discovered: 'bg-gray-100 text-gray-800',
  extracted: 'bg-blue-100 text-blue-800',
  uploaded: 'bg-green-100 text-green-800',
  translated: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTypeBadgeColor(awsType: string): string {
  return TYPE_COLORS[awsType] || 'bg-gray-100 text-gray-800';
}

function shortType(awsType: string): string {
  const parts = awsType.split('::');
  return parts.length >= 3 ? parts.slice(1).join('::') : awsType;
}

function groupResourcesBySkill(
  resources: Resource[],
  selectedIds: Set<string>
): Map<string, Resource[]> {
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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MigrationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Data fetching
  const {
    data: migration,
    isLoading: loadingMigration,
    error: migrationError,
  } = useMigration(id || '');
  const {
    data: resources,
    isLoading: loadingResources,
    error: resourcesError,
  } = useResources({ migration_id: id });

  const [skillRunErrors, setSkillRunErrors] = useState<string[]>([]);
  const [skillRunning, setSkillRunning] = useState(false);
  const uploadToMigration = useUploadToMigration();
  const deleteMigration = useDeleteMigration();

  // Translation jobs for this migration
  const { data: allSkillRuns } = useTranslationJobs();
  const migrationSkillRuns = useMemo(
    () => (allSkillRuns || []).filter((sr) => sr.migration_id === id),
    [allSkillRuns, id]
  );

  // Plan for this migration
  const [plan, setPlan] = useState<{ id: string; status: string; generated_at?: string; phases?: unknown[] } | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(true);
  const [generatingPlan, setGeneratingPlan] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const deletePlanMutation = useDeletePlan();

  // Assign resources modal state
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignSelectedIds, setAssignSelectedIds] = useState<Set<string>>(new Set());
  const [extractedResources, setExtractedResources] = useState<{id: string; name: string; aws_type: string}[]>([]);
  const [assigning, setAssigning] = useState(false);

  // Local state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [extractingInstance, setExtractingInstance] = useState(false);
  const [extractError, setExtractError] = useState<string | null>(null);

  // Instance selection
  const [showInstanceModal, setShowInstanceModal] = useState(false);
  const [instances, setInstances] = useState<Resource[]>([]);
  const [loadingInstances, setLoadingInstances] = useState(false);
  const [instanceError, setInstanceError] = useState<string | null>(null);
  const [selectedInstance, setSelectedInstance] = useState<Resource | null>(null);

  // Skill run confirmation
  const [showSkillModal, setShowSkillModal] = useState(false);

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadFileType, setUploadFileType] = useState('CloudTrail');
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch plan for this migration
  const fetchPlan = useCallback(async () => {
    if (!id) return;
    try {
      const res = await client.get('/api/plans', { params: { migration_id: id } });
      const plans = res.data;
      if (plans.length > 0) {
        setPlan({ id: plans[0].id, status: plans[0].status, generated_at: plans[0].generated_at, phases: plans[0].phases });
      } else {
        setPlan(null);
      }
    } catch {
      setPlan(null);
    } finally {
      setLoadingPlan(false);
    }
  }, [id]);

  const handleGeneratePlan = async () => {
    if (!id) return;
    setGeneratingPlan(true);
    setPlanError(null);
    try {
      const res = await client.post(`/api/migrations/${id}/plan`);
      const newPlan = res.data;
      setPlan({ id: newPlan.id, status: newPlan.status, generated_at: newPlan.generated_at, phases: newPlan.phases });
      queryClient.invalidateQueries({ queryKey: ['plans'] });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to generate plan';
      setPlanError(msg);
    } finally {
      setGeneratingPlan(false);
    }
  };

  useEffect(() => {
    fetchPlan();
  }, [fetchPlan]);

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------

  const allResources = resources || [];

  const uniqueTypes = useMemo(() => {
    const types = new Set<string>();
    for (const r of allResources) {
      types.add(r.aws_type);
    }
    return Array.from(types).sort();
  }, [allResources]);

  const filteredResources = useMemo(() => {
    let list = allResources;
    if (typeFilter) {
      list = list.filter((r) => r.aws_type === typeFilter);
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (r) =>
          r.name.toLowerCase().includes(q) ||
          r.aws_arn.toLowerCase().includes(q) ||
          r.aws_type.toLowerCase().includes(q)
      );
    }
    return list;
  }, [allResources, typeFilter, search]);

  const allFilteredSelected = useMemo(
    () =>
      filteredResources.length > 0 &&
      filteredResources.every((r) => selectedIds.has(r.id)),
    [filteredResources, selectedIds]
  );

  const skillGroups = useMemo(
    () => groupResourcesBySkill(allResources, selectedIds),
    [allResources, selectedIds]
  );

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const toggleSelect = useCallback((resourceId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(resourceId)) {
        next.delete(resourceId);
      } else {
        next.add(resourceId);
      }
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (allFilteredSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const r of filteredResources) {
          next.delete(r.id);
        }
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const r of filteredResources) {
          next.add(r.id);
        }
        return next;
      });
    }
  }, [allFilteredSelected, filteredResources]);

  // Open the assign modal.
  // scopedIds: if non-empty, show ONLY these resources (instance-scoped discovery).
  // If empty, fetch and show all unassigned resources.
  const openAssignModal = async (scopedIds: string[]) => {
    try {
      if (scopedIds.length > 0) {
        // Instance-scoped: show ALL resources found for this instance (assigned or not)
        const resResponse = await client.get('/api/aws/resources');
        const scopedSet = new Set(scopedIds);
        const scoped: {id: string; name: string; aws_type: string}[] = resResponse.data
          .filter((r: any) => scopedSet.has(r.id))
          .map((r: any) => ({ id: r.id, name: r.name || r.aws_arn || r.id, aws_type: r.aws_type || '' }));
        if (scoped.length === 0) {
          setExtractError('No resources found for this instance.');
          return;
        }
        setExtractedResources(scoped);
        setAssignSelectedIds(new Set(scoped.map((r) => r.id)));
      } else {
        // Full extraction: show all unassigned resources
        const resResponse = await client.get('/api/resources/unassigned');
        const unassigned: {id: string; name: string; aws_type: string}[] = resResponse.data.map(
          (r: any) => ({ id: r.id, name: r.name || r.aws_arn || r.id, aws_type: r.aws_type || '' })
        );
        if (unassigned.length === 0) {
          setExtractError('No unassigned resources found to add to this migration.');
          return;
        }
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
      const msg = err instanceof Error ? err.message : 'Failed to extract resources';
      setExtractError(msg);
    } finally {
      setExtracting(false);
    }
  };

  const handleExtractByInstance = async () => {
    if (!id || !selectedInstance) return;
    setExtractingInstance(true);
    setExtractError(null);
    try {
      const response = await client.post(
        `/api/migrations/${id}/extract/instance?resource_id=${selectedInstance.id}`
      );
      await queryClient.invalidateQueries({ queryKey: ['resources'] });
      await openAssignModal(response.data.resource_ids ?? []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to extract resources';
      setExtractError(msg);
    } finally {
      setExtractingInstance(false);
    }
  };

  const handleOpenInstanceModal = async () => {
    setShowInstanceModal(true);
    setLoadingInstances(true);
    setInstanceError(null);
    try {
      // Fetch all tenant EC2 instances — instance may not be assigned to this migration yet
      const res = await client.get('/api/aws/resources', {
        params: { type: 'AWS::EC2::Instance' },
      });
      setInstances(res.data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch instances';
      setInstanceError(msg);
      setInstances([]);
    } finally {
      setLoadingInstances(false);
    }
  };

  const handleRunSkill = () => {
    if (selectedIds.size === 0) return;
    setShowSkillModal(true);
  };

  const handleConfirmSkillRun = async () => {
    // Build the list of individual POST requests.
    // cfn_terraform runs 1:1 per resource (each stack is an independent template).
    // All other skill types batch resources of the same type into one run so the
    // AI can translate related resources together (e.g. VPC + subnets + SGs).
    const requests: Array<{ skillType: string; label: string; payload: object }> = [];
    for (const [skillType, groupResources] of skillGroups.entries()) {
      if (skillType === 'cfn_terraform') {
        for (const r of groupResources) {
          requests.push({
            skillType,
            label: `${skillType}:${r.name || r.id}`,
            payload: {
              skill_type: skillType,
              migration_id: id,
              input_resource_id: r.id,
              config: { resource_ids: [r.id], max_iterations: 3 },
            },
          });
        }
      } else {
        requests.push({
          skillType,
          label: skillType,
          payload: {
            skill_type: skillType,
            migration_id: id,
            input_resource_id: groupResources[0].id,
            config: { resource_ids: groupResources.map((r) => r.id), max_iterations: 3 },
          },
        });
      }
    }

    setShowSkillModal(false);
    setSkillRunErrors([]);
    setSkillRunning(true);

    const results = await Promise.allSettled(
      requests.map(({ payload }) =>
        client.post('/api/translation-jobs', payload).then((r) => r.data)
      )
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
        const detail = (result.reason as { response?: { data?: { detail?: string } } })
          ?.response?.data?.detail || result.reason?.message || 'Unknown error';
        errors.push(`${label}: ${detail}`);
      }
    });

    if (errors.length > 0) {
      setSkillRunErrors(errors);
      // stay on this page so errors are visible
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
      await client.post(`/api/migrations/${id}/resources`, {
        resource_ids: Array.from(assignSelectedIds),
      });
      await queryClient.invalidateQueries({ queryKey: ['resources'] });
      setShowAssignModal(false);
    } catch {
      // silently close
    } finally {
      setAssigning(false);
    }
  };

  const handleDeletePlan = async () => {
    if (!plan) return;
    if (!confirm('Delete this migration plan? This will stop any running workloads.')) return;
    deletePlanMutation.mutate(plan.id, {
      onSuccess: () => {
        setPlan(null);
        queryClient.invalidateQueries({ queryKey: ['plans'] });
      },
    });
  };

  const handleDeleteMigration = async () => {
    if (!id) return;
    if (!confirm(`Delete migration "${migration?.name}"? All associated resources will be returned to the global pool and all translation jobs and plans will be permanently deleted.`)) return;
    deleteMigration.mutate(id, {
      onSuccess: () => navigate('/dashboard'),
    });
  };

  // Upload handlers
  const loadUploadFile = (file: File) => {
    setUploadError('');
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('File is too large. Maximum size is 10 MB.');
      return;
    }
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

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (loadingMigration) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-32 bg-gray-200 rounded" />
          <div className="h-8 w-64 bg-gray-200 rounded" />
          <div className="h-4 w-40 bg-gray-100 rounded" />
          <div className="h-40 bg-gray-100 rounded-lg" />
          <div className="h-64 bg-gray-100 rounded-lg" />
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Error state
  // ---------------------------------------------------------------------------

  if (migrationError || !migration) {
    return (
      <div className="space-y-6">
        <Link
          to="/dashboard"
          className="text-blue-600 hover:text-blue-800 text-sm font-medium inline-flex items-center gap-1"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Back to Dashboard
        </Link>
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <p className="text-red-600 font-medium">
            {migrationError
              ? 'Failed to load migration. Please try again.'
              : 'Migration not found.'}
          </p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {skillRunErrors.length > 0 && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm font-semibold text-red-700 mb-1">
            {skillRunErrors.length} translation job{skillRunErrors.length !== 1 ? 's' : ''} failed to start:
          </p>
          <ul className="space-y-0.5">
            {skillRunErrors.map((e, i) => (
              <li key={i} className="text-xs text-red-600 font-mono">{e}</li>
            ))}
          </ul>
          <button
            onClick={() => setSkillRunErrors([])}
            className="mt-2 text-xs text-red-500 hover:text-red-700 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Back link */}
      <Link
        to="/dashboard"
        className="text-blue-600 hover:text-blue-800 text-sm font-medium inline-flex items-center gap-1"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 19l-7-7 7-7"
          />
        </svg>
        Back to Dashboard
      </Link>

      {/* Header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{migration.name}</h1>
              <span
                className={cn(
                  'px-2 py-0.5 rounded text-xs font-medium',
                  STATUS_COLORS[migration.status] || STATUS_COLORS.created
                )}
              >
                {migration.status}
              </span>
            </div>
            <p className="text-sm text-gray-500 mt-1">
              Created {formatDate(migration.created_at)}
            </p>
            {migration.aws_connection_id && (
              <p className="text-xs text-gray-400 mt-0.5">
                Connection: {migration.aws_connection_id}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleRunSkill}
              disabled={selectedIds.size === 0 || skillRunning}
              className={cn(
                'px-4 py-2 rounded-lg font-medium text-sm',
                selectedIds.size > 0
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-200 text-gray-400 cursor-not-allowed'
              )}
            >
              {skillRunning
                ? 'Running...'
                : `Run Translation Job (${selectedIds.size})`}
            </button>
            <button
              onClick={handleDeleteMigration}
              disabled={deleteMigration.isPending}
              className="px-4 py-2 rounded-lg font-medium text-sm bg-white border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              {deleteMigration.isPending ? 'Deleting...' : 'Delete Migration'}
            </button>
          </div>
        </div>
      </div>

      {/* Instance-based Discovery Section */}
      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        <h2 className="text-lg font-semibold">Resource Discovery</h2>
        <p className="text-sm text-gray-600">
          Discover AWS resources to include in this migration. Select a specific
          EC2 instance to scope discovery, or extract all resources at once.
        </p>

        {extractError && (
          <div
            className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm"
            role="alert"
          >
            {extractError}
            <button
              onClick={() => setExtractError(null)}
              className="ml-2 font-medium underline hover:no-underline"
            >
              Dismiss
            </button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-4">
          {/* Instance-based discovery */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={handleOpenInstanceModal}
              className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm"
            >
              Select Instance
            </button>
            {selectedInstance && (
              <span className="text-sm text-gray-700 bg-green-50 border border-green-200 px-3 py-1.5 rounded-lg inline-flex items-center gap-2">
                <span className="truncate max-w-[200px]">
                  {selectedInstance.name || selectedInstance.aws_arn}
                </span>
                <button
                  onClick={() => setSelectedInstance(null)}
                  className="text-gray-400 hover:text-gray-600 flex-shrink-0"
                  aria-label="Clear instance selection"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            )}
            {selectedInstance && (
              <button
                onClick={handleExtractByInstance}
                disabled={extractingInstance}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium text-sm disabled:opacity-50"
              >
                {extractingInstance ? 'Discovering...' : 'Discover Resources'}
              </button>
            )}
          </div>

          {/* Vertical divider */}
          <div className="hidden sm:block h-8 w-px bg-gray-300" aria-hidden="true" />

          {/* Full extraction */}
          <button
            onClick={handleExtractAll}
            disabled={extracting}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm disabled:opacity-50"
          >
            {extracting ? 'Extracting...' : 'Extract All Resources'}
          </button>

          {/* Vertical divider */}
          <div className="hidden sm:block h-8 w-px bg-gray-300" aria-hidden="true" />

          {/* Manual upload */}
          <button
            onClick={() => { setUploadFile(null); setUploadError(''); setShowUploadModal(true); }}
            className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm"
          >
            Manually Upload Resource
          </button>
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-label="Upload Resource File"
        >
          <div className="fixed inset-0 bg-black/40" onClick={() => setShowUploadModal(false)} aria-hidden="true" />
          <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 flex flex-col">
            <div className="p-6 border-b flex items-center justify-between">
              <h3 className="text-lg font-semibold">Upload Resource File</h3>
              <button onClick={() => setShowUploadModal(false)} className="text-gray-400 hover:text-gray-600" aria-label="Close">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label htmlFor="upload-file-type" className="block text-sm font-medium text-gray-700 mb-1">
                  File Type
                </label>
                <select
                  id="upload-file-type"
                  value={uploadFileType}
                  onChange={(e) => setUploadFileType(e.target.value)}
                  className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                className={cn(
                  'border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors',
                  isDragging
                    ? 'border-blue-500 bg-blue-50'
                    : uploadFile
                      ? 'border-green-400 bg-green-50'
                      : 'border-gray-300 hover:border-gray-400 bg-gray-50'
                )}
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
                  <div className="space-y-1">
                    <p className="text-green-700 font-medium text-sm">{uploadFile.name}</p>
                    <p className="text-xs text-gray-500">Click to replace</p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="text-gray-600 font-medium text-sm">Drop file here or click to browse</p>
                    <p className="text-xs text-gray-400">JSON, CSV, or LOG files (max 10 MB)</p>
                  </div>
                )}
              </div>
              {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}
              {uploadToMigration.isError && (
                <p className="text-sm text-red-600">
                  {(uploadToMigration.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Upload failed.'}
                </p>
              )}
            </div>
            <div className="p-6 border-t flex items-center justify-end gap-3">
              <button
                onClick={() => setShowUploadModal(false)}
                className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleUploadSubmit}
                disabled={!uploadFile || uploadToMigration.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium text-sm"
              >
                {uploadToMigration.isPending ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Resources Table */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h2 className="text-lg font-semibold">
            Resources{' '}
            {allResources.length > 0 && (
              <span className="text-sm font-normal text-gray-500">
                ({allResources.length} total
                {selectedIds.size > 0 && `, ${selectedIds.size} selected`})
              </span>
            )}
          </h2>
          <div className="flex items-center gap-3">
            {/* Type filter */}
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="text-sm border border-gray-300 rounded-lg px-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Filter by resource type"
            >
              <option value="">All Types</option>
              {uniqueTypes.map((t) => (
                <option key={t} value={t}>
                  {shortType(t)}
                </option>
              ))}
            </select>
            {/* Search */}
            <div className="relative">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search resources..."
                className="text-sm border border-gray-300 rounded-lg pl-9 pr-3 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-56"
                aria-label="Search resources"
              />
            </div>
          </div>
        </div>

        {/* Selected resources action bar */}
        {selectedIds.size > 0 && (
          <div className="px-6 py-3 bg-blue-50 border-b flex items-center justify-between gap-4">
            <p className="text-sm text-blue-700 font-medium">
              {selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected
              {skillGroups.size > 1 && (
                <span className="text-blue-500 font-normal">
                  {' '}across {skillGroups.size} translation job types
                </span>
              )}
            </p>
            <button
              onClick={handleRunSkill}
              disabled={skillRunning}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
            >
              {skillRunning ? 'Starting...' : 'Run Translation Jobs on Selected'}
            </button>
          </div>
        )}

        {loadingResources ? (
          <div className="p-6">
            <div className="animate-pulse space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-10 bg-gray-100 rounded" />
              ))}
            </div>
          </div>
        ) : resourcesError ? (
          <div className="p-6 text-center text-red-600">
            Failed to load resources. Please try again.
          </div>
        ) : allResources.length === 0 ? (
          <div className="p-12 text-center">
            <svg
              className="mx-auto w-12 h-12 text-gray-300"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
              />
            </svg>
            <p className="mt-3 text-gray-500 font-medium">No resources yet</p>
            <p className="text-sm text-gray-400 mt-1">
              Use the discovery section above to extract AWS resources, or upload
              a CloudTrail / Flow Log file.
            </p>
          </div>
        ) : filteredResources.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            No resources match your filters.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left w-10">
                    <input
                      type="checkbox"
                      checked={allFilteredSelected}
                      onChange={toggleSelectAll}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      aria-label="Select all resources"
                    />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Type
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Name / ID
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Latest Run
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Run Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Confidence
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredResources.map((r) => (
                  <tr
                    key={r.id}
                    className={cn(
                      'hover:bg-gray-50 transition-colors',
                      selectedIds.has(r.id) && 'bg-blue-50 hover:bg-blue-50'
                    )}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(r.id)}
                        onChange={() => toggleSelect(r.id)}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        aria-label={`Select ${r.name || r.aws_arn}`}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap',
                          getTypeBadgeColor(r.aws_type)
                        )}
                      >
                        {shortType(r.aws_type)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-sm font-medium text-gray-900">
                        {r.name || 'Unnamed'}
                      </p>
                      <p className="text-xs text-gray-400 font-mono truncate max-w-xs">
                        {r.aws_arn}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'px-2 py-0.5 rounded text-xs font-medium',
                          RESOURCE_STATUS_COLORS[r.status] ||
                            'bg-gray-100 text-gray-800'
                        )}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {r.latest_skill_run ? (
                        <Link
                          to={
                            r.latest_skill_run.status === 'complete'
                              ? `/translation-jobs/${r.latest_skill_run.id}/results`
                              : `/translation-jobs/${r.latest_skill_run.id}`
                          }
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium font-mono"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {r.latest_skill_run.skill_type}
                        </Link>
                      ) : (
                        <span className="text-gray-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {r.latest_skill_run ? (
                        <span className={cn(
                          'px-2 py-0.5 rounded text-xs font-medium',
                          r.latest_skill_run.status === 'complete' ? 'bg-green-100 text-green-700' :
                          r.latest_skill_run.status === 'failed' ? 'bg-red-100 text-red-700' :
                          r.latest_skill_run.status === 'running' ? 'bg-blue-100 text-blue-700' :
                          'bg-gray-100 text-gray-700'
                        )}>
                          {r.latest_skill_run.status}
                        </span>
                      ) : (
                        <span className="text-gray-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {r.latest_skill_run?.status === 'complete'
                        ? `${Math.round(r.latest_skill_run.confidence * 100)}%`
                        : <span className="text-gray-400 text-xs">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Plans */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b flex items-center justify-between">
          <h2 className="text-lg font-semibold">Migration Plans</h2>
          <button
            onClick={handleGeneratePlan}
            disabled={generatingPlan}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
          >
            {generatingPlan ? 'Generating...' : 'Generate New Plan'}
          </button>
        </div>
        {planError && <div className="px-6 py-3 text-sm text-red-600">{planError}</div>}
        {loadingPlan ? (
          <div className="p-6"><div className="animate-pulse h-10 bg-gray-100 rounded" /></div>
        ) : !plan ? (
          <div className="p-6 text-center text-gray-500 text-sm">No plans yet. Click "Generate New Plan" to create one.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Generated</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Phases</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="px-4 py-3"><span className={cn('px-2 py-0.5 rounded text-xs font-medium', STATUS_COLORS[plan.status] || 'bg-gray-100 text-gray-800')}>{plan.status}</span></td>
                  <td className="px-4 py-3 text-sm text-gray-500">{formatDate(plan.generated_at || '')}</td>
                  <td className="px-4 py-3 text-sm">{plan.phases?.length ?? 0}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Link to={`/plans/${plan.id}`} className="text-blue-600 hover:text-blue-800 text-sm font-medium">View Plan</Link>
                      <button onClick={handleDeletePlan} disabled={deletePlanMutation.isPending} className="text-red-500 hover:text-red-700 text-sm font-medium disabled:opacity-50">
                        {deletePlanMutation.isPending ? 'Deleting...' : 'Delete'}
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Instance Selection Modal */}
      {showInstanceModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-label="Select EC2 Instance"
        >
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => setShowInstanceModal(false)}
            aria-hidden="true"
          />
          <div className="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
            <div className="p-6 border-b flex items-center justify-between">
              <h3 className="text-lg font-semibold">Select EC2 Instance</h3>
              <button
                onClick={() => setShowInstanceModal(false)}
                className="text-gray-400 hover:text-gray-600"
                aria-label="Close modal"
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
            <div className="p-6 overflow-y-auto flex-1">
              {loadingInstances ? (
                <div className="animate-pulse space-y-3">
                  {[...Array(3)].map((_, i) => (
                    <div key={i} className="h-14 bg-gray-100 rounded" />
                  ))}
                </div>
              ) : instanceError ? (
                <div className="text-center py-4">
                  <p className="text-red-600 text-sm">{instanceError}</p>
                  <button
                    onClick={handleOpenInstanceModal}
                    className="mt-2 text-sm text-blue-600 hover:text-blue-800 font-medium"
                  >
                    Retry
                  </button>
                </div>
              ) : instances.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-4">
                  No EC2 instances found. Make sure your AWS connection is
                  configured and resources have been extracted.
                </p>
              ) : (
                <div className="space-y-2">
                  {instances.map((inst) => (
                    <button
                      key={inst.id}
                      onClick={() => {
                        setSelectedInstance(inst);
                        setShowInstanceModal(false);
                      }}
                      className={cn(
                        'w-full text-left p-3 rounded-lg border transition-colors',
                        selectedInstance?.id === inst.id
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
                      )}
                    >
                      <p className="text-sm font-medium text-gray-900">
                        {inst.name || 'Unnamed Instance'}
                      </p>
                      <p className="text-xs text-gray-500 font-mono mt-0.5 truncate">
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
          className="fixed inset-0 z-50 flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm Translation Jobs"
        >
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => setShowSkillModal(false)}
            aria-hidden="true"
          />
          <div className="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
            <div className="p-6 border-b">
              <h3 className="text-lg font-semibold">Confirm Translation Jobs</h3>
              <p className="text-sm text-gray-500 mt-1">
                {selectedIds.size} resource{selectedIds.size !== 1 ? 's' : ''} selected.
                CloudFormation stacks run individually; other types batch into one translation job per type.
              </p>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {Array.from(skillGroups.entries()).map(([skillType, groupResources]) => {
                const isCfn = skillType === 'cfn_terraform';
                return (
                  <div key={skillType} className="border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-semibold text-gray-900">
                        {SKILL_LABELS[skillType] || skillType}
                      </h4>
                      <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                        {isCfn
                          ? `${groupResources.length} job${groupResources.length !== 1 ? 's' : ''} (1 per stack)`
                          : `${groupResources.length} resource${groupResources.length !== 1 ? 's' : ''} → 1 job`}
                      </span>
                    </div>
                    <ul className="space-y-1.5">
                      {groupResources.map((r) => (
                        <li key={r.id} className="flex items-center gap-2 text-xs text-gray-600">
                          <span className={cn('px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0', getTypeBadgeColor(r.aws_type))}>
                            {shortType(r.aws_type)}
                          </span>
                          <span className="truncate">{r.name || r.aws_arn}</span>
                          {isCfn && (
                            <span className="ml-auto flex-shrink-0 text-gray-400">→ 1 job</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
            <div className="p-6 border-t flex items-center justify-end gap-3">
              <button
                onClick={() => setShowSkillModal(false)}
                className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmSkillRun}
                disabled={skillRunning}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm disabled:opacity-50"
              >
                {skillRunning ? 'Starting...' : 'Run Translation Jobs'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Translation Jobs */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-6 border-b">
          <h2 className="text-lg font-semibold">Translation Jobs</h2>
        </div>
        {migrationSkillRuns.length === 0 ? (
          <div className="p-6 text-center text-gray-500">
            No translation jobs for this migration yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Run Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Confidence</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {migrationSkillRuns.map((sr) => (
                  <tr key={sr.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900 font-medium">
                      {getSkillRunName(sr.skill_type, sr.resource_names, sr.resource_name)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        'px-2 py-0.5 rounded text-xs font-medium',
                        sr.status === 'complete' ? 'bg-green-100 text-green-800' :
                        sr.status === 'running' ? 'bg-blue-100 text-blue-800' :
                        sr.status === 'failed' ? 'bg-red-100 text-red-800' :
                        'bg-gray-100 text-gray-800'
                      )}>
                        {sr.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">{(sr.confidence * 100).toFixed(0)}%</td>
                    <td className="px-4 py-3 text-sm text-gray-500">{formatDate(sr.created_at)}</td>
                    <td className="px-4 py-3">
                      {sr.status === 'complete' ? (
                        <Link to={`/translation-jobs/${sr.id}/results`} className="text-blue-600 hover:text-blue-800 text-sm font-medium">
                          View Results
                        </Link>
                      ) : sr.status === 'running' || sr.status === 'queued' ? (
                        <Link to={`/translation-jobs/${sr.id}`} className="text-blue-600 hover:text-blue-800 text-sm font-medium">
                          View Progress
                        </Link>
                      ) : (
                        <Link to={`/translation-jobs/${sr.id}/results`} className="text-gray-600 hover:text-gray-800 text-sm font-medium">
                          View Details
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

      {/* Assign Resources Modal */}
      {showAssignModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          role="dialog"
          aria-modal="true"
          aria-label="Assign Resources to Migration"
        >
          <div
            className="fixed inset-0 bg-black/40"
            onClick={() => setShowAssignModal(false)}
            aria-hidden="true"
          />
          <div className="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
            <div className="p-6 border-b">
              <h3 className="text-lg font-semibold">Assign Resources to Migration</h3>
              <p className="text-sm text-gray-500 mt-1">
                {extractedResources.length} resource{extractedResources.length !== 1 ? 's' : ''} extracted. Select which to assign to this migration.
              </p>
            </div>
            <div className="p-6 overflow-y-auto flex-1 space-y-2">
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 pb-2 border-b">
                <input
                  type="checkbox"
                  checked={assignSelectedIds.size === extractedResources.length && extractedResources.length > 0}
                  onChange={() => {
                    if (assignSelectedIds.size === extractedResources.length) {
                      setAssignSelectedIds(new Set());
                    } else {
                      setAssignSelectedIds(new Set(extractedResources.map((r) => r.id)));
                    }
                  }}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                Select All
              </label>
              {extractedResources.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm text-gray-700 py-1">
                  <input
                    type="checkbox"
                    checked={assignSelectedIds.has(r.id)}
                    onChange={() => {
                      setAssignSelectedIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(r.id)) next.delete(r.id);
                        else next.add(r.id);
                        return next;
                      });
                    }}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="truncate">{r.name}</span>
                  {r.aws_type && (
                    <span className="text-xs text-gray-400 ml-auto flex-shrink-0">{r.aws_type}</span>
                  )}
                </label>
              ))}
            </div>
            <div className="p-6 border-t flex items-center justify-end gap-3">
              <button
                onClick={() => setShowAssignModal(false)}
                className="px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm"
              >
                Skip
              </button>
              <button
                onClick={handleAssignResources}
                disabled={assignSelectedIds.size === 0 || assigning}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm disabled:opacity-50"
              >
                {assigning ? 'Assigning...' : `Assign Selected (${assignSelectedIds.size})`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
