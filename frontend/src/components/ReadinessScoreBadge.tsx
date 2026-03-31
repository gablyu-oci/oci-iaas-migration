interface ReadinessScoreBadgeProps {
  score: number;
}

export default function ReadinessScoreBadge({ score }: ReadinessScoreBadgeProps) {
  let color: string;
  let bg: string;
  let border: string;

  if (score > 80) {
    color = '#22c55e';
    bg = 'rgba(34,197,94,0.08)';
    border = 'rgba(34,197,94,0.25)';
  } else if (score >= 50) {
    color = '#f59e0b';
    bg = 'rgba(245,158,11,0.08)';
    border = 'rgba(245,158,11,0.25)';
  } else {
    color = '#ef4444';
    bg = 'rgba(239,68,68,0.08)';
    border = 'rgba(239,68,68,0.25)';
  }

  return (
    <span
      className="badge"
      style={{ color, background: bg, borderColor: border }}
      aria-label={`Readiness score: ${score}`}
    >
      {score}
    </span>
  );
}
