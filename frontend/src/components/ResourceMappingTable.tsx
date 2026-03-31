import { useState, useEffect } from 'react';
import client from '../api/client';

interface ResourceMapping {
  aws_resource_id: string;
  aws_type: string;
  aws_name: string;
  aws_config_summary: string;
  oci_resource_type: string;
  oci_shape: string;
  oci_config_summary: string;
  mapping_confidence: string;
  notes: string[];
  gaps: string[];
  aws_monthly_cost: number | null;
  oci_monthly_cost: number | null;
}

const CONFIDENCE_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  high:   { bg: 'rgba(22,163,74,0.1)',  color: '#16a34a', label: 'High' },
  medium: { bg: 'rgba(217,119,6,0.1)',  color: '#d97706', label: 'Medium' },
  low:    { bg: 'rgba(220,38,38,0.1)',  color: '#dc2626', label: 'Low' },
};

function shortType(awsType: string): string {
  return awsType.replace('AWS::', '').replace('Local DB', 'DB');
}

export default function ResourceMappingTable({ appGroupId }: { appGroupId: string }) {
  const [mappings, setMappings] = useState<ResourceMapping[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!appGroupId) return;
    setLoading(true);
    setError(null);
    client
      .get(`/api/app-groups/${appGroupId}/resource-mapping`)
      .then((res) => setMappings(res.data))
      .catch((err) => setError(err?.message || 'Failed to load mapping'))
      .finally(() => setLoading(false));
  }, [appGroupId]);

  if (loading) {
    return (
      <div className="rounded-xl p-6" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)' }}>
        <div className="flex items-center gap-3 mb-4">
          <span className="spinner flex-shrink-0" />
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--color-text-bright)' }}>
              Loading resource mapping
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-dim)' }}>
              Mapping AWS resources to OCI equivalents with AI-assisted review…
            </p>
          </div>
        </div>
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="skel h-12 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg p-4 text-center" style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}>
        <p className="text-xs" style={{ color: 'var(--color-error)' }}>{error}</p>
      </div>
    );
  }

  if (!mappings || mappings.length === 0) {
    return (
      <div className="rounded-lg p-4 text-center" style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}>
        <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>No resource mappings available</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--color-rule)' }}>
      <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'var(--color-raised)', borderBottom: '1px solid var(--color-rule)' }}>
            <th className="text-left px-3 py-2.5 font-semibold" style={{ color: 'var(--color-text-dim)' }}>AWS Resource</th>
            <th className="text-left px-3 py-2.5 font-semibold" style={{ color: 'var(--color-text-dim)' }}>
              <span style={{ fontSize: '0.75rem' }}>→</span>
            </th>
            <th className="text-left px-3 py-2.5 font-semibold" style={{ color: 'var(--color-text-dim)' }}>OCI Target</th>
            <th className="text-center px-3 py-2.5 font-semibold" style={{ color: 'var(--color-text-dim)' }}>Confidence</th>
            <th className="text-left px-3 py-2.5 font-semibold" style={{ color: 'var(--color-text-dim)' }}>Notes</th>
          </tr>
        </thead>
        <tbody>
          {mappings.map((m, i) => {
            const conf = CONFIDENCE_STYLES[m.mapping_confidence] || CONFIDENCE_STYLES.low;
            return (
              <tr
                key={`${m.aws_resource_id}-${i}`}
                style={{
                  borderBottom: '1px solid var(--color-rule)',
                  background: i % 2 === 0 ? 'var(--color-surface)' : 'var(--color-well)',
                }}
              >
                {/* AWS side */}
                <td className="px-3 py-2.5">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium" style={{ color: 'var(--color-text-bright)' }}>
                      {m.aws_name}
                    </span>
                    <span style={{ color: 'var(--color-text-dim)', fontSize: '0.625rem' }}>
                      {shortType(m.aws_type)}
                    </span>
                    {m.aws_config_summary && (
                      <span style={{ color: 'var(--color-rail)', fontSize: '0.625rem', fontFamily: 'var(--font-mono)' }}>
                        {m.aws_config_summary}
                      </span>
                    )}
                  </div>
                </td>

                {/* Arrow */}
                <td className="px-1 text-center" style={{ color: 'var(--color-ember)' }}>
                  <svg className="w-4 h-4 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </td>

                {/* OCI side */}
                <td className="px-3 py-2.5">
                  <div className="flex flex-col gap-0.5">
                    <span className="font-medium" style={{ color: '#F80000' }}>
                      {m.oci_resource_type}
                    </span>
                    {m.oci_shape && (
                      <span style={{ color: 'var(--color-text-dim)', fontSize: '0.625rem', fontFamily: 'var(--font-mono)' }}>
                        {m.oci_shape}
                      </span>
                    )}
                    {m.oci_config_summary && (
                      <span style={{ color: 'var(--color-rail)', fontSize: '0.625rem' }}>
                        {m.oci_config_summary}
                      </span>
                    )}
                  </div>
                </td>

                {/* Confidence */}
                <td className="px-3 py-2.5 text-center">
                  <span
                    className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                    style={{ background: conf.bg, color: conf.color }}
                  >
                    {conf.label}
                  </span>
                </td>

                {/* Notes & Gaps */}
                <td className="px-3 py-2.5" style={{ maxWidth: '200px' }}>
                  {m.notes.map((n, j) => (
                    <div key={j} className="flex gap-1 items-start" style={{ color: 'var(--color-text-dim)', fontSize: '0.625rem' }}>
                      <span style={{ color: 'var(--color-success)', flexShrink: 0 }}>+</span>
                      <span>{n}</span>
                    </div>
                  ))}
                  {m.gaps.map((g, j) => (
                    <div key={`g-${j}`} className="flex gap-1 items-start" style={{ color: 'var(--color-warning)', fontSize: '0.625rem' }}>
                      <span style={{ flexShrink: 0 }}>!</span>
                      <span>{g}</span>
                    </div>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Cost summary */}
      {mappings.some(m => m.aws_monthly_cost || m.oci_monthly_cost) && (
        <div
          className="px-3 py-2.5 flex items-center gap-6 text-xs"
          style={{ background: 'var(--color-raised)', borderTop: '1px solid var(--color-rule)' }}
        >
          <span style={{ color: 'var(--color-text-dim)' }}>Monthly Cost:</span>
          <span>
            <span style={{ color: 'var(--color-text-dim)' }}>AWS </span>
            <span style={{ color: '#FF9900', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              ${mappings.reduce((sum, m) => sum + (m.aws_monthly_cost || 0), 0).toFixed(2)}
            </span>
          </span>
          <span style={{ color: 'var(--color-rail)' }}>→</span>
          <span>
            <span style={{ color: 'var(--color-text-dim)' }}>OCI </span>
            <span style={{ color: '#F80000', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              ${mappings.reduce((sum, m) => sum + (m.oci_monthly_cost || 0), 0).toFixed(2)}
            </span>
          </span>
        </div>
      )}
    </div>
  );
}
