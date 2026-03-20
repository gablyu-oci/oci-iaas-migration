import { useState, useRef, type FormEvent, type DragEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useCreateTranslationJob } from '../api/hooks/useTranslationJobs';
import { useResources } from '../api/hooks/useResources';
import ResourceTable, { type Resource } from '../components/ResourceTable';

const SKILL_TYPES = [
  { value: 'cfn_terraform', label: 'CFN → Terraform', description: 'Convert CloudFormation to OCI Terraform HCL', accept: '.yaml,.yml,.json', hint: 'YAML or JSON CloudFormation template' },
  { value: 'iam_translation', label: 'IAM Translation', description: 'Translate AWS IAM policies to OCI IAM', accept: '.json', hint: 'JSON IAM policy document' },
  { value: 'dependency_discovery', label: 'Dependency Discovery', description: 'Discover resource dependencies from CloudTrail', accept: '.json,.csv,.log', hint: 'CloudTrail JSON or VPC Flow Log' },
  { value: 'network_translation', label: 'Network Translation', description: 'VPC, Subnets, SGs → OCI VCN', accept: '.json,.yaml,.yml,.tf', hint: 'VPC/Subnet/SG config' },
  { value: 'ec2_translation', label: 'EC2 Translation', description: 'EC2 / ASGs → OCI Compute', accept: '.json,.yaml,.yml,.tf', hint: 'EC2 or ASG config' },
  { value: 'database_translation', label: 'Database Translation', description: 'RDS → OCI Database System', accept: '.json,.yaml,.yml,.tf', hint: 'RDS instance config' },
  { value: 'loadbalancer_translation', label: 'Load Balancer', description: 'ALB / NLB → OCI Load Balancer', accept: '.json,.yaml,.yml,.tf', hint: 'ALB or NLB config' },
];

export default function TranslationJobNew() {
  const [searchParams] = useSearchParams();
  const preselectedResourceId = searchParams.get('resource_id') || '';

  const [skillType, setSkillType] = useState('cfn_terraform');
  const [inputMode, setInputMode] = useState<'resource' | 'file'>(preselectedResourceId ? 'resource' : 'file');
  const [selectedResourceId, setSelectedResourceId] = useState(preselectedResourceId);
  const [inputContent, setInputContent] = useState('');
  const [pastedContent, setPastedContent] = useState('');
  const [fileName, setFileName] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [fileError, setFileError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [maxIterations, setMaxIterations] = useState(3);

  const currentSkill = SKILL_TYPES.find((s) => s.value === skillType)!;
  const navigate = useNavigate();
  const createSkillRun = useCreateTranslationJob();
  const { data: resources, isLoading: loadingResources } = useResources();

  const loadFile = (file: File) => {
    setFileError('');
    if (file.size > 5 * 1024 * 1024) { setFileError('File is too large. Maximum size is 5 MB.'); return; }
    const reader = new FileReader();
    reader.onload = (e) => {
      setInputContent(e.target?.result as string);
      setPastedContent('');
      setFileName(file.name);
    };
    reader.onerror = () => setFileError('Failed to read file.');
    reader.readAsText(file);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) loadFile(file);
  };

  const handlePasteChange = (value: string) => {
    setPastedContent(value);
    if (value.trim()) { setInputContent(value); setFileName(''); }
    else if (!fileName) setInputContent('');
  };

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
      onSuccess: (data: { id: string }) => navigate(`/translation-jobs/${data.id}`),
    });
  };

  return (
    <div className="space-y-6 max-w-4xl animate-fade-in">
      <div>
        <button
          onClick={() => navigate(-1)}
          className="back-link"
          style={{ background: 'none', border: 'none', cursor: 'pointer' }}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </button>
        <h1 className="page-title">New Translation Job</h1>
        <p className="page-subtitle">Configure and launch an AI-powered migration translation job.</p>
      </div>

      {createSkillRun.isError && (
        <div className="alert alert-error" role="alert">
          {(createSkillRun.error as any)?.response?.data?.detail || 'Failed to create translation job.'}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Skill Type */}
        <div className="panel">
          <div className="panel-header">
            <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Skill Type</h2>
          </div>
          <div className="panel-body">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {SKILL_TYPES.map((st) => (
                <label
                  key={st.value}
                  className="rounded-lg p-3 cursor-pointer transition-colors"
                  style={{
                    background: skillType === st.value ? 'rgba(249,115,22,0.08)' : 'var(--color-well)',
                    border: `1px solid ${skillType === st.value ? 'rgba(249,115,22,0.35)' : 'var(--color-fence)'}`,
                  }}
                >
                  <input
                    type="radio"
                    name="skill_type"
                    value={st.value}
                    checked={skillType === st.value}
                    onChange={() => setSkillType(st.value)}
                    className="sr-only"
                  />
                  <p className="text-xs font-semibold" style={{ color: skillType === st.value ? 'var(--color-ember)' : '#0f172a' }}>
                    {st.label}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: '#64748b' }}>{st.description}</p>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Input Source */}
        <div className="panel">
          <div className="panel-header">
            <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Input Source</h2>
          </div>
          <div className="panel-body space-y-4">
            <div className="flex gap-5">
              {(['resource', 'file'] as const).map((mode) => (
                <label key={mode} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="input_mode"
                    value={mode}
                    checked={inputMode === mode}
                    onChange={() => setInputMode(mode)}
                    style={{ accentColor: 'var(--color-ember)' }}
                  />
                  <span className="text-sm" style={{ color: '#475569' }}>
                    {mode === 'resource' ? 'Select from resources' : 'Upload file or paste text'}
                  </span>
                </label>
              ))}
            </div>

            {inputMode === 'resource' && (
              <div>
                {loadingResources ? (
                  <div className="space-y-2">
                    {[...Array(3)].map((_, i) => <div key={i} className="skel h-10" />)}
                  </div>
                ) : resources && resources.length > 0 ? (
                  <div
                    className="rounded-lg overflow-auto"
                    style={{ maxHeight: '20rem', border: '1px solid var(--color-rule)' }}
                  >
                    <ResourceTable
                      resources={resources}
                      onSelect={(r: Resource) => setSelectedResourceId(r.id)}
                      selectedId={selectedResourceId}
                    />
                  </div>
                ) : (
                  <p className="text-sm" style={{ color: '#64748b' }}>
                    No resources available. Extract or upload resources first.
                  </p>
                )}
                {selectedResourceId && (
                  <p className="mt-2 text-xs" style={{ color: '#16a34a' }}>
                    ✓ Resource selected: <span style={{ fontFamily: 'var(--font-mono)' }}>{selectedResourceId}</span>
                  </p>
                )}
              </div>
            )}

            {inputMode === 'file' && (
              <div className="space-y-4">
                <div
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-lg p-8 text-center cursor-pointer transition-colors"
                  style={{
                    border: `2px dashed ${isDragging ? 'var(--color-ember)' : fileName ? 'rgba(74,222,128,0.4)' : 'var(--color-fence)'}`,
                    background: isDragging ? 'rgba(249,115,22,0.04)' : fileName ? 'rgba(74,222,128,0.04)' : 'var(--color-well)',
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={currentSkill.accept}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) loadFile(f); }}
                    className="hidden"
                  />
                  {fileName ? (
                    <div>
                      <p className="text-sm font-medium" style={{ color: '#16a34a' }}>✓ {fileName}</p>
                      <p className="text-xs mt-1" style={{ color: '#475569' }}>
                        {(inputContent.length / 1024).toFixed(1)} KB loaded · click to replace
                      </p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-sm" style={{ color: '#64748b' }}>Drop file here or click to browse</p>
                      <p className="text-xs mt-1" style={{ color: '#475569' }}>{currentSkill.hint}</p>
                    </div>
                  )}
                </div>

                {fileError && <p className="text-xs" style={{ color: '#dc2626' }}>{fileError}</p>}

                <div>
                  <div className="flex items-center gap-3 mb-3">
                    <div className="flex-1 h-px" style={{ background: 'var(--color-rule)' }} />
                    <span className="text-xs uppercase" style={{ color: '#475569' }}>Or paste content</span>
                    <div className="flex-1 h-px" style={{ background: 'var(--color-rule)' }} />
                  </div>
                  <textarea
                    value={pastedContent}
                    onChange={(e) => handlePasteChange(e.target.value)}
                    placeholder={`Paste your ${currentSkill.hint.toLowerCase()} here…`}
                    rows={6}
                    className="field-input"
                    style={{ fontFamily: 'var(--font-mono)', resize: 'vertical' }}
                  />
                  {pastedContent.trim() && (
                    <p className="mt-1 text-xs" style={{ color: '#16a34a' }}>
                      ✓ {(pastedContent.length / 1024).toFixed(1)} KB ready
                    </p>
                  )}
                </div>

                {inputContent && !pastedContent.trim() && (
                  <details className="text-sm">
                    <summary
                      className="cursor-pointer text-xs"
                      style={{ color: '#475569' }}
                    >
                      Preview content
                    </summary>
                    <pre
                      className="mt-2 p-3 rounded-lg overflow-auto text-xs"
                      style={{
                        background: 'var(--color-well)',
                        border: '1px solid var(--color-fence)',
                        color: '#64748b',
                        fontFamily: 'var(--font-mono)',
                        maxHeight: '12rem',
                      }}
                    >
                      {inputContent.slice(0, 2000)}
                      {inputContent.length > 2000 && '\n… (truncated for preview)'}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Configuration */}
        <div className="panel">
          <div className="panel-header">
            <h2 className="text-sm font-semibold" style={{ color: '#0f172a' }}>Configuration</h2>
          </div>
          <div className="panel-body">
            <label htmlFor="max-iterations" className="field-label">
              Max Iterations: <span style={{ color: 'var(--color-ember)' }}>{maxIterations}</span>
            </label>
            <input
              id="max-iterations"
              type="range"
              min={1}
              max={5}
              value={maxIterations}
              onChange={(e) => setMaxIterations(Number(e.target.value))}
              className="w-full mt-2"
              style={{ accentColor: 'var(--color-ember)' }}
            />
            <div className="flex justify-between text-xs mt-1" style={{ color: '#475569' }}>
              <span>1 — Fast</span>
              <span>3 — Balanced</span>
              <span>5 — Thorough</span>
            </div>
          </div>
        </div>

        {/* Submit */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={
              createSkillRun.isPending ||
              (inputMode === 'resource' && !selectedResourceId) ||
              (inputMode === 'file' && !inputContent.trim())
            }
            className="btn btn-primary btn-lg"
          >
            {createSkillRun.isPending ? <><span className="spinner" />Launching…</> : 'Launch Translation Job'}
          </button>
          <button type="button" onClick={() => navigate(-1)} className="btn btn-secondary btn-lg">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
