interface OSCompatBadgeProps {
  status: string;
}

const STATUS_MAP: Record<string, { label: string; color: string; bg: string; border: string }> = {
  compatible: {
    label: 'Compatible',
    color: '#22c55e',
    bg: 'rgba(34,197,94,0.08)',
    border: 'rgba(34,197,94,0.25)',
  },
  compatible_with_remediation: {
    label: 'Needs Remediation',
    color: '#f59e0b',
    bg: 'rgba(245,158,11,0.08)',
    border: 'rgba(245,158,11,0.25)',
  },
  incompatible: {
    label: 'Incompatible',
    color: '#ef4444',
    bg: 'rgba(239,68,68,0.08)',
    border: 'rgba(239,68,68,0.25)',
  },
  unknown: {
    label: 'Unknown',
    color: '#6b7280',
    bg: 'rgba(107,114,128,0.08)',
    border: 'rgba(107,114,128,0.25)',
  },
};

export default function OSCompatBadge({ status }: OSCompatBadgeProps) {
  const info = STATUS_MAP[status] || STATUS_MAP.unknown;

  return (
    <span
      className="badge"
      style={{
        color: info.color,
        background: info.bg,
        borderColor: info.border,
      }}
      aria-label={`OS compatibility: ${info.label}`}
    >
      {info.label}
    </span>
  );
}
