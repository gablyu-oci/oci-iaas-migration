import { useEffect, useRef } from 'react';
import { useTranslationJobStream, useTranslationJob } from '../api/hooks/useTranslationJobs';
import type { InteractionEvent } from '../api/hooks/useTranslationJobs';

interface Props {
  skillRunId: string;
  onComplete?: () => void;
}

const PHASES = [
  { key: 'queued',       label: 'Queued',       icon: '⏳' },
  { key: 'gap_analysis', label: 'Gap Analysis',  icon: '🔍' },
  { key: 'enhancement',  label: 'Enhancement',   icon: '✨' },
  { key: 'review',       label: 'Review',        icon: '🔎' },
  { key: 'fix',          label: 'Fix',           icon: '🔧' },
  { key: 'complete',     label: 'Complete',      icon: '✅' },
];

const PHASE_ORDER = PHASES.map((p) => p.key);

function phaseIndex(phase: string | null | undefined): number {
  if (!phase) return 0;
  const idx = PHASE_ORDER.indexOf(phase);
  return idx === -1 ? 0 : idx;
}

function formatTime(secs: number): string {
  if (secs < 60) return `${Math.floor(secs)}s`;
  return `${Math.floor(secs / 60)}m ${Math.floor(secs % 60)}s`;
}

const SKILL_LABELS: Record<string, string> = {
  cfn_terraform: 'CloudFormation → Terraform',
  iam_translation: 'IAM Policy Translation',
  dependency_discovery: 'Dependency Discovery',
};

export default function SkillProgressTracker({ skillRunId, onComplete }: Props) {
  const { data: run } = useTranslationJob(skillRunId);
  const { event, interactions } = useTranslationJobStream(skillRunId);
  const completeFired = useRef(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  const phase    = event?.phase   ?? run?.current_phase   ?? 'queued';
  const iteration = event?.iteration ?? run?.current_iteration ?? 0;
  const confidence = event?.confidence ?? run?.confidence ?? 0;
  const status   = event?.status  ?? run?.status  ?? 'queued';
  const elapsed  = event?.elapsed_secs ?? 0;

  const maxIterations =
    (run?.config as Record<string, number> | undefined)?.max_iterations ?? 3;

  const currentPhaseIdx = status === 'complete'
    ? PHASE_ORDER.indexOf('complete')
    : status === 'failed'
    ? -1
    : phaseIndex(phase);

  useEffect(() => {
    if (status === 'complete' && onComplete && !completeFired.current) {
      completeFired.current = true;
      const timer = setTimeout(onComplete, 1200);
      return () => clearTimeout(timer);
    }
  }, [status, onComplete]);

  // Auto-scroll log to bottom on new interactions
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [interactions.length]);

  const confidencePct = Math.round(confidence * 100);
  const isFailed = status === 'failed';
  const isComplete = status === 'complete';
  const isRunning = status === 'running';

  // Confidence ring via SVG
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const strokeDash = (confidencePct / 100) * circumference;

  const ringColor = isFailed
    ? '#ef4444'
    : confidencePct >= 85
    ? '#22c55e'
    : confidencePct >= 65
    ? '#f59e0b'
    : '#3b82f6';

  return (
    <div className="space-y-5">
      {/* Header card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1">
              {SKILL_LABELS[run?.skill_type ?? ''] ?? run?.skill_type ?? 'Skill Run'}
            </p>
            <p className="text-sm text-gray-500 font-mono truncate max-w-xs">
              {skillRunId}
            </p>
          </div>
          <StatusBadge status={status} />
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4">
        {/* Confidence ring */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex flex-col items-center gap-2">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Confidence</p>
          <div className="relative w-20 h-20">
            <svg className="w-20 h-20 -rotate-90" viewBox="0 0 88 88">
              <circle cx="44" cy="44" r={radius} fill="none" stroke="#f3f4f6" strokeWidth="8" />
              <circle
                cx="44" cy="44" r={radius}
                fill="none"
                stroke={ringColor}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${strokeDash} ${circumference}`}
                className="transition-all duration-700"
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-lg font-bold text-gray-800">
              {confidencePct}%
            </span>
          </div>
          <p className="text-xs text-gray-400">
            {confidencePct >= 85 ? 'Approved' : confidencePct >= 65 ? 'With notes' : 'Needs fixes'}
          </p>
        </div>

        {/* Iteration */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex flex-col items-center justify-center gap-1">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Iteration</p>
          <p className="text-4xl font-bold text-gray-800">
            {iteration}
            <span className="text-xl font-normal text-gray-400">/{maxIterations}</span>
          </p>
          <p className="text-xs text-gray-400">enhancement loops</p>
        </div>

        {/* Elapsed */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 flex flex-col items-center justify-center gap-1">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Elapsed</p>
          <p className="text-4xl font-bold text-gray-800 font-mono">{formatTime(elapsed)}</p>
          <p className="text-xs text-gray-400">
            {isRunning ? 'in progress' : isComplete ? 'total' : '—'}
          </p>
        </div>
      </div>

      {/* Phase pipeline */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-5">
          Pipeline
        </p>
        <div className="flex items-center gap-0">
          {PHASES.filter((p) => p.key !== 'queued').map((p, i, arr) => {
            const idx = PHASE_ORDER.indexOf(p.key);
            const done = currentPhaseIdx > idx || isComplete;
            const active = currentPhaseIdx === idx && !isFailed && !isComplete;
            const isLast = i === arr.length - 1;

            return (
              <div key={p.key} className="flex items-center flex-1 min-w-0">
                {/* Step */}
                <div className="flex flex-col items-center flex-shrink-0">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center text-lg transition-all duration-500 ${
                      isFailed && active
                        ? 'bg-red-100 ring-2 ring-red-400'
                        : done || isComplete
                        ? 'bg-green-100'
                        : active
                        ? 'bg-blue-100 ring-2 ring-blue-400 ring-offset-2'
                        : 'bg-gray-100'
                    }`}
                  >
                    {active && isRunning ? (
                      <span className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <span>{p.icon}</span>
                    )}
                  </div>
                  <span
                    className={`text-xs mt-1.5 font-medium text-center leading-tight ${
                      active ? 'text-blue-600' : done ? 'text-green-600' : 'text-gray-400'
                    }`}
                  >
                    {p.label}
                  </span>
                </div>

                {/* Connector */}
                {!isLast && (
                  <div className="flex-1 h-0.5 mx-1 mb-5">
                    <div
                      className={`h-full transition-all duration-700 rounded-full ${
                        done ? 'bg-green-400' : 'bg-gray-200'
                      }`}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Confidence threshold guide */}
      {isRunning && (
        <div className="bg-gray-50 rounded-xl border border-gray-100 px-5 py-4">
          <div className="flex gap-6 justify-center text-xs text-gray-500">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
              ≥ 85% Approved
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
              65–85% Approved with notes
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />
              &lt; 65% Needs fixes
            </span>
          </div>
        </div>
      )}

      {/* Agent interaction log */}
      {(interactions.length > 0 || isRunning) && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Agent Log</p>
            {isRunning && (
              <span className="flex items-center gap-1.5 text-xs text-blue-500">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse inline-block" />
                Live
              </span>
            )}
          </div>
          <div className="max-h-64 overflow-y-auto font-mono text-xs">
            {interactions.length === 0 ? (
              <div className="px-5 py-4 text-gray-400 italic">Waiting for agent activity…</div>
            ) : (
              <table className="min-w-full">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-4 py-2 text-left text-gray-500 font-medium">Agent</th>
                    <th className="px-4 py-2 text-left text-gray-500 font-medium">Iter</th>
                    <th className="px-4 py-2 text-left text-gray-500 font-medium">Decision</th>
                    <th className="px-4 py-2 text-right text-gray-500 font-medium">Conf</th>
                    <th className="px-4 py-2 text-right text-gray-500 font-medium">Tokens</th>
                    <th className="px-4 py-2 text-right text-gray-500 font-medium">Cost</th>
                    <th className="px-4 py-2 text-right text-gray-500 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {interactions.map((ix) => (
                    <InteractionRow key={ix.id} ix={ix} />
                  ))}
                </tbody>
              </table>
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}

const DECISION_STYLES: Record<string, string> = {
  APPROVED: 'text-green-600',
  NEEDS_FIXES: 'text-amber-600',
  REJECTED: 'text-red-600',
};

function InteractionRow({ ix }: { ix: InteractionEvent }) {
  const totalTokens = (ix.tokens_input ?? 0) + (ix.tokens_output ?? 0);
  const decisionStyle = ix.decision ? (DECISION_STYLES[ix.decision] ?? 'text-gray-600') : 'text-gray-400';
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-1.5 text-gray-700 whitespace-nowrap">
        {ix.agent_type ?? '—'}
      </td>
      <td className="px-4 py-1.5 text-gray-500 text-center">
        {ix.iteration ?? '—'}
      </td>
      <td className={`px-4 py-1.5 whitespace-nowrap font-medium ${decisionStyle}`}>
        {ix.decision ?? '—'}
      </td>
      <td className="px-4 py-1.5 text-right text-gray-600">
        {ix.confidence != null ? `${Math.round(ix.confidence * 100)}%` : '—'}
      </td>
      <td className="px-4 py-1.5 text-right text-gray-500">
        {totalTokens > 0 ? totalTokens.toLocaleString() : '—'}
      </td>
      <td className="px-4 py-1.5 text-right text-gray-500">
        {ix.cost_usd != null ? `$${ix.cost_usd.toFixed(4)}` : '—'}
      </td>
      <td className="px-4 py-1.5 text-right text-gray-400">
        {ix.duration_seconds != null ? `${ix.duration_seconds.toFixed(1)}s` : '—'}
      </td>
    </tr>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued:   'bg-gray-100 text-gray-600',
    running:  'bg-blue-100 text-blue-700',
    complete: 'bg-green-100 text-green-700',
    failed:   'bg-red-100 text-red-700',
  };
  const dots: Record<string, string> = {
    queued:   'bg-gray-400',
    running:  'bg-blue-500 animate-pulse',
    complete: 'bg-green-500',
    failed:   'bg-red-500',
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold ${styles[status] ?? styles.queued}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dots[status] ?? dots.queued}`} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
