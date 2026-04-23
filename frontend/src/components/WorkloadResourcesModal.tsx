import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import client from '../api/client';
import ResourceDetailModal from './ResourceDetailModal';

// ─── Type-based color palette ──────────────────────────────────────────────
// Colors the AWS-type badge by service category so scanning a workload's
// resource list is faster than parsing prefixes. Badge text stays legible
// on both light and dark themes by pairing a translucent background with
// the saturated foreground color.

function typeColor(awsTypeShort: string): { bg: string; fg: string; border: string } {
  const s = awsTypeShort;
  // Storage — volumes, S3, EFS, FSx, snapshots, images
  if (/::Volume|::Snapshot|::Image|S3::|EFS::|FSx::/.test(s)) {
    return { bg: 'rgba(37,99,235,0.12)', fg: '#2563eb', border: 'rgba(37,99,235,0.3)' };
  }
  // Network — VPC, subnet, SG, gateways, peering, route-tables, IPs
  if (/::VPC|::Subnet|::SecurityGroup|::NetworkInterface|::InternetGateway|::NatGateway|::RouteTable|::EIP|::NetworkAcl|::VPCPeering|::TransitGateway|::VPNConnection|::VPNGateway|::CustomerGateway|::VPCEndpoint|Route53::|DirectConnect::/.test(s)) {
    return { bg: 'rgba(13,148,136,0.12)', fg: '#0d9488', border: 'rgba(13,148,136,0.3)' };
  }
  // Compute — EC2 instances, ASGs, launch templates, key pairs
  if (/EC2::Instance|AutoScaling::|LaunchTemplate|LaunchConfiguration|::KeyPair|::SpotFleet/.test(s)) {
    return { bg: 'rgba(234,88,12,0.12)', fg: '#ea580c', border: 'rgba(234,88,12,0.3)' };
  }
  // Database
  if (/RDS::|DynamoDB::|DocDB::|Neptune::|ElastiCache::|OpenSearchService::|Redshift::|DAX::|MSK::|Timestream::/.test(s)) {
    return { bg: 'rgba(124,58,237,0.12)', fg: '#7c3aed', border: 'rgba(124,58,237,0.3)' };
  }
  // Load balancing
  if (/ElasticLoadBalancing/.test(s)) {
    return { bg: 'rgba(79,70,229,0.12)', fg: '#4f46e5', border: 'rgba(79,70,229,0.3)' };
  }
  // Security (IAM, KMS, Secrets, SSM, ACM, WAF)
  if (/IAM::|KMS::|SecretsManager::|SSM::|CertificateManager::|WAFv2::/.test(s)) {
    return { bg: 'rgba(220,38,38,0.12)', fg: '#dc2626', border: 'rgba(220,38,38,0.3)' };
  }
  // Serverless / containers
  if (/Lambda::|ApiGateway::|ApiGatewayV2::|StepFunctions::|Events::|Kinesis::|ECS::|EKS::|ECR::/.test(s)) {
    return { bg: 'rgba(202,138,4,0.12)', fg: '#ca8a04', border: 'rgba(202,138,4,0.3)' };
  }
  // Observability / messaging
  if (/CloudWatch::|Logs::|SNS::|SQS::|CloudTrail::/.test(s)) {
    return { bg: 'rgba(22,163,74,0.12)', fg: '#16a34a', border: 'rgba(22,163,74,0.3)' };
  }
  // IaC / CDN
  if (/CloudFormation::|CloudFront::/.test(s)) {
    return { bg: 'rgba(100,116,139,0.12)', fg: '#64748b', border: 'rgba(100,116,139,0.3)' };
  }
  return { bg: 'var(--color-well)', fg: 'var(--color-text-dim)', border: 'var(--color-rule)' };
}

function TypeBadge({ awsTypeShort }: { awsTypeShort: string }) {
  const c = typeColor(awsTypeShort);
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium whitespace-nowrap"
      style={{ background: c.bg, color: c.fg, border: `1px solid ${c.border}`, fontFamily: 'var(--font-mono)' }}
    >
      {awsTypeShort}
    </span>
  );
}

// ─── Types ────────────────────────────────────────────────────────────────

interface OCIMapping {
  aws_type?: string | null;
  oci_service?: string | null;
  oci_resource_label?: string | null;
  oci_terraform?: string | null;
  skill?: string | null;
  confidence?: 'high' | 'medium' | 'low' | null;
  notes?: string[];
  gaps?: string[];
}

interface UsageSummary {
  cpu_p95?: number | null;
  mem_p95?: number | null;
  net_in_p95?: number | null;
  net_out_p95?: number | null;
  disk_read_p95?: number | null;
  disk_write_p95?: number | null;
}

interface OCMCompat {
  level: 'full' | 'with_prep' | 'manual' | 'unsupported';
  matched_rule?: string | null;
}

interface WorkloadResourceRow {
  id: string;
  aws_type: string;
  aws_type_short: string;
  name: string;
  aws_arn: string;
  aws_config_summary: string;
  usage: UsageSummary | null;
  oci_mapping_raw: OCIMapping | null;
  ocm_compatibility: OCMCompat | null;
  raw_config: Record<string, unknown>;
}

// ─── Data hook ────────────────────────────────────────────────────────────

function useWorkloadResourceDetails(appGroupId: string | null) {
  return useQuery<WorkloadResourceRow[]>({
    queryKey: ['workload-resources', appGroupId],
    queryFn: async () =>
      (await client.get(`/api/app-groups/${appGroupId}/resource-details`)).data,
    enabled: !!appGroupId,
  });
}

// ─── Sub-renderers ────────────────────────────────────────────────────────

function OCMBadge({ level }: { level: string | null | undefined }) {
  if (!level) return <span style={{ color: 'var(--color-text-dim)', fontSize: '0.625rem' }}>—</span>;
  const map: Record<string, { label: string; bg: string; fg: string }> = {
    full:        { label: 'ready',  bg: 'rgba(74, 153, 85, 0.12)',  fg: 'var(--color-success, #4a9955)' },
    with_prep:   { label: 'prep',   bg: 'rgba(217, 160, 32, 0.12)', fg: 'var(--color-warning, #d9a020)' },
    manual:      { label: 'manual', bg: 'rgba(217, 160, 32, 0.12)', fg: 'var(--color-warning, #d9a020)' },
    unsupported: { label: 'no-go',  bg: 'rgba(217, 52, 52, 0.12)',  fg: 'var(--color-danger,  #d93434)' },
  };
  const s = map[level] ?? { label: level, bg: 'var(--color-well)', fg: 'var(--color-text-dim)' };
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium"
      style={{ background: s.bg, color: s.fg, fontFamily: 'var(--font-mono)' }}
    >
      {s.label}
    </span>
  );
}

function UsageCell({ usage }: { usage: UsageSummary | null }) {
  if (!usage) return <span style={{ color: 'var(--color-text-dim)' }}>no metrics</span>;
  const bits: string[] = [];
  if (usage.cpu_p95 != null) bits.push(`cpu ${usage.cpu_p95}%`);
  if (usage.mem_p95 != null) bits.push(`mem ${usage.mem_p95}%`);
  if (usage.net_in_p95 != null && usage.net_in_p95 > 0) {
    const mb = Math.round(usage.net_in_p95 / 1e6);
    bits.push(`net-in ${mb}MB/s`);
  }
  if (bits.length === 0) return <span style={{ color: 'var(--color-text-dim)' }}>no metrics</span>;
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem' }}>
      {bits.join(' · ')}
    </span>
  );
}

function OCIMappingCell({ mapping }: { mapping: OCIMapping | null }) {
  if (!mapping) return <span style={{ color: 'var(--color-text-dim)' }}>unmapped</span>;
  return (
    <div style={{ lineHeight: 1.3 }}>
      <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem' }}>
        {mapping.oci_terraform || '—'}
      </code>
      {mapping.oci_service && (
        <div className="text-[10px]" style={{ color: 'var(--color-text-dim)' }}>
          {mapping.oci_service}
        </div>
      )}
    </div>
  );
}

// ─── Main modal ────────────────────────────────────────────────────────────

export default function WorkloadResourcesModal({
  appGroupId,
  workloadName,
  onClose,
}: {
  appGroupId: string;
  workloadName: string;
  onClose: () => void;
}) {
  const { data: rows, isLoading, error } = useWorkloadResourceDetails(appGroupId);
  const [detailResource, setDetailResource] = useState<WorkloadResourceRow | null>(null);
  const [filter, setFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('');

  const filteredRows = useMemo(() => {
    if (!rows) return [];
    const q = filter.trim().toLowerCase();
    return rows.filter((r) => {
      if (typeFilter && r.aws_type !== typeFilter) return false;
      if (!q) return true;
      return (
        r.name.toLowerCase().includes(q) ||
        r.aws_type.toLowerCase().includes(q) ||
        r.aws_config_summary.toLowerCase().includes(q)
      );
    });
  }, [rows, filter, typeFilter]);

  const uniqueTypes = useMemo(() => {
    const set = new Set((rows ?? []).map((r) => r.aws_type));
    return Array.from(set).sort();
  }, [rows]);

  return (
    <>
      <div
        className="modal-overlay"
        role="dialog"
        aria-modal="true"
        aria-label={`Resources in ${workloadName}`}
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      >
        <div
          className="modal"
          style={{
            maxWidth: '1400px',
            width: '95vw',
            maxHeight: '92vh',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div className="modal-header">
            <div>
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                Resources in {workloadName}
              </h3>
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
                {rows?.length ?? 0} resource{(rows?.length ?? 0) === 1 ? '' : 's'}
                {filteredRows.length !== rows?.length && (
                  <> · {filteredRows.length} shown</>
                )}
              </p>
            </div>
            <button
              onClick={onClose}
              className="btn btn-ghost btn-sm"
              aria-label="Close modal"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Filter bar */}
          {rows && rows.length > 0 && (
            <div
              className="px-4 py-2 flex items-center gap-2"
              style={{ borderBottom: '1px solid var(--color-rule)' }}
            >
              <input
                type="search"
                placeholder="Filter by name, type, or config…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="rounded px-2 py-1 text-xs flex-1"
                style={{
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  color: 'var(--color-text-bright)',
                }}
              />
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="rounded px-2 py-1 text-xs"
                style={{
                  background: 'var(--color-well)',
                  border: '1px solid var(--color-rule)',
                  color: 'var(--color-text-bright)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                <option value="">All types ({uniqueTypes.length})</option>
                {uniqueTypes.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          )}

          <div className="modal-body overflow-auto flex-1 p-0">
            {isLoading && (
              <div className="p-4 space-y-2">
                {[...Array(6)].map((_, i) => <div key={i} className="skel h-10 rounded" />)}
              </div>
            )}
            {error && (
              <div className="p-4">
                <p className="text-xs" style={{ color: 'var(--color-danger, #d33)' }}>
                  Failed to load: {(error as Error).message}
                </p>
              </div>
            )}
            {!isLoading && !error && filteredRows.length === 0 && (
              <div className="empty-state p-8">
                <p>No resources match.</p>
              </div>
            )}
            {!isLoading && !error && filteredRows.length > 0 && (
              <table className="dt" style={{ width: '100%' }}>
                <thead style={{ position: 'sticky', top: 0, zIndex: 1, background: 'var(--color-raised)' }}>
                  <tr>
                    <th>Type</th>
                    <th>Name</th>
                    <th style={{ minWidth: '20rem' }}>AWS Config</th>
                    <th>Usage (14d p95)</th>
                    <th>OCI Mapping</th>
                    <th>OCM</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <TypeBadge awsTypeShort={r.aws_type_short} />
                      </td>
                      <td className="td-primary" style={{ maxWidth: '14rem' }}>
                        <span className="truncate block" title={r.name}>{r.name || '—'}</span>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.6875rem', fontFamily: 'var(--font-mono)', color: 'var(--color-text-bright)' }}>
                          {r.aws_config_summary}
                        </span>
                      </td>
                      <td>
                        <UsageCell usage={r.usage} />
                      </td>
                      <td>
                        <OCIMappingCell mapping={r.oci_mapping_raw} />
                      </td>
                      <td>
                        <OCMBadge level={r.ocm_compatibility?.level} />
                      </td>
                      <td>
                        <button
                          onClick={() => setDetailResource(r)}
                          className="btn btn-ghost btn-sm"
                          style={{ fontSize: '0.6875rem' }}
                        >
                          View detail
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Full detail modal (Details / Raw Config / Translation Jobs tabs) —
          same experience as clicking a row on the Resources page. */}
      {detailResource && (
        <ResourceDetailModal
          resource={{
            id: detailResource.id,
            name: detailResource.name,
            aws_type: detailResource.aws_type,
            aws_arn: detailResource.aws_arn,
            raw_config: detailResource.raw_config,
          }}
          onClose={() => setDetailResource(null)}
        />
      )}
    </>
  );
}
