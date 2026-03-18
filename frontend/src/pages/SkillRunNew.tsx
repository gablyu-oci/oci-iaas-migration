import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useCreateSkillRun } from '../api/hooks/useSkillRuns';
import { useResources } from '../api/hooks/useResources';
import ResourceTable, { type Resource } from '../components/ResourceTable';

const SKILL_TYPES = [
  {
    value: 'cfn_terraform',
    label: 'CloudFormation to Terraform',
    description: 'Convert AWS CloudFormation templates to OCI Terraform',
  },
  {
    value: 'iam_translation',
    label: 'IAM Translation',
    description: 'Translate AWS IAM policies to OCI IAM policies',
  },
  {
    value: 'dependency_discovery',
    label: 'Dependency Discovery',
    description: 'Discover and map resource dependencies',
  },
];

export default function SkillRunNew() {
  const [searchParams] = useSearchParams();
  const preselectedResourceId = searchParams.get('resource_id') || '';

  const [skillType, setSkillType] = useState('cfn_terraform');
  const [inputMode, setInputMode] = useState<'resource' | 'content'>(
    preselectedResourceId ? 'resource' : 'content'
  );
  const [selectedResourceId, setSelectedResourceId] = useState(
    preselectedResourceId
  );
  const [inputContent, setInputContent] = useState('');
  const [maxIterations, setMaxIterations] = useState(3);

  const navigate = useNavigate();
  const createSkillRun = useCreateSkillRun();
  const { data: resources, isLoading: loadingResources } = useResources();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    const payload: {
      skill_type: string;
      input_content?: string;
      input_resource_id?: string;
      config?: Record<string, unknown>;
    } = {
      skill_type: skillType,
      config: { max_iterations: maxIterations },
    };

    if (inputMode === 'resource' && selectedResourceId) {
      payload.input_resource_id = selectedResourceId;
    } else if (inputMode === 'content' && inputContent.trim()) {
      payload.input_content = inputContent;
    }

    createSkillRun.mutate(payload, {
      onSuccess: (data: { id: string }) => {
        navigate(`/skill-runs/${data.id}`);
      },
    });
  };

  const handleResourceSelect = (resource: Resource) => {
    setSelectedResourceId(resource.id);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold">New Skill Run</h1>
        <p className="text-gray-600 mt-1">
          Configure and launch an AI-powered migration skill.
        </p>
      </div>

      {createSkillRun.isError && (
        <div className="p-3 bg-red-50 text-red-700 rounded-lg text-sm" role="alert">
          {(createSkillRun.error as any)?.response?.data?.detail ||
            'Failed to create skill run.'}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Skill Type */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Skill Type</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {SKILL_TYPES.map((st) => (
              <label
                key={st.value}
                className={`border-2 rounded-lg p-4 cursor-pointer transition-colors ${
                  skillType === st.value
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <input
                  type="radio"
                  name="skill_type"
                  value={st.value}
                  checked={skillType === st.value}
                  onChange={() => setSkillType(st.value)}
                  className="sr-only"
                />
                <p className="font-medium text-sm">{st.label}</p>
                <p className="text-xs text-gray-500 mt-1">{st.description}</p>
              </label>
            ))}
          </div>
        </div>

        {/* Input Source */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Input Source</h2>

          <div className="flex gap-4 mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="input_mode"
                value="resource"
                checked={inputMode === 'resource'}
                onChange={() => setInputMode('resource')}
                className="text-blue-600"
              />
              <span className="text-sm font-medium">
                Select from resources
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="input_mode"
                value="content"
                checked={inputMode === 'content'}
                onChange={() => setInputMode('content')}
                className="text-blue-600"
              />
              <span className="text-sm font-medium">Paste content</span>
            </label>
          </div>

          {inputMode === 'resource' && (
            <div>
              {loadingResources ? (
                <div className="animate-pulse space-y-3">
                  {[...Array(3)].map((_, i) => (
                    <div key={i} className="h-10 bg-gray-100 rounded" />
                  ))}
                </div>
              ) : resources && resources.length > 0 ? (
                <div className="max-h-80 overflow-auto border rounded-lg">
                  <ResourceTable
                    resources={resources}
                    onSelect={handleResourceSelect}
                    selectedId={selectedResourceId}
                  />
                </div>
              ) : (
                <p className="text-gray-500 text-sm">
                  No resources available. Upload or extract resources first.
                </p>
              )}
              {selectedResourceId && (
                <p className="mt-2 text-sm text-green-600">
                  Selected resource: {selectedResourceId}
                </p>
              )}
            </div>
          )}

          {inputMode === 'content' && (
            <div>
              <label
                htmlFor="input-content"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Paste YAML, JSON, or CloudFormation content
              </label>
              <textarea
                id="input-content"
                value={inputContent}
                onChange={(e) => setInputContent(e.target.value)}
                rows={12}
                placeholder="Paste your CloudFormation template, IAM policy, or resource configuration here..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
              />
            </div>
          )}
        </div>

        {/* Configuration */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Configuration</h2>
          <div>
            <label
              htmlFor="max-iterations"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Max Iterations: {maxIterations}
            </label>
            <input
              id="max-iterations"
              type="range"
              min={1}
              max={5}
              value={maxIterations}
              onChange={(e) => setMaxIterations(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>1 (Fast)</span>
              <span>3 (Balanced)</span>
              <span>5 (Thorough)</span>
            </div>
          </div>
        </div>

        {/* Submit */}
        <div className="flex gap-4">
          <button
            type="submit"
            disabled={
              createSkillRun.isPending ||
              (inputMode === 'resource' && !selectedResourceId) ||
              (inputMode === 'content' && !inputContent.trim())
            }
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {createSkillRun.isPending ? 'Launching...' : 'Launch Skill Run'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-6 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
