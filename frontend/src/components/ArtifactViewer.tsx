import { useState } from 'react';
import {
  useSkillRunArtifacts,
  getArtifactDownloadUrl,
} from '../api/hooks/useSkillRuns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import client from '../api/client';

interface Props {
  skillRunId: string;
}

export default function ArtifactViewer({ skillRunId }: Props) {
  const { data: artifacts, isLoading } = useSkillRunArtifacts(skillRunId);
  const [previewContent, setPreviewContent] = useState<Record<string, string>>(
    {}
  );
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadPreview = async (artifactId: string) => {
    if (previewContent[artifactId]) {
      setExpandedId(expandedId === artifactId ? null : artifactId);
      return;
    }
    try {
      const resp = await client.get(
        `/api/artifacts/${artifactId}/download`,
        { responseType: 'text' }
      );
      setPreviewContent((prev) => ({ ...prev, [artifactId]: resp.data }));
      setExpandedId(artifactId);
    } catch {
      // ignore preview errors
    }
  };

  const typeColors: Record<string, string> = {
    terraform_tf: 'bg-purple-100 text-purple-800',
    dependency_json: 'bg-blue-100 text-blue-800',
    dependency_graph_mmd: 'bg-cyan-100 text-cyan-800',
    dependency_graph_dot: 'bg-teal-100 text-teal-800',
    run_report_md: 'bg-green-100 text-green-800',
    terraform_json: 'bg-yellow-100 text-yellow-800',
    other: 'bg-gray-100 text-gray-800',
  };

  if (isLoading)
    return <div className="animate-pulse h-20 bg-gray-100 rounded" />;
  if (!artifacts?.length)
    return <p className="text-gray-500">No artifacts available.</p>;

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold">
        Artifacts ({artifacts.length})
      </h3>
      {artifacts.map((a) => (
        <div key={a.id} className="border rounded-lg overflow-hidden">
          <div className="flex items-center justify-between p-3 bg-gray-50">
            <div className="flex items-center gap-3">
              <span
                className={`px-2 py-0.5 rounded text-xs font-medium ${typeColors[a.file_type] || typeColors.other}`}
              >
                {a.file_type}
              </span>
              <span className="font-mono text-sm">{a.file_name}</span>
            </div>
            <div className="flex gap-2">
              {(a.content_type.startsWith('text/') ||
                a.content_type === 'application/json') && (
                <button
                  onClick={() => loadPreview(a.id)}
                  className="text-sm text-blue-600 hover:text-blue-800"
                >
                  {expandedId === a.id ? 'Hide' : 'Preview'}
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
          {expandedId === a.id && previewContent[a.id] && (
            <div className="p-4 border-t max-h-96 overflow-auto">
              {a.file_name.endsWith('.md') ? (
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {previewContent[a.id]}
                  </ReactMarkdown>
                </div>
              ) : (
                <pre className="text-xs font-mono whitespace-pre-wrap bg-gray-900 text-gray-100 p-4 rounded">
                  {previewContent[a.id]}
                </pre>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
