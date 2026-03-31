import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useMigration } from '../api/hooks/useMigrations';
import { useLatestSynthesis } from '../api/plans';
import {
  useTranslationJobArtifacts,
  downloadArtifactsAsZip,
} from '../api/hooks/useTranslationJobs';
import type { Artifact } from '../api/hooks/useTranslationJobs';
import { formatDate } from '../lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github.css';
import client from '../api/client';

// -- Helpers ------------------------------------------------------------------

function isTerraform(a: Artifact) {
  return a.file_name.endsWith('.tf') || a.file_name.endsWith('.tfvars');
}

function isMarkdown(a: Artifact) {
  return a.file_name.endsWith('.md');
}

async function downloadFile(artifactId: string, fileName: string): Promise<void> {
  const token = localStorage.getItem('token');
  const resp = await client.get(`/api/artifacts/${artifactId}/download`, {
    responseType: 'blob',
    params: { token },
  });
  const url = URL.createObjectURL(resp.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const DECISION_COLOR: Record<string, string> = {
  APPROVED: '#16a34a',
  APPROVED_WITH_NOTES: '#d97706',
  NEEDS_FIXES: '#dc2626',
};

const DECISION_LABEL: Record<string, string> = {
  APPROVED: 'Approved',
  APPROVED_WITH_NOTES: 'Approved with notes',
  NEEDS_FIXES: 'Needs fixes',
};

const DECISION_BADGE: Record<string, string> = {
  APPROVED: 'badge badge-success',
  APPROVED_WITH_NOTES: 'badge badge-warning',
  NEEDS_FIXES: 'badge badge-error',
};

// -- Phase parsing ------------------------------------------------------------

interface ParsedPhase {
  number: number;
  name: string;
  checklist: { text: string; checked: boolean }[];
  fileRefs: string[];
  rawText: string;
}

/** Map of keywords to terraform file prefix patterns */
const KEYWORD_FILE_MAP: Record<string, string[]> = {
  network: ['01-networking', 'networking'],
  networking: ['01-networking', 'networking'],
  vcn: ['01-networking', 'networking'],
  subnet: ['01-networking', 'networking'],
  database: ['02-database', 'database'],
  db: ['02-database', 'database'],
  rds: ['02-database', 'database'],
  compute: ['03-compute', 'compute'],
  instance: ['03-compute', 'compute'],
  ec2: ['03-compute', 'compute'],
  server: ['03-compute', 'compute'],
  iam: ['iam', '04-iam'],
  loadbalancer: ['05-loadbalancer', 'loadbalancer', 'load-balancer'],
  storage: ['04-storage', 'storage'],
};

function parseRunbookPhases(markdown: string): ParsedPhase[] {
  // Split by ## Phase or ## Step headings
  const phaseRegex = /^##\s+(?:Phase|Step)\s+(\d+)[:\s]*(.*)$/gim;
  const phases: ParsedPhase[] = [];
  const matches: { index: number; number: number; name: string }[] = [];

  let match: RegExpExecArray | null;
  while ((match = phaseRegex.exec(markdown)) !== null) {
    matches.push({
      index: match.index,
      number: parseInt(match[1], 10),
      name: match[2].trim(),
    });
  }

  if (matches.length === 0) return [];

  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].index;
    const end = i + 1 < matches.length ? matches[i + 1].index : markdown.length;
    const body = markdown.slice(start, end);

    // Extract checklist items
    const checklistRegex = /^[-*]\s*\[([ xX])\]\s*(.+)$/gm;
    const checklist: { text: string; checked: boolean }[] = [];
    let clMatch: RegExpExecArray | null;
    while ((clMatch = checklistRegex.exec(body)) !== null) {
      checklist.push({
        checked: clMatch[1].toLowerCase() === 'x',
        text: clMatch[2].trim(),
      });
    }

    // Extract explicit .tf file references
    const tfRefRegex = /[\w-]+\.tf(?:vars)?/g;
    const fileRefs: string[] = [];
    let tfMatch: RegExpExecArray | null;
    while ((tfMatch = tfRefRegex.exec(body)) !== null) {
      if (!fileRefs.includes(tfMatch[0])) {
        fileRefs.push(tfMatch[0]);
      }
    }

    phases.push({
      number: matches[i].number,
      name: matches[i].name,
      checklist,
      fileRefs,
      rawText: body,
    });
  }

  return phases;
}

function matchArtifactsToPhase(
  phase: ParsedPhase,
  tfArtifacts: Artifact[],
): Artifact[] {
  const matched: Artifact[] = [];

  for (const art of tfArtifacts) {
    // Direct filename match from parsed file references
    if (phase.fileRefs.some((ref) => art.file_name === ref)) {
      matched.push(art);
      continue;
    }

    // Keyword-based matching from phase name and body text
    const searchText = (phase.name + ' ' + phase.rawText).toLowerCase();
    for (const [keyword, prefixes] of Object.entries(KEYWORD_FILE_MAP)) {
      if (searchText.includes(keyword)) {
        const baseName = art.file_name.replace(/\.tf(vars)?$/, '').toLowerCase();
        if (prefixes.some((p) => baseName.includes(p))) {
          matched.push(art);
          break;
        }
      }
    }
  }

  // Deduplicate
  const seen = new Set<string>();
  return matched.filter((a) => {
    if (seen.has(a.id)) return false;
    seen.add(a.id);
    return true;
  });
}

function buildFallbackPhases(tfArtifacts: Artifact[]): ParsedPhase[] {
  return tfArtifacts.map((art, i) => ({
    number: i + 1,
    name: art.file_name.replace(/\.tf(vars)?$/, '').replace(/^\d+-/, ''),
    checklist: [
      { text: `terraform init`, checked: false },
      { text: `terraform plan -target=module.${art.file_name.replace(/\.tf$/, '')}`, checked: false },
      { text: `terraform apply`, checked: false },
    ],
    fileRefs: [art.file_name],
    rawText: '',
  }));
}

// -- Icons --------------------------------------------------------------------

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className="w-4 h-4 transition-transform"
      style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
    </svg>
  );
}

function DownloadIcon({ size = 4 }: { size?: number }) {
  return (
    <svg className={`w-${size} h-${size}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
      />
    </svg>
  );
}

function FileIcon({ isTf, isMd }: { isTf: boolean; isMd: boolean }) {
  if (isTf) {
    return (
      <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
        />
      </svg>
    );
  }
  if (isMd) {
    return (
      <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    );
  }
  return (
    <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
      />
    </svg>
  );
}

// -- Markdown preview modal ---------------------------------------------------

function MarkdownModal({
  title,
  content,
  onClose,
}: {
  title: string;
  content: string;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={onClose}
    >
      <div
        className="panel"
        style={{ width: '90vw', maxWidth: 800, maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="panel-header flex items-center justify-between"
          style={{ flexShrink: 0 }}
        >
          <span className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}>
            {title}
          </span>
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm"
            aria-label="Close"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div
          className="panel-body prose prose-sm max-w-none overflow-y-auto"
          style={{ flex: 1, color: 'var(--color-text-bright)' }}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

// -- Main Page ----------------------------------------------------------------

export default function MigrationSynthesisResults() {
  const { id } = useParams<{ id: string }>();
  const { data: migration } = useMigration(id || '');
  const { data: synthesisJob, isLoading: loadingSynthesis } = useLatestSynthesis(id || '');
  const { data: artifacts, isLoading: loadingArtifacts } = useTranslationJobArtifacts(
    synthesisJob?.id || '',
  );

  // Accordion state: which phases are expanded
  const [expandedPhases, setExpandedPhases] = useState<Set<number>>(new Set([1]));
  // All-files panel open/closed
  const [allFilesOpen, setAllFilesOpen] = useState(false);
  // Content cache for fetched markdown
  const [contentCache, setContentCache] = useState<Record<string, string>>({});
  const [contentLoading, setContentLoading] = useState<Record<string, boolean>>({});
  // Special attention content
  const [specialAttentionContent, setSpecialAttentionContent] = useState<string | null>(null);
  // Runbook content
  const [runbookContent, setRunbookContent] = useState<string | null>(null);
  // Summary modal
  const [showSummaryModal, setShowSummaryModal] = useState(false);
  const [summaryContent, setSummaryContent] = useState<string | null>(null);
  // Download-all loading
  const [zipping, setZipping] = useState(false);
  // Individual download loading
  const [downloading, setDownloading] = useState<Set<string>>(new Set());

  // Derived lists
  const allArtifacts = artifacts ?? [];
  const tfFiles = allArtifacts
    .filter(isTerraform)
    .sort((a, b) => a.file_name.localeCompare(b.file_name));
  const mdFiles = allArtifacts
    .filter(isMarkdown)
    .sort((a, b) => a.file_name.localeCompare(b.file_name));
  const allFiles = [...tfFiles, ...mdFiles];

  const specialAttentionArtifact = allArtifacts.find((a) => a.file_name === 'special-attention.md') ?? null;
  const runbookArtifact = allArtifacts.find((a) => a.file_name === 'migration-runbook.md') ?? null;
  const summaryArtifact = allArtifacts.find((a) => a.file_name === 'synthesis-summary.md') ?? null;

  // Confidence / decision
  const confidence = synthesisJob?.confidence ?? 0;
  const confidencePct = Math.round(confidence * 100);
  const decision = synthesisJob
    ? confidencePct >= 85
      ? 'APPROVED'
      : confidencePct >= 65
        ? 'APPROVED_WITH_NOTES'
        : 'NEEDS_FIXES'
    : null;

  // Fetch a specific artifact's text content
  const fetchContent = useCallback(
    async (artifactId: string): Promise<string> => {
      if (contentCache[artifactId]) return contentCache[artifactId];
      setContentLoading((prev) => ({ ...prev, [artifactId]: true }));
      try {
        const token = localStorage.getItem('token');
        const resp = await client.get(`/api/artifacts/${artifactId}/download`, {
          responseType: 'text',
          params: { token },
        });
        const text = typeof resp.data === 'string' ? resp.data : String(resp.data);
        setContentCache((prev) => ({ ...prev, [artifactId]: text }));
        return text;
      } catch {
        const fallback = '(Failed to load content)';
        setContentCache((prev) => ({ ...prev, [artifactId]: fallback }));
        return fallback;
      } finally {
        setContentLoading((prev) => ({ ...prev, [artifactId]: false }));
      }
    },
    [contentCache],
  );

  // Load special-attention.md and migration-runbook.md when artifacts are available
  useEffect(() => {
    if (specialAttentionArtifact && !specialAttentionContent && !contentLoading[specialAttentionArtifact.id]) {
      fetchContent(specialAttentionArtifact.id).then(setSpecialAttentionContent);
    }
  }, [specialAttentionArtifact, specialAttentionContent, contentLoading, fetchContent]);

  useEffect(() => {
    if (runbookArtifact && !runbookContent && !contentLoading[runbookArtifact.id]) {
      fetchContent(runbookArtifact.id).then(setRunbookContent);
    }
  }, [runbookArtifact, runbookContent, contentLoading, fetchContent]);

  // Parse phases from runbook or build fallback
  const parsedPhases: ParsedPhase[] =
    runbookContent && parseRunbookPhases(runbookContent).length > 0
      ? parseRunbookPhases(runbookContent)
      : tfFiles.length > 0
        ? buildFallbackPhases(tfFiles)
        : [];

  // Parse special attention items (bullet points / lines)
  const attentionItems: string[] = specialAttentionContent
    ? specialAttentionContent
        .split('\n')
        .filter((line) => /^[-*]\s+/.test(line.trim()))
        .map((line) => line.trim().replace(/^[-*]\s+/, ''))
    : [];

  // Map attention items to phases by keyword overlap
  function getPhaseAttentionItems(phase: ParsedPhase): string[] {
    if (!attentionItems.length) return [];
    const phaseText = (phase.name + ' ' + phase.rawText).toLowerCase();
    return attentionItems.filter((item) => {
      const words = item.toLowerCase().split(/\s+/);
      // Check if any significant word from the attention item appears in the phase text
      return words.some(
        (w) => w.length > 3 && phaseText.includes(w),
      );
    });
  }

  // Toggle accordion
  const togglePhase = (num: number) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num);
      else next.add(num);
      return next;
    });
  };

  // Download all terraform files as zip
  const handleDownloadAll = async () => {
    if (tfFiles.length === 0) return;
    setZipping(true);
    try {
      await downloadArtifactsAsZip(tfFiles.map((a) => a.id));
    } finally {
      setZipping(false);
    }
  };

  // Download a single file
  const handleDownloadFile = async (artifact: Artifact) => {
    setDownloading((prev) => new Set(prev).add(artifact.id));
    try {
      await downloadFile(artifact.id, artifact.file_name);
    } finally {
      setDownloading((prev) => {
        const next = new Set(prev);
        next.delete(artifact.id);
        return next;
      });
    }
  };

  // View summary modal
  const handleViewSummary = async () => {
    if (!summaryArtifact) return;
    if (!summaryContent) {
      const text = await fetchContent(summaryArtifact.id);
      setSummaryContent(text);
    }
    setShowSummaryModal(true);
  };

  // -- Loading / empty states -------------------------------------------------

  if (loadingSynthesis) {
    return (
      <div className="flex justify-center py-20">
        <span className="spinner spinner-lg" />
      </div>
    );
  }

  if (!synthesisJob) {
    return (
      <div className="space-y-4">
        <Link to={`/migrations/${id}`} className="back-link">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Migration
        </Link>
        <div className="alert alert-error">No synthesis job found for this migration.</div>
      </div>
    );
  }

  // -- Render -----------------------------------------------------------------

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Summary modal */}
      {showSummaryModal && summaryContent && (
        <MarkdownModal
          title="synthesis-summary.md"
          content={summaryContent}
          onClose={() => setShowSummaryModal(false)}
        />
      )}

      {/* ── 1. Header ── */}
      <div>
        <Link to={`/migrations/${id}`} className="back-link">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {migration?.name ?? 'Migration'}
        </Link>

        <div className="flex items-start justify-between gap-4 mt-1">
          <div>
            <h1 className="page-title">Migration Plan</h1>
            {synthesisJob.completed_at && (
              <p className="page-subtitle">Generated {formatDate(synthesisJob.completed_at)}</p>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {tfFiles.length > 0 && (
              <button
                onClick={handleDownloadAll}
                disabled={zipping}
                className="btn btn-primary flex items-center gap-2"
              >
                <DownloadIcon />
                {zipping ? (
                  <>
                    <span className="spinner" style={{ width: 14, height: 14 }} />
                    Zipping...
                  </>
                ) : (
                  `Download All (${tfFiles.length})`
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── 2. Overview Stats ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Confidence */}
        <div className="panel panel-body flex items-center gap-4">
          <div className="relative w-14 h-14 flex-shrink-0">
            <svg className="w-14 h-14" style={{ transform: 'rotate(-90deg)' }} viewBox="0 0 56 56">
              <circle cx="28" cy="28" r="22" fill="none" stroke="var(--color-well)" strokeWidth="6" />
              <circle
                cx="28"
                cy="28"
                r="22"
                fill="none"
                stroke={decision ? DECISION_COLOR[decision] : '#94a3b8'}
                strokeWidth="6"
                strokeLinecap="round"
                strokeDasharray={`${(confidencePct / 100) * (2 * Math.PI * 22)} ${2 * Math.PI * 22}`}
                style={{ transition: 'stroke-dasharray 0.6s ease' }}
              />
            </svg>
            <span
              className="absolute inset-0 flex items-center justify-center text-sm font-bold"
              style={{ color: 'var(--color-text-bright)' }}
            >
              {confidencePct}%
            </span>
          </div>
          <div>
            <p className="field-label">Confidence</p>
            {decision && (
              <span className={`${DECISION_BADGE[decision]} mt-1`}>
                {DECISION_LABEL[decision]}
              </span>
            )}
          </div>
        </div>

        {/* File count */}
        <div className="panel panel-body">
          <p className="field-label">Output Files</p>
          <p className="text-2xl font-bold mt-1" style={{ color: 'var(--color-text-bright)' }}>
            {loadingArtifacts ? (
              <span className="skel" style={{ display: 'inline-block', width: 40, height: 28 }} />
            ) : (
              allFiles.length
            )}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-dim)' }}>
            {tfFiles.length} Terraform &middot; {mdFiles.length} docs
          </p>
        </div>

        {/* Quick reference */}
        <div className="panel panel-body flex flex-col justify-between">
          <p className="field-label">Migration Summary</p>
          {summaryArtifact ? (
            <button
              onClick={handleViewSummary}
              className="text-sm font-medium mt-2 text-left hover:opacity-75 transition-opacity"
              style={{
                color: 'var(--color-ember)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 0,
              }}
            >
              View full summary &rarr;
            </button>
          ) : (
            <p className="text-xs mt-1" style={{ color: 'var(--color-text-dim)' }}>
              No summary available
            </p>
          )}
          <p className="text-xs mt-1" style={{ color: 'var(--color-rail)' }}>
            Phases &middot; attention items &middot; pre-apply checklist
          </p>
        </div>
      </div>

      {/* ── 3. Special Attention Banner ── */}
      {specialAttentionArtifact && attentionItems.length > 0 && (
        <div className="alert alert-warning">
          <div className="flex items-start gap-3">
            <WarningIcon />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold mb-1">Special Attention Required</p>
              <ul className="text-sm space-y-1" style={{ margin: 0, paddingLeft: '1.25rem' }}>
                {attentionItems.slice(0, 5).map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
                {attentionItems.length > 5 && (
                  <li style={{ color: 'var(--color-text-dim)' }}>
                    and {attentionItems.length - 5} more items...
                  </li>
                )}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* ── 4. Multi-Phase Accordion ── */}
      {loadingArtifacts ? (
        <div className="panel panel-body space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="skel" style={{ height: 56 }} />
          ))}
        </div>
      ) : parsedPhases.length > 0 ? (
        <div className="space-y-3">
          <h2
            className="text-base font-semibold"
            style={{ color: 'var(--color-text-bright)' }}
          >
            Migration Phases
          </h2>
          {parsedPhases.map((phase) => {
            const isOpen = expandedPhases.has(phase.number);
            const phaseArtifacts = matchArtifactsToPhase(phase, tfFiles);
            const phaseAttention = getPhaseAttentionItems(phase);
            const completedCount = phase.checklist.filter((c) => c.checked).length;
            const totalCount = phase.checklist.length;

            return (
              <div key={phase.number} className="panel overflow-hidden">
                {/* Accordion header */}
                <button
                  onClick={() => togglePhase(phase.number)}
                  className="w-full flex items-center gap-3 px-5 py-4 text-left transition-colors"
                  style={{
                    background: isOpen ? 'var(--color-well)' : 'var(--color-surface)',
                    border: 'none',
                    cursor: 'pointer',
                    borderBottom: isOpen ? '1px solid var(--color-rule)' : 'none',
                  }}
                  aria-expanded={isOpen}
                  aria-controls={`phase-${phase.number}-content`}
                >
                  <span style={{ color: 'var(--color-text-dim)' }}>
                    <ChevronIcon open={isOpen} />
                  </span>
                  <span
                    className="flex items-center gap-2 flex-1 min-w-0"
                  >
                    <span
                      className="text-xs font-bold px-2 py-0.5 rounded"
                      style={{
                        background: 'var(--color-ember)',
                        color: '#fff',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {phase.number}
                    </span>
                    <span className="text-sm font-semibold truncate" style={{ color: 'var(--color-text-bright)' }}>
                      {phase.name}
                    </span>
                  </span>
                  <span className="flex items-center gap-2 flex-shrink-0">
                    {totalCount > 0 && (
                      <span className="badge badge-neutral text-xs">
                        {completedCount}/{totalCount}
                      </span>
                    )}
                    {phaseArtifacts.length > 0 && (
                      <span className="badge badge-info text-xs">
                        {phaseArtifacts.length} file{phaseArtifacts.length !== 1 ? 's' : ''}
                      </span>
                    )}
                  </span>
                </button>

                {/* Accordion body */}
                {isOpen && (
                  <div
                    id={`phase-${phase.number}-content`}
                    className="px-5 py-4 space-y-4"
                    style={{ background: 'var(--color-surface)' }}
                  >
                    {/* Phase attention items */}
                    {phaseAttention.length > 0 && (
                      <div
                        className="alert alert-warning"
                        style={{ margin: 0 }}
                      >
                        <div className="flex items-start gap-2">
                          <WarningIcon />
                          <div>
                            <p className="text-xs font-semibold mb-1">Attention for this phase</p>
                            <ul className="text-xs space-y-0.5" style={{ margin: 0, paddingLeft: '1rem' }}>
                              {phaseAttention.map((item, i) => (
                                <li key={i}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Checklist */}
                    {phase.checklist.length > 0 && (
                      <div>
                        <p
                          className="text-xs font-semibold uppercase tracking-widest mb-2"
                          style={{ color: 'var(--color-text-dim)' }}
                        >
                          Checklist
                        </p>
                        <div className="space-y-1.5">
                          {phase.checklist.map((item, i) => (
                            <label
                              key={i}
                              className="flex items-start gap-2 text-sm"
                              style={{ color: 'var(--color-text)', cursor: 'default' }}
                            >
                              <input
                                type="checkbox"
                                className="cb flex-shrink-0 mt-0.5"
                                defaultChecked={item.checked}
                                aria-label={item.text}
                              />
                              <span
                                style={{
                                  fontFamily: item.text.includes('terraform')
                                    ? 'var(--font-mono)'
                                    : undefined,
                                  fontSize: item.text.includes('terraform') ? '0.8125rem' : undefined,
                                }}
                              >
                                {item.text}
                              </span>
                            </label>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Terraform files for this phase */}
                    {phaseArtifacts.length > 0 && (
                      <div>
                        <p
                          className="text-xs font-semibold uppercase tracking-widest mb-2"
                          style={{ color: 'var(--color-text-dim)' }}
                        >
                          Files
                        </p>
                        <div className="space-y-1">
                          {phaseArtifacts.map((art) => (
                            <div
                              key={art.id}
                              className="flex items-center justify-between gap-3 px-3 py-2 rounded"
                              style={{ background: 'var(--color-pit)' }}
                            >
                              <div className="flex items-center gap-2 min-w-0">
                                <span style={{ color: 'var(--color-ember)' }}>
                                  <FileIcon isTf isMd={false} />
                                </span>
                                <span
                                  className="text-sm truncate"
                                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-bright)' }}
                                >
                                  {art.file_name}
                                </span>
                              </div>
                              <button
                                onClick={() => handleDownloadFile(art)}
                                disabled={downloading.has(art.id)}
                                className="btn btn-ghost btn-sm flex items-center gap-1.5"
                                style={{ flexShrink: 0 }}
                              >
                                {downloading.has(art.id) ? (
                                  <span className="spinner" style={{ width: 12, height: 12 }} />
                                ) : (
                                  <DownloadIcon />
                                )}
                                <span className="text-xs">Download</span>
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : !loadingArtifacts && allFiles.length === 0 ? (
        <div className="empty-state">
          <p>No output files have been generated yet.</p>
        </div>
      ) : null}

      {/* ── 5. All Output Files Panel ── */}
      {allFiles.length > 0 && (
        <div className="panel overflow-hidden">
          <button
            onClick={() => setAllFilesOpen((prev) => !prev)}
            className="w-full flex items-center justify-between px-5 py-3.5 text-left"
            style={{
              background: 'var(--color-well)',
              border: 'none',
              cursor: 'pointer',
              borderBottom: allFilesOpen ? '1px solid var(--color-rule)' : 'none',
            }}
            aria-expanded={allFilesOpen}
            aria-controls="all-files-panel"
          >
            <span className="flex items-center gap-2">
              <span style={{ color: 'var(--color-text-dim)' }}>
                <ChevronIcon open={allFilesOpen} />
              </span>
              <span className="text-sm font-semibold" style={{ color: 'var(--color-text-bright)' }}>
                All Output Files
              </span>
              <span className="badge badge-neutral text-xs">{allFiles.length}</span>
            </span>
          </button>

          {allFilesOpen && (
            <div id="all-files-panel">
              <table
                className="w-full text-sm"
                style={{ borderCollapse: 'collapse' }}
              >
                <thead>
                  <tr style={{ background: 'var(--color-pit)' }}>
                    <th
                      className="text-left px-5 py-2 text-xs font-semibold uppercase tracking-widest"
                      style={{ color: 'var(--color-text-dim)', borderBottom: '1px solid var(--color-rule)' }}
                    >
                      File
                    </th>
                    <th
                      className="text-left px-5 py-2 text-xs font-semibold uppercase tracking-widest"
                      style={{ color: 'var(--color-text-dim)', borderBottom: '1px solid var(--color-rule)' }}
                    >
                      Type
                    </th>
                    <th
                      className="text-left px-5 py-2 text-xs font-semibold uppercase tracking-widest"
                      style={{ color: 'var(--color-text-dim)', borderBottom: '1px solid var(--color-rule)' }}
                    >
                      Created
                    </th>
                    <th
                      className="text-right px-5 py-2 text-xs font-semibold uppercase tracking-widest"
                      style={{ color: 'var(--color-text-dim)', borderBottom: '1px solid var(--color-rule)' }}
                    >
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {allFiles.map((art) => {
                    const tf = isTerraform(art);
                    const md = isMarkdown(art);
                    return (
                      <tr
                        key={art.id}
                        style={{ borderBottom: '1px solid var(--color-rule)' }}
                      >
                        <td className="px-5 py-2.5">
                          <div className="flex items-center gap-2">
                            <span style={{ color: tf ? 'var(--color-ember)' : '#2563eb' }}>
                              <FileIcon isTf={tf} isMd={md} />
                            </span>
                            <span
                              style={{
                                fontFamily: 'var(--font-mono)',
                                color: 'var(--color-text-bright)',
                                fontSize: '0.8125rem',
                              }}
                            >
                              {art.file_name}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-2.5">
                          <span
                            className={`badge ${tf ? 'badge-warning' : 'badge-info'}`}
                          >
                            {tf ? 'Terraform' : md ? 'Markdown' : art.content_type}
                          </span>
                        </td>
                        <td className="px-5 py-2.5 text-xs" style={{ color: 'var(--color-text-dim)' }}>
                          {formatDate(art.created_at)}
                        </td>
                        <td className="px-5 py-2.5 text-right">
                          <button
                            onClick={() => handleDownloadFile(art)}
                            disabled={downloading.has(art.id)}
                            className="btn btn-ghost btn-sm flex items-center gap-1.5 ml-auto"
                          >
                            {downloading.has(art.id) ? (
                              <span className="spinner" style={{ width: 12, height: 12 }} />
                            ) : (
                              <DownloadIcon />
                            )}
                            Download
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
