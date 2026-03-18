import { useState } from 'react';
import {
  useSkillRunArtifacts,
  getArtifactDownloadUrl,
} from '../api/hooks/useSkillRuns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github.css';
import 'github-markdown-css/github-markdown-light.css';
import client from '../api/client';

interface Props {
  skillRunId: string;
}

const typeColors: Record<string, string> = {
  terraform_tf: 'bg-purple-100 text-purple-800',
  dependency_json: 'bg-blue-100 text-blue-800',
  dependency_graph_mmd: 'bg-cyan-100 text-cyan-800',
  dependency_graph_dot: 'bg-teal-100 text-teal-800',
  run_report_md: 'bg-green-100 text-green-800',
  translation_log_md: 'bg-indigo-100 text-indigo-800',
  oci_policies_txt: 'bg-orange-100 text-orange-800',
  terraform_json: 'bg-yellow-100 text-yellow-800',
  other: 'bg-gray-100 text-gray-800',
};

export default function ArtifactViewer({ skillRunId }: Props) {
  const { data: artifacts, isLoading } = useSkillRunArtifacts(skillRunId);
  const [previewContent, setPreviewContent] = useState<Record<string, string>>({});
  const [modalId, setModalId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadAndOpen = async (artifactId: string, modal: boolean) => {
    let content = previewContent[artifactId];
    if (!content) {
      try {
        const resp = await client.get(`/api/artifacts/${artifactId}/download`, {
          responseType: 'text',
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

  if (isLoading) return <div className="animate-pulse h-20 bg-gray-100 rounded" />;
  if (!artifacts?.length) return <p className="text-gray-500">No artifacts available.</p>;

  const modalArtifact = modalId ? artifacts.find((a) => a.id === modalId) : null;

  return (
    <>
      <div className="space-y-3">
        <h3 className="text-lg font-semibold">Artifacts ({artifacts.length})</h3>
        {artifacts.map((a) => {
          const isMarkdown = a.file_name.endsWith('.md');
          const isText =
            a.content_type.startsWith('text/') || a.content_type === 'application/json';

          return (
            <div key={a.id} className="border rounded-lg overflow-hidden">
              <div className="flex items-center justify-between p-3 bg-gray-50">
                <div className="flex items-center gap-3">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${typeColors[a.file_type] ?? typeColors.other}`}
                  >
                    {a.file_type}
                  </span>
                  <span className="font-mono text-sm">{a.file_name}</span>
                </div>
                <div className="flex gap-3 items-center">
                  {isMarkdown && (
                    <button
                      onClick={() => loadAndOpen(a.id, true)}
                      className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                    >
                      Preview
                    </button>
                  )}
                  {isText && !isMarkdown && (
                    <button
                      onClick={() => loadAndOpen(a.id, false)}
                      className="text-sm text-blue-600 hover:text-blue-800"
                    >
                      {expandedId === a.id ? 'Hide' : 'View'}
                    </button>
                  )}
                  <a
                    href={getArtifactDownloadUrl(a.id)}
                    className="text-sm text-gray-600 hover:text-gray-800"
                    download
                  >
                    Download
                  </a>
                </div>
              </div>

              {/* Inline preview for non-markdown text */}
              {expandedId === a.id && previewContent[a.id] && (
                <div className="border-t max-h-96 overflow-auto">
                  <pre className="text-xs font-mono whitespace-pre-wrap bg-gray-950 text-gray-100 p-4">
                    {previewContent[a.id]}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Markdown modal */}
      {modalId && modalArtifact && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 overflow-y-auto py-8 px-4"
          onClick={(e) => e.target === e.currentTarget && setModalId(null)}
        >
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white rounded-t-xl z-10">
              <div className="flex items-center gap-3">
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium ${typeColors[modalArtifact.file_type] ?? typeColors.other}`}
                >
                  {modalArtifact.file_type}
                </span>
                <span className="font-mono text-sm font-medium">{modalArtifact.file_name}</span>
              </div>
              <div className="flex items-center gap-3">
                <a
                  href={getArtifactDownloadUrl(modalArtifact.id)}
                  className="text-sm text-gray-600 hover:text-gray-800"
                  download
                >
                  Download
                </a>
                <button
                  onClick={() => setModalId(null)}
                  className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-500 hover:text-gray-700 text-lg"
                >
                  ×
                </button>
              </div>
            </div>

            {/* Markdown body */}
            <div className="px-8 py-6 overflow-auto">
              <div className="markdown-body">
                {previewContent[modalId] ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeHighlight]}
                  >
                    {previewContent[modalId]}
                  </ReactMarkdown>
                ) : (
                  <div className="text-center py-12 text-gray-400">Loading…</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
