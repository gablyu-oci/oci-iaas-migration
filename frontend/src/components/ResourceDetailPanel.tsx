import { useQuery } from '@tanstack/react-query';
import client from '../api/client';

interface DetailRow {
  label: string;
  value: string | number | boolean;
  hint?: string;
}

interface DetailSection {
  title: string;
  rows: DetailRow[];
}

interface OCIMapping {
  aws_type: string;
  oci_service: string | null;
  oci_resource_label: string | null;
  oci_terraform: string | null;
  skill: string | null;
  confidence: 'high' | 'medium' | 'low' | null;
  notes: string[];
  gaps: string[];
}

interface RightsizingPreview {
  recommended_oci_shape: string;
  ocpus: number;
  memory_gb: number;
  monthly_cost: number;
  aws_monthly_cost: number;
  confidence: 'high' | 'medium' | 'low';
  notes: string[];
}

interface MetricBucket {
  avg?: number;
  p95?: number;
  max?: number;
}

interface OCMCompatibility {
  supported: boolean;
  level: 'full' | 'with_prep' | 'manual' | 'unsupported';
  matched_rule: string | null;
  reason: string;
  alternative: string;
  prep_steps: string[];
  notes: string[];
  detected_os: string;
}

interface ResourceDetails {
  id: string;
  aws_type: string | null;
  aws_arn: string | null;
  name: string | null;
  status: string;
  created_at: string;
  raw_config: Record<string, unknown> | null;
  oci_mapping: OCIMapping | null;
  summary: Record<string, string | number | boolean>;
  sections: DetailSection[];
  rightsizing: RightsizingPreview | null;
  ocm_compatibility: OCMCompatibility | null;
  metrics: Record<string, MetricBucket> | null;
  software_inventory: {
    os_name?: string;
    os_version?: string;
    kernel?: string;
    installed_applications?: { name: string; version: string; publisher?: string }[];
  } | null;
}

function useResourceDetails(resourceId: string | null) {
  return useQuery<ResourceDetails>({
    queryKey: ['resource-details', resourceId],
    queryFn: async () => (await client.get(`/api/aws/resources/${resourceId}/details`)).data,
    enabled: !!resourceId,
  });
}

// ─── Reusable pieces ──────────────────────────────────────────────────────────

function ConfidenceBadge({ confidence }: { confidence: string | null | undefined }) {
  if (!confidence) return null;
  const color =
    confidence === 'high' ? 'var(--color-success, #4a9)' :
    confidence === 'medium' ? 'var(--color-warning, #d90)' :
    'var(--color-danger, #d33)';
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium"
      style={{ background: 'var(--color-well)', border: `1px solid ${color}`, color }}
    >
      {confidence}
    </span>
  );
}

function Row({ row }: { row: DetailRow }) {
  const value = typeof row.value === 'boolean' ? (row.value ? 'yes' : 'no') : String(row.value);
  return (
    <div className="flex items-start justify-between gap-4 py-1.5">
      <span className="text-xs shrink-0" style={{ color: 'var(--color-text-dim)', minWidth: '11rem' }}>
        {row.label}
      </span>
      <span
        className="text-xs text-right break-all"
        style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}
      >
        {value}
        {row.hint ? (
          <span className="block text-[10px] mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
            {row.hint}
          </span>
        ) : null}
      </span>
    </div>
  );
}

function SectionCard({ section }: { section: DetailSection }) {
  if (!section.rows || section.rows.length === 0) return null;
  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-fence)' }}
    >
      <p className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-bright)' }}>
        {section.title}
      </p>
      <div style={{ borderTop: '1px dashed var(--color-fence)' }}>
        {section.rows.map((row, i) => <Row key={`${row.label}-${i}`} row={row} />)}
      </div>
    </div>
  );
}

function SummaryStrip({ summary }: { summary: Record<string, string | number | boolean> }) {
  const entries = Object.entries(summary);
  if (entries.length === 0) return null;
  return (
    <div
      className="rounded-lg p-3 grid gap-3"
      style={{
        background: 'var(--color-well)',
        border: '1px solid var(--color-fence)',
        gridTemplateColumns: `repeat(${Math.min(entries.length, 4)}, 1fr)`,
      }}
    >
      {entries.map(([label, value]) => (
        <div key={label}>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>
            {label}
          </p>
          <p
            className="text-sm mt-0.5 break-all"
            style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}
          >
            {typeof value === 'boolean' ? (value ? 'yes' : 'no') : String(value)}
          </p>
        </div>
      ))}
    </div>
  );
}

function OCIMappingCard({ mapping }: { mapping: OCIMapping | null }) {
  if (!mapping) return null;
  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-fence)' }}
    >
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>
          OCI target
        </p>
        <ConfidenceBadge confidence={mapping.confidence} />
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs" style={{ color: 'var(--color-text-bright)' }}>
        <div>
          <span style={{ color: 'var(--color-text-dim)' }}>Service:</span>{' '}
          {mapping.oci_service || '—'}
        </div>
        <div>
          <span style={{ color: 'var(--color-text-dim)' }}>Terraform:</span>{' '}
          <code style={{ fontFamily: 'var(--font-mono)' }}>{mapping.oci_terraform || '—'}</code>
        </div>
        <div>
          <span style={{ color: 'var(--color-text-dim)' }}>Skill:</span>{' '}
          <code style={{ fontFamily: 'var(--font-mono)' }}>{mapping.skill || '—'}</code>
        </div>
        <div>
          <span style={{ color: 'var(--color-text-dim)' }}>Resource:</span>{' '}
          {mapping.oci_resource_label || '—'}
        </div>
      </div>
      {mapping.notes && mapping.notes.length > 0 && (
        <div className="mt-2">
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>Notes</p>
          <ul className="text-xs mt-1 list-disc pl-4" style={{ color: 'var(--color-text-dim)' }}>
            {mapping.notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
      {mapping.gaps && mapping.gaps.length > 0 && (
        <div className="mt-2">
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-danger, #d33)' }}>
            Gaps
          </p>
          <ul className="text-xs mt-1 list-disc pl-4" style={{ color: 'var(--color-danger, #d33)' }}>
            {mapping.gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function RightsizingCard({ rightsizing }: { rightsizing: RightsizingPreview | null }) {
  if (!rightsizing) return null;
  const savingsPct = rightsizing.aws_monthly_cost > 0
    ? Math.round((1 - rightsizing.monthly_cost / rightsizing.aws_monthly_cost) * 1000) / 10
    : null;
  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-fence)' }}
    >
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>
          Rightsizing preview
        </p>
        <ConfidenceBadge confidence={rightsizing.confidence} />
      </div>
      <div className="grid grid-cols-4 gap-3 mb-2">
        <div>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>Shape</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}>
            {rightsizing.recommended_oci_shape}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>OCPU / Mem</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-bright)' }}>
            {rightsizing.ocpus} / {rightsizing.memory_gb}G
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>Monthly (OCI)</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-bright)' }}>
            ${rightsizing.monthly_cost.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>
            Monthly (AWS) {savingsPct !== null && savingsPct > 0 ? `— ${savingsPct}% savings` : ''}
          </p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-bright)' }}>
            ${rightsizing.aws_monthly_cost.toFixed(2)}
          </p>
        </div>
      </div>
      {rightsizing.notes.length > 0 && (
        <ul className="text-[11px] mt-1 list-disc pl-4" style={{ color: 'var(--color-text-dim)' }}>
          {rightsizing.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </div>
  );
}

function MetricsCard({ metrics }: { metrics: Record<string, MetricBucket> | null }) {
  if (!metrics || Object.keys(metrics).length === 0) return null;
  const rows = Object.entries(metrics).map(([name, bucket]) => ({
    name,
    avg: bucket.avg,
    p95: bucket.p95,
    max: bucket.max,
  }));
  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-fence)' }}
    >
      <p className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-bright)' }}>
        CloudWatch (last 14 days)
      </p>
      <table className="w-full text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
        <thead style={{ color: 'var(--color-text-dim)' }}>
          <tr>
            <th className="text-left py-1 font-normal">Metric</th>
            <th className="text-right py-1 font-normal">avg</th>
            <th className="text-right py-1 font-normal">p95</th>
            <th className="text-right py-1 font-normal">max</th>
          </tr>
        </thead>
        <tbody style={{ color: 'var(--color-text-bright)' }}>
          {rows.map((r) => (
            <tr key={r.name} style={{ borderTop: '1px dashed var(--color-fence)' }}>
              <td className="py-1">{r.name}</td>
              <td className="text-right py-1">{r.avg ?? '—'}</td>
              <td className="text-right py-1">{r.p95 ?? '—'}</td>
              <td className="text-right py-1">{r.max ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OCMCompatibilityCard({ compat }: { compat: OCMCompatibility | null }) {
  if (!compat) return null;
  const { level } = compat;
  const badge =
    level === 'full'        ? { label: '✓ OCM-ready',       color: 'var(--color-success, #4a9)' } :
    level === 'with_prep'   ? { label: '⚠ OCM — needs prep', color: 'var(--color-warning, #d90)' } :
    level === 'manual'      ? { label: '⚠ OCM — manual review', color: 'var(--color-warning, #d90)' } :
                              { label: '✗ Not OCM-compatible', color: 'var(--color-danger, #d33)' };

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-fence)' }}
    >
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold" style={{ color: 'var(--color-text-bright)' }}>
          Oracle Cloud Migrations compatibility
        </p>
        <span
          className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium"
          style={{ background: 'var(--color-well)', border: `1px solid ${badge.color}`, color: badge.color }}
        >
          {badge.label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs mb-2">
        <div>
          <span style={{ color: 'var(--color-text-dim)' }}>Detected OS:</span>{' '}
          <span style={{ color: 'var(--color-text-bright)' }}>{compat.detected_os || '—'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--color-text-dim)' }}>Rule matched:</span>{' '}
          <code style={{ fontFamily: 'var(--font-mono)' }}>{compat.matched_rule || '—'}</code>
        </div>
      </div>
      {compat.reason && (
        <p className="text-xs mb-2" style={{ color: 'var(--color-text-dim)' }}>
          <strong style={{ color: 'var(--color-text-bright)' }}>Why:</strong> {compat.reason}
        </p>
      )}
      {compat.alternative && (
        <p className="text-xs mb-2" style={{ color: 'var(--color-text-dim)' }}>
          <strong style={{ color: 'var(--color-text-bright)' }}>Alternative:</strong> {compat.alternative}
        </p>
      )}
      {compat.prep_steps.length > 0 && (
        <div className="mt-2">
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>
            Prep steps required
          </p>
          <ol className="text-xs mt-1 list-decimal pl-4 space-y-0.5" style={{ color: 'var(--color-text-dim)' }}>
            {compat.prep_steps.map((s, i) => <li key={i}>{s}</li>)}
          </ol>
        </div>
      )}
      {compat.notes.length > 0 && (
        <ul className="text-[11px] mt-2 list-disc pl-4" style={{ color: 'var(--color-text-dim)' }}>
          {compat.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </div>
  );
}


function SoftwareInventoryCard({
  inventory,
}: {
  inventory: ResourceDetails['software_inventory'];
}) {
  if (!inventory) return null;
  const apps = inventory.installed_applications || [];
  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-fence)' }}
    >
      <p className="text-xs font-semibold mb-2" style={{ color: 'var(--color-text-bright)' }}>
        Software inventory (SSM)
      </p>
      <div className="grid grid-cols-3 gap-3 mb-2 text-xs">
        <div>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>OS</p>
          <p style={{ color: 'var(--color-text-bright)' }}>{inventory.os_name || '—'}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>OS version</p>
          <p style={{ color: 'var(--color-text-bright)' }}>{inventory.os_version || '—'}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-text-dim)' }}>Kernel</p>
          <p style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}>
            {inventory.kernel || '—'}
          </p>
        </div>
      </div>
      {apps.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wide mb-1" style={{ color: 'var(--color-text-dim)' }}>
            Installed apps ({apps.length})
          </p>
          <ul className="text-xs space-y-0.5">
            {apps.map((a, i) => (
              <li key={`${a.name}-${i}`} style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}>
                {a.name} {a.version ? <span style={{ color: 'var(--color-text-dim)' }}>{a.version}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Main panel ──────────────────────────────────────────────────────────────

export default function ResourceDetailPanel({ resourceId }: { resourceId: string }) {
  const { data, isLoading, error } = useResourceDetails(resourceId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(4)].map((_, i) => <div key={i} className="skel rounded-lg" style={{ height: '80px' }} />)}
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-lg p-3" style={{ background: 'var(--color-well)', border: '1px solid var(--color-danger, #d33)' }}>
        <p className="text-xs" style={{ color: 'var(--color-danger, #d33)' }}>
          Failed to load resource details: {(error as Error).message}
        </p>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="space-y-3">
      <SummaryStrip summary={data.summary} />
      <OCIMappingCard mapping={data.oci_mapping} />
      <OCMCompatibilityCard compat={data.ocm_compatibility} />
      <RightsizingCard rightsizing={data.rightsizing} />
      {data.sections.map((s, i) => <SectionCard key={`${s.title}-${i}`} section={s} />)}
      <MetricsCard metrics={data.metrics} />
      <SoftwareInventoryCard inventory={data.software_inventory} />
    </div>
  );
}
