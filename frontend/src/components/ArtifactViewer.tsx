import { useState } from 'react';
import {
  useTranslationJobArtifacts,
  getArtifactDownloadUrl,
  downloadArtifactsAsZip,
} from '../api/hooks/useTranslationJobs';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github.css';
import client from '../api/client';

interface Props {
  skillRunId: string;
}

const TYPE_BADGE: Record<string, string> = {
  terraform_tf:          'badge badge-accent',
  dependency_json:       'badge badge-info',
  dependency_graph_mmd:  'badge badge-info',
  dependency_graph_dot:  'badge badge-info',
  run_report_md:         'badge badge-success',
  translation_log_md:    'badge badge-warning',
  oci_policies_txt:      'badge badge-warning',
  terraform_json:        'badge badge-neutral',
  other:                 'badge badge-neutral',
};

export default function ArtifactViewer({ skillRunId }: Props) {
  const { data: artifacts, isLoading } = useTranslationJobArtifacts(skillRunId);
  const [previewContent, setPreviewContent] = useState<Record<string, string>>({});
  const [modalId, setModalId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [zipping, setZipping] = useState(false);

  const loadAndOpen = async (artifactId: string, modal: boolean) => {
    let content = previewContent[artifactId];
    if (!content) {
      try {
        const token = localStorage.getItem('token');
        const resp = await client.get(`/api/artifacts/${artifactId}/download`, {
          responseType: 'text',
          params: { token },
        });
        content = resp.data;
        setPreviewContent((prev) => ({ ...prev, [artifactId]: content }));
      } catch {
        return;
      }
    }
    if (modal) {
      setModalId(artifactId);
    } else {
      setExpandedId(expandedId === artifactId ? null : artifactId);
    }
  };

  const toggle = (id: string) =>
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const handleZip = async () => {
    if (selected.size === 0) return;
    setZipping(true);
    try { await downloadArtifactsAsZip([...selected]); }
    finally { setZipping(false); }
  };

  if (isLoading) return <div className="skel h-20" />;
  if (!artifacts?.length) return (
    <div className="empty-state"><p>No artifacts available.</p></div>
  );

  const allSelected = selected.size === artifacts.length;
  const modalArtifact = modalId ? artifacts.find((a) => a.id === modalId) : null;

  return (
    <>
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <p className="field-label mb-0">
          Artifacts <span className="tab-count">{artifacts.length}</span>
        </p>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-ghost btn-sm text-xs"
            onClick={() => setSelected(allSelected ? new Set() : new Set(artifacts.map(a => a.id)))}
          >
            {allSelected ? 'Deselect all' : 'Select all'}
          </button>
          <button
            className="btn btn-secondary btn-sm"
            disabled={selected.size === 0 || zipping}
            onClick={handleZip}
          >
            {zipping
              ? <><span className="spinner" style={{ width: 12, height: 12 }} /> Zipping…</>
              : selected.size > 0
                ? `Download ZIP (${selected.size})`
                : 'Download ZIP'}
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {artifacts.map((a) => {
          const isMarkdown = a.file_name.endsWith('.md');
          const isText =
            a.content_type.startsWith('text/') || a.content_type === 'application/json';
          const isSelected = selected.has(a.id);

          return (
            <div
              key={a.id}
              className="rounded-lg overflow-hidden"
              style={{
                border: `1px solid ${isSelected ? 'rgba(249,115,22,0.35)' : 'var(--color-fence)'}`,
                transition: 'border-color 0.15s',
              }}
            >
              <div
                className="flex items-center justify-between p-3"
                style={{ background: isSelected ? 'rgba(249,115,22,0.06)' : 'var(--color-well)' }}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <input
                    type="checkbox"
                    className="cb"
                    checked={isSelected}
                    onChange={() => toggle(a.id)}
                  />
                  <span className={TYPE_BADGE[a.file_type] ?? TYPE_BADGE.other}>
                    {a.file_type}
                  </span>
                  <span
                    className="text-xs truncate"
                    style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}
                  >
                    {a.file_name}
                  </span>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0 ml-3">
                  {isMarkdown && (
                    <button
                      onClick={() => loadAndOpen(a.id, true)}
                      className="btn btn-ghost btn-sm"
                    >
                      Preview
                    </button>
                  )}
                  {isText && !isMarkdown && (
                    <button
                      onClick={() => loadAndOpen(a.id, false)}
                      className="btn btn-ghost btn-sm"
                    >
                      {expandedId === a.id ? 'Hide' : 'View'}
                    </button>
                  )}
                  <a
                    href={getArtifactDownloadUrl(a.id)}
                    className="btn btn-secondary btn-sm"
                    download
                  >
                    Download
                  </a>
                </div>
              </div>

              {/* Inline preview for non-markdown text */}
              {expandedId === a.id && previewContent[a.id] && (
                <div style={{ borderTop: '1px solid var(--color-fence)' }}>
                  <pre
                    className="text-xs overflow-auto p-4"
                    style={{
                      background: 'var(--color-pit)',
                      color: 'var(--color-text-dim)',
                      fontFamily: 'var(--font-mono)',
                      maxHeight: '24rem',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {previewContent[a.id]}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Markdown preview modal */}
      {modalId && modalArtifact && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Artifact Preview"
          onClick={(e) => e.target === e.currentTarget && setModalId(null)}
        >
          <div
            className="modal modal-lg"
            style={{ maxHeight: '88vh', display: 'flex', flexDirection: 'column' }}
          >
            <div className="modal-header">
              <div className="flex items-center gap-3 min-w-0">
                <span className={TYPE_BADGE[modalArtifact.file_type] ?? TYPE_BADGE.other}>
                  {modalArtifact.file_type}
                </span>
                <span
                  className="text-xs font-medium truncate"
                  style={{ color: 'var(--color-text-bright)', fontFamily: 'var(--font-mono)' }}
                >
                  {modalArtifact.file_name}
                </span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                <a
                  href={getArtifactDownloadUrl(modalArtifact.id)}
                  className="btn btn-secondary btn-sm"
                  download
                >
                  Download
                </a>
                <button
                  onClick={() => setModalId(null)}
                  className="btn btn-ghost btn-sm"
                  aria-label="Close"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div
              className="modal-body overflow-y-auto flex-1"
              style={{
                color: 'var(--color-text-bright)',
                fontSize: '0.875rem',
                lineHeight: '1.7',
              }}
            >
              {previewContent[modalId] ? (
                <div className="prose-dark">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                    components={{
                      h1: ({ children }) => <h1 style={{ color: 'var(--color-text-bright)', fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.75rem', marginTop: '1.5rem', paddingBottom: '0.5rem', borderBottom: '1px solid var(--color-fence)' }}>{children}</h1>,
                      h2: ({ children }) => <h2 style={{ color: 'var(--color-text-bright)', fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem', marginTop: '1.25rem' }}>{children}</h2>,
                      h3: ({ children }) => <h3 style={{ color: 'var(--color-text-bright)', fontSize: '0.95rem', fontWeight: 600, marginBottom: '0.4rem', marginTop: '1rem' }}>{children}</h3>,
                      p: ({ children }) => <p style={{ color: 'var(--color-text-dim)', marginBottom: '0.75rem' }}>{children}</p>,
                      li: ({ children }) => <li style={{ color: 'var(--color-text-dim)', marginBottom: '0.25rem' }}>{children}</li>,
                      code: ({ children, className }) =>
                        className ? (
                          <code className={className}>{children}</code>
                        ) : (
                          <code style={{ background: 'var(--color-well)', color: 'var(--color-ember)', padding: '0.1em 0.4em', borderRadius: '4px', fontSize: '0.85em', fontFamily: 'var(--font-mono)' }}>{children}</code>
                        ),
                      pre: ({ children }) => (
                        <pre style={{ background: 'var(--color-pit)', border: '1px solid var(--color-fence)', borderRadius: '8px', padding: '1rem', marginBottom: '1rem', overflowX: 'auto', fontSize: '0.8rem' }}>
                          {children}
                        </pre>
                      ),
                      blockquote: ({ children }) => (
                        <blockquote style={{ borderLeft: '3px solid var(--color-ember)', paddingLeft: '1rem', margin: '1rem 0', color: 'var(--color-text-dim)' }}>
                          {children}
                        </blockquote>
                      ),
                      table: ({ children }) => (
                        <div style={{ overflowX: 'auto', marginBottom: '1rem' }}>
                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>{children}</table>
                        </div>
                      ),
                      th: ({ children }) => <th style={{ padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--color-fence)', color: 'var(--color-text-dim)', textAlign: 'left', fontWeight: 600 }}>{children}</th>,
                      td: ({ children }) => <td style={{ padding: '0.5rem 0.75rem', borderBottom: '1px solid var(--color-rule)', color: 'var(--color-text-dim)' }}>{children}</td>,
                    }}
                  >
                    {previewContent[modalId]}
                  </ReactMarkdown>
                </div>
              ) : (
                <div className="flex items-center justify-center py-12">
                  <span className="spinner spinner-lg" />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
