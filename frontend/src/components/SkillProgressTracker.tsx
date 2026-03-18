import { useEffect, useRef } from 'react';
import { useSkillRunStream, useSkillRun } from '../api/hooks/useSkillRuns';
import { cn } from '../lib/utils';

interface Props {
  skillRunId: string;
  onComplete?: () => void;
}

export default function SkillProgressTracker({ skillRunId, onComplete }: Props) {
  const { data: run } = useSkillRun(skillRunId);
  const { event } = useSkillRunStream(skillRunId);
  const completeFired = useRef(false);

  const phase = event?.phase || run?.current_phase || 'queued';
  const iteration = event?.iteration || run?.current_iteration || 0;
  const confidence = event?.confidence || run?.confidence || 0;
  const status = event?.status || run?.status || 'queued';
  const elapsed = event?.elapsed_secs || 0;

  const maxIterations =
    (run?.config as Record<string, number> | undefined)?.max_iterations || 3;

  useEffect(() => {
    if (status === 'complete' && onComplete && !completeFired.current) {
      completeFired.current = true;
      const timer = setTimeout(onComplete, 500);
      return () => clearTimeout(timer);
    }
  }, [status, onComplete]);

  const statusColors: Record<string, string> = {
    queued: 'bg-gray-100 text-gray-800',
    running: 'bg-blue-100 text-blue-800',
    complete: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Skill Run Progress</h3>
        <span
          className={cn(
            'px-3 py-1 rounded-full text-sm font-medium',
            statusColors[status] || statusColors.queued
          )}
        >
          {status.toUpperCase()}
        </span>
      </div>

      <div className="text-center py-4">
        <p className="text-2xl font-mono">
          Round {iteration} of {maxIterations} &middot;{' '}
          <span className="text-blue-600">{phase}</span> phase &middot;{' '}
          <span className="text-green-600">
            {(confidence * 100).toFixed(0)}%
          </span>{' '}
          confidence &middot; {elapsed.toFixed(0)}s
        </p>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-3">
        <div
          className={cn(
            'h-3 rounded-full transition-all duration-500',
            status === 'failed'
              ? 'bg-red-500'
              : status === 'complete'
                ? 'bg-green-500'
                : 'bg-blue-500'
          )}
          style={{ width: `${Math.min(confidence * 100, 100)}%` }}
        />
      </div>

      {status === 'running' && (
        <div className="flex justify-center">
          <div
            className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"
            role="status"
            aria-label="Loading"
          />
        </div>
      )}
    </div>
  );
}
