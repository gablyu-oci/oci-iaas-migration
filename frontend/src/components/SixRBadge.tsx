interface SixRBadgeProps {
  strategy: string;
  confidence?: string;
}

const STRATEGY_COLORS: Record<string, string> = {
  Rehost: '#3b82f6',
  Replatform: '#8b5cf6',
  Refactor: '#06b6d4',
  Repurchase: '#f59e0b',
  Retire: '#6b7280',
  Retain: '#ef4444',
};

export default function SixRBadge({ strategy, confidence }: SixRBadgeProps) {
  const color = STRATEGY_COLORS[strategy] || '#64748b';

  return (
    <span
      className="badge"
      style={{
        color,
        background: `${color}14`,
        borderColor: `${color}40`,
      }}
      aria-label={`Strategy: ${strategy}${confidence ? `, confidence: ${confidence}` : ''}`}
    >
      {strategy}
      {confidence && (
        <span
          style={{
            width: '0.375rem',
            height: '0.375rem',
            borderRadius: '50%',
            background: color,
            display: 'inline-block',
            marginLeft: '0.25rem',
            opacity: confidence === 'high' ? 1 : confidence === 'medium' ? 0.6 : 0.3,
          }}
          title={`Confidence: ${confidence}`}
        />
      )}
    </span>
  );
}
