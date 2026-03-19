import { useState, useRef, type FormEvent, type DragEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useCreateTranslationJob } from '../api/hooks/useTranslationJobs';
import { useResources } from '../api/hooks/useResources';
import ResourceTable, { type Resource } from '../components/ResourceTable';

const SKILL_TYPES = [
  {
    value: 'cfn_terraform',
    label: 'CloudFormation to Terraform',
    description: 'Convert AWS CloudFormation templates to OCI Terraform HCL',
    accept: '.yaml,.yml,.json',
    hint: 'YAML or JSON CloudFormation template',
  },
  {
    value: 'iam_translation',
    label: 'IAM Translation',
    description: 'Translate AWS IAM policies to OCI IAM policies',
    accept: '.json',
    hint: 'JSON IAM policy document',
  },
  {
    value: 'dependency_discovery',
    label: 'Dependency Discovery',
    description: 'Discover and map resource dependencies from CloudTrail',
    accept: '.json,.csv,.log',
    hint: 'CloudTrail JSON or VPC Flow Log',
  },
  {
    value: 'network_translation',
    label: 'Network Translation',
    description: 'Translate VPC, Subnets, and Security Groups to OCI VCN',
    accept: '.json,.yaml,.yml,.tf',
    hint: 'VPC/Subnet/SG configuration (JSON, YAML, or Terraform)',
  },
  {
    value: 'ec2_translation',
    label: 'EC2 Translation',
    description: 'Translate EC2 instances and ASGs to OCI Compute',
    accept: '.json,.yaml,.yml,.tf',
    hint: 'EC2 instance or ASG configuration',
  },
  {
    value: 'database_translation',
    label: 'Database Translation',
    description: 'Translate RDS instances to OCI Database System',
    accept: '.json,.yaml,.yml,.tf',
    hint: 'RDS instance configuration',
  },
  {
    value: 'loadbalancer_translation',
    label: 'Load Balancer Translation',
    description: 'Translate ALB/NLB to OCI Load Balancer',
    accept: '.json,.yaml,.yml,.tf',
    hint: 'ALB or NLB configuration',
  },
];

export default function TranslationJobNew() {
  const [searchParams] = useSearchParams();
  const preselectedResourceId = searchParams.get('resource_id') || '';

  const [skillType, setSkillType] = useState('cfn_terraform');
  const [inputMode, setInputMode] = useState<'resource' | 'file'>(
    preselectedResourceId ? 'resource' : 'file'
  );
  const [selectedResourceId, setSelectedResourceId] = useState(
    preselectedResourceId
  );
  const [inputContent, setInputContent] = useState('');
  const [pastedContent, setPastedContent] = useState('');
  const [fileName, setFileName] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [fileError, setFileError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [maxIterations, setMaxIterations] = useState(3);

  const currentSkill = SKILL_TYPES.find((s) => s.value === skillType)!;

  const loadFile = (file: File) => {
    setFileError('');
    if (file.size > 5 * 1024 * 1024) {
      setFileError('File is too large. Maximum size is 5 MB.');
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      setInputContent(e.target?.result as string);
      setPastedContent('');
      setFileName(file.name);
    };
    reader.onerror = () => setFileError('Failed to read file.');
    reader.readAsText(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) loadFile(file);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) loadFile(file);
  };

  const handlePasteChange = (value: string) => {
    setPastedContent(value);
    if (value.trim()) {
      setInputContent(value);
      setFileName('');
    } else if (!fileName) {
      setInputContent('');
    }
  };

  const navigate = useNavigate();
  const createSkillRun = useCreateTranslationJob();
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
    } else if (inputMode === 'file' && inputContent.trim()) {
      payload.input_content = inputContent;
    }

    createSkillRun.mutate(payload, {
      onSuccess: (data: { id: string }) => {
        navigate(`/translation-jobs/${data.id}`);
      },
    });
  };

  const handleResourceSelect = (resource: Resource) => {
    setSelectedResourceId(resource.id);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center text-sm text-gray-500 hover:text-gray-700 mb-2"
        >
          ← Back
        </button>
        <h1 className="text-2xl font-bold">New Translation Job</h1>
        <p className="text-gray-600 mt-1">
          Configure and launch an AI-powered migration translation job.
        </p>
      </div>

      {createSkillRun.isError && (
        <div className="p-3 bg-red-50 text-red-700 rounded-lg text-sm" role="alert">
          {(createSkillRun.error as any)?.response?.data?.detail ||
            'Failed to create translation job.'}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Skill Type */}
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Skill Type</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
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
              <span className="text-sm font-medium">Select from resources</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="input_mode"
                value="file"
                checked={inputMode === 'file'}
                onChange={() => setInputMode('file')}
                className="text-blue-600"
              />
              <span className="text-sm font-medium">Upload file or paste text</span>
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

          {inputMode === 'file' && (
            <div className="space-y-4">
              {/* Drop zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  isDragging
                    ? 'border-blue-500 bg-blue-50'
                    : fileName
                    ? 'border-green-400 bg-green-50'
                    : 'border-gray-300 hover:border-gray-400 bg-gray-50'
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={currentSkill.accept}
                  onChange={handleFileChange}
                  className="hidden"
                />
                {fileName ? (
                  <div className="space-y-1">
                    <p className="text-green-700 font-medium">&#10003; {fileName}</p>
                    <p className="text-xs text-gray-500">
                      {(inputContent.length / 1024).toFixed(1)} KB loaded -- click to replace
                    </p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="text-gray-600 font-medium">
                      Drop file here or click to browse
                    </p>
                    <p className="text-xs text-gray-400">{currentSkill.hint}</p>
                  </div>
                )}
              </div>

              {fileError && (
                <p className="text-sm text-red-600">{fileError}</p>
              )}

              {/* Or paste content */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <div className="flex-1 h-px bg-gray-200" />
                  <span className="text-xs text-gray-400 font-medium uppercase">Or paste content</span>
                  <div className="flex-1 h-px bg-gray-200" />
                </div>
                <textarea
                  value={pastedContent}
                  onChange={(e) => handlePasteChange(e.target.value)}
                  placeholder={`Paste your ${currentSkill.hint.toLowerCase()} here...`}
                  rows={6}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-y"
                />
                {pastedContent.trim() && (
                  <p className="mt-1 text-xs text-green-600">
                    {(pastedContent.length / 1024).toFixed(1)} KB of pasted content ready
                  </p>
                )}
              </div>

              {/* Preview */}
              {inputContent && !pastedContent.trim() && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
                    Preview content
                  </summary>
                  <pre className="mt-2 p-3 bg-gray-50 border rounded-lg overflow-auto max-h-48 text-xs font-mono text-gray-700">
                    {inputContent.slice(0, 2000)}
                    {inputContent.length > 2000 && '\n... (truncated for preview)'}
                  </pre>
                </details>
              )}
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
              (inputMode === 'file' && !inputContent.trim())
            }
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {createSkillRun.isPending ? 'Launching...' : 'Launch Translation Job'}
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
