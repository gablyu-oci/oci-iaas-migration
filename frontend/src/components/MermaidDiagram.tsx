import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#b84a1c',
    primaryTextColor: '#e2e8f0',
    lineColor: '#475569',
    secondaryColor: '#1e293b',
    tertiaryColor: '#0f172a',
  },
  flowchart: { curve: 'basis' },
});

interface Props {
  chart: string;
}

export default function MermaidDiagram({ chart }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chart || !containerRef.current) return;

    const id = `mermaid-${Date.now()}`;
    mermaid.render(id, chart).then(
      ({ svg }) => {
        if (containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      },
      (err) => {
        setError(String(err));
      },
    );
  }, [chart]);

  if (error) {
    return (
      <div className="rounded-lg p-4" style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}>
        <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>Could not render diagram</p>
        <pre className="text-xs mt-2 overflow-auto" style={{ color: 'var(--color-error)' }}>{error}</pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="rounded-lg overflow-auto"
      style={{
        background: '#0d1221',
        border: '1px solid var(--color-fence)',
        padding: '1rem',
        minHeight: '200px',
      }}
    />
  );
}
