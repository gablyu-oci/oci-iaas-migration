import { useState } from 'react';

export interface WorkloadCardProps {
  name: string;
  workloadType: string;
  resourceCount: number;
  resources: { id: string; name: string; aws_type: string }[];
  readinessScore?: number | null;
  sixrStrategy?: string | null;
  totalAwsCost?: number | null;
  totalOciCost?: number | null;
  groupingMethod?: string | null;
  graphSvg?: string | null;
  onClick?: () => void;
  isBound?: boolean;
  onSelect?: () => void;
  onUnbind?: () => void;
  selectLoading?: boolean;
}

const WORKLOAD_CONFIG: Record<string, { label: string; color: string; bg: string; border: string; icon: JSX.Element }> = {
  web_api: {
    label: 'Web/API App',
    color: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    border: 'rgba(37,99,235,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
      </svg>
    ),
  },
  database: {
    label: 'Database',
    color: '#7c3aed',
    bg: 'rgba(124,58,237,0.08)',
    border: 'rgba(124,58,237,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
      </svg>
    ),
  },
  ai_ml: {
    label: 'AI/ML',
    color: '#16a34a',
    bg: 'rgba(22,163,74,0.08)',
    border: 'rgba(22,163,74,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
  },
  container: {
    label: 'Container',
    color: '#0d9488',
    bg: 'rgba(13,148,136,0.08)',
    border: 'rgba(13,148,136,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  data_analytics: {
    label: 'Data & Analytics',
    color: '#ea580c',
    bg: 'rgba(234,88,12,0.08)',
    border: 'rgba(234,88,12,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  serverless: {
    label: 'Serverless',
    color: '#ca8a04',
    bg: 'rgba(202,138,4,0.08)',
    border: 'rgba(202,138,4,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  storage: {
    label: 'Storage',
    color: 'var(--color-text-dim)',
    bg: 'rgba(100,116,139,0.08)',
    border: 'rgba(100,116,139,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
      </svg>
    ),
  },
  batch_hpc: {
    label: 'Batch/HPC',
    color: '#dc2626',
    bg: 'rgba(220,38,38,0.08)',
    border: 'rgba(220,38,38,0.2)',
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
    ),
  },
};

function getConfig(type: string) {
  return WORKLOAD_CONFIG[type] || WORKLOAD_CONFIG.web_api;
}

function shortType(awsType: string): string {
  const parts = awsType.split('::');
  return parts.length >= 3 ? parts.slice(1).join('::') : awsType;
}

function formatMoney(val: number): string {
  return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function resourceSummary(resources: { aws_type: string }[]): string {
  const counts: Record<string, number> = {};
  for (const r of resources) {
    const short = shortType(r.aws_type);
    counts[short] = (counts[short] || 0) + 1;
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([type, count]) => `${count} ${type}`)
    .join(', ');
}

// No longer needed — SVG is passed inline via graphSvg prop

export default function WorkloadCard({
  name,
  workloadType,
  resourceCount,
  resources,
  readinessScore,
  sixrStrategy,
  totalAwsCost,
  totalOciCost,
  graphSvg,
  onClick,
  isBound,
  onSelect,
  onUnbind,
  selectLoading,
}: WorkloadCardProps) {
  const [showGraph, setShowGraph] = useState(false);
  const config = getConfig(workloadType);

  return (
    <div
      className="panel"
      style={{
        overflow: 'hidden',
        border: isBound ? '2px solid var(--color-ember)' : undefined,
        boxShadow: isBound ? '0 0 0 1px var(--color-ember), var(--shadow-card)' : undefined,
      }}
    >
      {/* Color bar */}
      <div style={{ height: '3px', background: config.color }} />

      <div className="panel-body" style={{ padding: '1rem 1.25rem' }}>
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="flex items-center justify-center flex-shrink-0 rounded-lg"
              style={{
                width: '2.5rem',
                height: '2.5rem',
                background: config.bg,
                border: `1px solid ${config.border}`,
                color: config.color,
              }}
            >
              {config.icon}
            </div>
            <div className="min-w-0">
              <h3
                className="text-sm font-semibold truncate"
                style={{ color: 'var(--color-text-bright)', margin: 0 }}
              >
                {name}
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className="badge"
                  style={{
                    background: config.bg,
                    color: config.color,
                    borderColor: config.border,
                    fontSize: '0.625rem',
                  }}
                >
                  {config.label}
                </span>
                <span
                  className="text-xs"
                  style={{ color: 'var(--color-text-dim)' }}
                >
                  {resourceCount} resource{resourceCount !== 1 ? 's' : ''}
                </span>
              </div>
            </div>
          </div>

          {/* Readiness score */}
          {readinessScore != null && (
            <div className="flex-shrink-0 text-right">
              <div
                className="text-lg font-bold"
                style={{
                  color: readinessScore >= 70 ? '#16a34a' : readinessScore >= 40 ? '#d97706' : '#dc2626',
                }}
              >
                {Math.round(readinessScore)}
              </div>
              <div className="text-xs" style={{ color: 'var(--color-rail)' }}>readiness</div>
            </div>
          )}
        </div>

        {/* Resource summary */}
        <p
          className="text-xs mb-3"
          style={{ color: 'var(--color-text-dim)', fontFamily: 'var(--font-mono)' }}
        >
          {resourceSummary(resources)}
        </p>

        {/* Cost comparison */}
        {totalAwsCost != null && totalOciCost != null && (
          <div
            className="flex items-center gap-4 text-xs mb-3 p-2.5 rounded"
            style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)' }}
          >
            <div>
              <span style={{ color: 'var(--color-rail)' }}>AWS: </span>
              <span style={{ color: '#FF9900', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {formatMoney(totalAwsCost)}
              </span>
            </div>
            <svg className="w-3 h-3" style={{ color: 'var(--color-rail)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
            <div>
              <span style={{ color: 'var(--color-rail)' }}>OCI: </span>
              <span style={{ color: '#F80000', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                {formatMoney(totalOciCost)}
              </span>
            </div>
            {totalAwsCost > 0 && totalOciCost < totalAwsCost && (
              <span
                className="badge badge-success"
                style={{ fontSize: '0.5625rem', marginLeft: 'auto' }}
              >
                {Math.round(((totalAwsCost - totalOciCost) / totalAwsCost) * 100)}% savings
              </span>
            )}
          </div>
        )}

        {/* 6R Strategy badge */}
        {sixrStrategy && (
          <div className="mb-3">
            <span className="badge badge-info" style={{ fontSize: '0.625rem' }}>
              {sixrStrategy}
            </span>
          </div>
        )}

        {/* Resource list (collapsible) */}
        <details className="group">
          <summary
            className="flex items-center gap-1.5 text-xs font-medium cursor-pointer list-none"
            style={{ color: 'var(--color-text-dim)' }}
          >
            <svg
              className="w-3 h-3 transition-transform group-open:rotate-90"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            {resourceCount} resource{resourceCount !== 1 ? 's' : ''}
          </summary>
          <div className="mt-2 space-y-1.5 pt-2" style={{ borderTop: '1px solid var(--color-rule)' }}>
            {resources.map((r) => (
              <div
                key={r.id}
                className="flex items-center gap-2 text-xs"
                style={{ color: 'var(--color-text-dim)' }}
              >
                <span className="badge badge-neutral" style={{ fontSize: '0.5625rem' }}>
                  {shortType(r.aws_type)}
                </span>
                <span className="truncate">{r.name || r.id}</span>
              </div>
            ))}
          </div>
        </details>
      </div>

      {/* Bound badge */}
      {isBound && (
        <div
          className="flex items-center gap-2 px-4 py-2"
          style={{ background: 'var(--color-ember-dim)', borderTop: '1px solid var(--color-rule)' }}
        >
          <svg className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--color-ember)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span className="text-xs font-semibold" style={{ color: 'var(--color-ember)' }}>Selected for Migration</span>
        </div>
      )}

      {/* Action bar */}
      {(graphSvg || onClick || onSelect || onUnbind) && (
        <div
          className="flex items-center"
          style={{ borderTop: '1px solid var(--color-rule)' }}
        >
          {graphSvg && (
            <button
              onClick={() => setShowGraph(true)}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 text-xs font-medium transition-colors"
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--color-text-dim)',
                fontFamily: 'inherit',
                borderRight: (onClick || onSelect || onUnbind) ? '1px solid var(--color-rule)' : undefined,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-well)'; e.currentTarget.style.color = 'var(--color-text-bright)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--color-text-dim)'; }}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              View Graph
            </button>
          )}
          {onClick && (
            <button
              onClick={onClick}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 text-xs font-semibold transition-colors"
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--color-ember)',
                fontFamily: 'inherit',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-ember-dim)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              Plan Migration
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </button>
          )}
          {isBound && onUnbind && (
            <button
              onClick={onUnbind}
              disabled={selectLoading}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 text-xs font-medium transition-colors"
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--color-text-dim)',
                fontFamily: 'inherit',
                borderRight: '1px solid var(--color-rule)',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-well)'; e.currentTarget.style.color = '#dc2626'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--color-text-dim)'; }}
            >
              {selectLoading ? <span className="spinner" /> : 'Unbind'}
            </button>
          )}
          {!isBound && onSelect && (
            <button
              onClick={onSelect}
              disabled={selectLoading}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 text-xs font-semibold transition-colors"
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--color-ember)',
                fontFamily: 'inherit',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-ember-dim)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              {selectLoading ? <><span className="spinner" />Selecting...</> : 'Select for Migration'}
            </button>
          )}
        </div>
      )}

      {/* Graph modal */}
      {showGraph && graphSvg && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
          onClick={() => setShowGraph(false)}
        >
          <div
            className="relative rounded-xl overflow-hidden"
            style={{
              background: 'var(--color-surface)',
              border: '1px solid var(--color-rule)',
              maxWidth: '90vw',
              maxHeight: '90vh',
              boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div
              className="flex items-center justify-between px-4 py-3"
              style={{ borderBottom: '1px solid var(--color-rule)' }}
            >
              <div className="flex items-center gap-2">
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ background: config.color }}
                />
                <span className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                  {name} — Dependency Graph
                </span>
              </div>
              <button
                onClick={() => setShowGraph(false)}
                className="flex items-center justify-center rounded-lg"
                style={{
                  width: '2rem',
                  height: '2rem',
                  background: 'var(--color-well)',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--color-text-dim)',
                }}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            {/* Zoom controls */}
            <div
              className="flex items-center gap-3 px-4 py-2"
              style={{ borderBottom: '1px solid var(--color-rule)' }}
            >
              <button
                onClick={() => {
                  const el = document.getElementById('graph-svg-container');
                  const svg = el?.querySelector('svg');
                  const slider = document.getElementById('graph-zoom-slider') as HTMLInputElement;
                  if (!svg || !slider) return;
                  const newVal = Math.max(10, Number(slider.value) - 20);
                  slider.value = String(newVal);
                  svg.style.width = newVal + '%';
                  svg.style.height = 'auto';
                }}
                className="flex items-center justify-center rounded"
                style={{ width: '1.75rem', height: '1.75rem', background: 'var(--color-well)', border: '1px solid var(--color-rule)', cursor: 'pointer', color: 'var(--color-text-dim)', fontSize: '16px', fontWeight: 'bold' }}
              >−</button>
              <input
                id="graph-zoom-slider"
                type="range"
                min="10"
                max="200"
                defaultValue="100"
                style={{ flex: 1, accentColor: '#60a5fa' }}
                onChange={(e) => {
                  const el = document.getElementById('graph-svg-container');
                  const svg = el?.querySelector('svg');
                  if (!svg) return;
                  svg.style.width = e.target.value + '%';
                  svg.style.height = 'auto';
                }}
              />
              <button
                onClick={() => {
                  const el = document.getElementById('graph-svg-container');
                  const svg = el?.querySelector('svg');
                  const slider = document.getElementById('graph-zoom-slider') as HTMLInputElement;
                  if (!svg || !slider) return;
                  const newVal = Math.min(200, Number(slider.value) + 20);
                  slider.value = String(newVal);
                  svg.style.width = newVal + '%';
                  svg.style.height = 'auto';
                }}
                className="flex items-center justify-center rounded"
                style={{ width: '1.75rem', height: '1.75rem', background: 'var(--color-well)', border: '1px solid var(--color-rule)', cursor: 'pointer', color: 'var(--color-text-dim)', fontSize: '16px', fontWeight: 'bold' }}
              >+</button>
              <button
                onClick={() => {
                  const el = document.getElementById('graph-svg-container');
                  const svg = el?.querySelector('svg');
                  const slider = document.getElementById('graph-zoom-slider') as HTMLInputElement;
                  if (!svg || !slider) return;
                  slider.value = '100';
                  svg.style.width = '100%';
                  svg.style.height = 'auto';
                }}
                className="text-xs px-2 py-1 rounded"
                style={{ background: 'var(--color-well)', border: '1px solid var(--color-rule)', cursor: 'pointer', color: 'var(--color-text-dim)' }}
              >Fit</button>
            </div>
            {/* SVG content — fit to window, scrollable */}
            <div
              id="graph-svg-container"
              className="overflow-auto p-4"
              style={{ maxHeight: 'calc(90vh - 110px)' }}
              ref={(el) => {
                if (!el) return;
                const svg = el.querySelector('svg');
                if (svg) {
                  svg.style.width = '100%';
                  svg.style.height = 'auto';
                  svg.style.maxWidth = 'none';
                }
              }}
              dangerouslySetInnerHTML={{ __html: graphSvg! }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
