interface CostBreakdown {
  compute: { aws: number; oci: number };
  storage: { aws: number; oci: number };
  database: { aws: number; oci: number };
  networking: { aws: number; oci: number };
}

interface CostComparisonChartProps {
  breakdown: CostBreakdown;
}

const CATEGORIES: (keyof CostBreakdown)[] = ['compute', 'storage', 'database', 'networking'];

const CATEGORY_LABELS: Record<string, string> = {
  compute: 'Compute',
  storage: 'Storage',
  database: 'Database',
  networking: 'Networking',
};

function formatDollar(val: number): string {
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export default function CostComparisonChart({ breakdown }: CostComparisonChartProps) {
  const maxVal = Math.max(
    ...CATEGORIES.flatMap((cat) => [breakdown[cat].aws, breakdown[cat].oci]),
    1
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      {CATEGORIES.map((cat) => {
        const awsVal = breakdown[cat].aws;
        const ociVal = breakdown[cat].oci;
        const awsPct = (awsVal / maxVal) * 100;
        const ociPct = (ociVal / maxVal) * 100;

        return (
          <div key={cat}>
            <p
              style={{
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'var(--color-text-dim)',
                marginBottom: '0.5rem',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              {CATEGORY_LABELS[cat]}
            </p>

            {/* AWS bar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <span
                style={{
                  width: '2.5rem',
                  fontSize: '0.6875rem',
                  fontWeight: 600,
                  color: '#FF9900',
                  flexShrink: 0,
                }}
              >
                AWS
              </span>
              <div
                style={{
                  flex: 1,
                  background: 'var(--color-well)',
                  borderRadius: '0.25rem',
                  height: '1.25rem',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${Math.max(awsPct, 1)}%`,
                    height: '100%',
                    background: '#FF9900',
                    borderRadius: '0.25rem',
                    transition: 'width 0.3s ease',
                    display: 'flex',
                    alignItems: 'center',
                    paddingLeft: '0.375rem',
                  }}
                >
                  {awsPct > 15 && (
                    <span style={{ fontSize: '0.625rem', fontWeight: 600, color: '#fff' }}>
                      {formatDollar(awsVal)}
                    </span>
                  )}
                </div>
                {awsPct <= 15 && (
                  <span
                    style={{
                      position: 'absolute',
                      left: `calc(${Math.max(awsPct, 1)}% + 0.375rem)`,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      fontSize: '0.625rem',
                      fontWeight: 600,
                      color: '#FF9900',
                    }}
                  >
                    {formatDollar(awsVal)}
                  </span>
                )}
              </div>
            </div>

            {/* OCI bar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span
                style={{
                  width: '2.5rem',
                  fontSize: '0.6875rem',
                  fontWeight: 600,
                  color: '#F80000',
                  flexShrink: 0,
                }}
              >
                OCI
              </span>
              <div
                style={{
                  flex: 1,
                  background: 'var(--color-well)',
                  borderRadius: '0.25rem',
                  height: '1.25rem',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${Math.max(ociPct, 1)}%`,
                    height: '100%',
                    background: '#F80000',
                    borderRadius: '0.25rem',
                    transition: 'width 0.3s ease',
                    display: 'flex',
                    alignItems: 'center',
                    paddingLeft: '0.375rem',
                  }}
                >
                  {ociPct > 15 && (
                    <span style={{ fontSize: '0.625rem', fontWeight: 600, color: '#fff' }}>
                      {formatDollar(ociVal)}
                    </span>
                  )}
                </div>
                {ociPct <= 15 && (
                  <span
                    style={{
                      position: 'absolute',
                      left: `calc(${Math.max(ociPct, 1)}% + 0.375rem)`,
                      top: '50%',
                      transform: 'translateY(-50%)',
                      fontSize: '0.625rem',
                      fontWeight: 600,
                      color: '#F80000',
                    }}
                  >
                    {formatDollar(ociVal)}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}

      {/* Legend */}
      <div style={{ display: 'flex', gap: '1rem', fontSize: '0.6875rem', color: 'var(--color-text-dim)', marginTop: '0.25rem' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
          <span style={{ width: '0.625rem', height: '0.625rem', borderRadius: '0.125rem', background: '#FF9900', display: 'inline-block' }} />
          AWS Current
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
          <span style={{ width: '0.625rem', height: '0.625rem', borderRadius: '0.125rem', background: '#F80000', display: 'inline-block' }} />
          OCI Projected
        </span>
      </div>
    </div>
  );
}
