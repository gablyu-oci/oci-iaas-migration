import { useEffect, useState } from 'react';
import {
  useModelSettings, useUpdateModelSettings, type ModelInfo,
  useCredentials, useUpdateCredentials, useTestCredentials,
} from '../api/hooks/useSettings';

type SettingsSection = 'credentials' | 'models' | 'account' | 'notifications';

const NAV_ITEMS: { id: SettingsSection; label: string; icon: JSX.Element }[] = [
  {
    id: 'credentials',
    label: 'LLM Endpoint',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
      </svg>
    ),
  },
  {
    id: 'models',
    label: 'LLM Models',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M12 3v3M12 18v3M3 12h3M18 12h3M5.64 5.64l2.12 2.12M16.24 16.24l2.12 2.12M5.64 18.36l2.12-2.12M16.24 7.76l2.12-2.12M12 7a5 5 0 100 10 5 5 0 000-10z" />
      </svg>
    ),
  },
  {
    id: 'account',
    label: 'Account',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    id: 'notifications',
    label: 'Notifications',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
      </svg>
    ),
  },
];

const FAMILY_LABEL: Record<string, string> = {
  openai: 'OpenAI',
  google: 'Google',
  xai: 'xAI',
  meta: 'Meta Llama',
};

function groupModelsByFamily(models: ModelInfo[]): Record<string, ModelInfo[]> {
  const grouped: Record<string, ModelInfo[]> = {};
  for (const m of models) {
    (grouped[m.family] ||= []).push(m);
  }
  return grouped;
}

function ModelSelect({
  value, onChange, models, label, hint,
}: {
  value: string;
  onChange: (v: string) => void;
  models: ModelInfo[];
  label: string;
  hint: string;
}) {
  const grouped = groupModelsByFamily(models);
  const families = Object.keys(grouped).sort();

  return (
    <label className="block">
      <span className="block text-xs font-semibold mb-1" style={{ color: 'var(--color-text-bright)' }}>
        {label}
      </span>
      <span className="block text-xs mb-2" style={{ color: 'var(--color-text-dim)' }}>{hint}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg px-3 py-2 text-sm"
        style={{
          background: 'var(--color-well)',
          border: '1px solid var(--color-rule)',
          color: 'var(--color-text-bright)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        {families.map((fam) => (
          <optgroup key={fam} label={FAMILY_LABEL[fam] ?? fam}>
            {grouped[fam].map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}{m.reasoning ? ' — reasoning' : ''}  ·  {m.id}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

function CredentialsSection() {
  const { data, isLoading } = useCredentials();
  const update = useUpdateCredentials();
  const test = useTestCredentials();

  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (data) {
      setBaseUrl(data.base_url);
      setApiKey(''); // blank = keep existing
    }
  }, [data]);

  if (isLoading || !data) {
    return <div className="skel rounded-xl" style={{ height: '240px' }} />;
  }

  const dirty =
    apiKey.trim().length > 0 ||
    baseUrl !== data.base_url;

  const inputStyle = {
    background: 'var(--color-well)',
    border: '1px solid var(--color-rule)',
    color: 'var(--color-text-bright)',
    fontFamily: 'var(--font-mono)',
  } as const;

  const runTest = () => test.mutate(
    dirty ? { api_key: apiKey || undefined, base_url: baseUrl } : undefined,
  );

  const save = () => update.mutate({
    api_key: apiKey.trim() || undefined,
    base_url: baseUrl,
  }, {
    onSuccess: () => setApiKey(''),
  });

  return (
    <div className="space-y-4">
      <div
        className="rounded-xl p-5"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-rule)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text-bright)' }}>
          LLM endpoint
        </h3>
        <p className="text-xs mb-4" style={{ color: 'var(--color-text-dim)' }}>
          Any OpenAI-compatible chat-completions endpoint works — the Oracle internal Llama Stack gateway
          (anonymous, no key needed), OCI Generative AI, OpenAI, vLLM, etc. Stored in the
          backend's <code style={{ fontFamily: 'var(--font-mono)' }}>system_settings</code> table and applied
          in memory on save — the next LLM call picks up the change without a restart. The API key
          leaves the backend only masked.
        </p>

        <div className="grid grid-cols-1 gap-4 mb-4">
          {/* Base URL */}
          <label className="block">
            <span className="block text-xs font-semibold mb-1" style={{ color: 'var(--color-text-bright)' }}>
              Base URL
            </span>
            <span className="block text-xs mb-2" style={{ color: 'var(--color-text-dim)' }}>
              Include the API version path (e.g. <code style={{ fontFamily: 'var(--font-mono)' }}>/v1</code>).
              Examples: <code style={{ fontFamily: 'var(--font-mono)' }}>https://llama-stack.ai-apps-ord.oci-incubations.com/v1</code>,
              {' '}<code style={{ fontFamily: 'var(--font-mono)' }}>https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com/openai/v1</code>.
            </span>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://llama-stack.ai-apps-ord.oci-incubations.com/v1"
              className="w-full rounded-lg px-3 py-2 text-sm"
              style={inputStyle}
            />
          </label>

          {/* API Key (optional) */}
          <label className="block">
            <span className="block text-xs font-semibold mb-1" style={{ color: 'var(--color-text-bright)' }}>
              API key <span style={{ color: 'var(--color-text-dim)', fontWeight: 400 }}>(optional)</span>
            </span>
            <span className="block text-xs mb-2" style={{ color: 'var(--color-text-dim)' }}>
              {data.api_key_set
                ? <>Currently set: <code style={{ fontFamily: 'var(--font-mono)' }}>{data.api_key_masked}</code>. Leave blank to keep existing; paste a new one to rotate.</>
                : <>No key set — that's fine for anonymous endpoints like the Llama Stack gateway.</>}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={data.api_key_set ? '(leave blank to keep existing)' : 'optional — leave blank for anonymous endpoints'}
                autoComplete="off"
                className="flex-1 rounded-lg px-3 py-2 text-sm"
                style={inputStyle}
              />
              <button
                type="button"
                onClick={() => setShowKey((v) => !v)}
                className="btn btn-secondary"
                style={{ flexShrink: 0 }}
              >
                {showKey ? 'Hide' : 'Show'}
              </button>
            </div>
          </label>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={save}
            disabled={!dirty || update.isPending}
            className="btn btn-primary"
            style={{ opacity: (!dirty || update.isPending) ? 0.5 : 1 }}
          >
            {update.isPending ? 'Saving…' : dirty ? 'Save' : 'Saved'}
          </button>
          <button
            onClick={runTest}
            disabled={test.isPending}
            className="btn btn-secondary"
            style={{ opacity: test.isPending ? 0.5 : 1 }}
          >
            {test.isPending ? 'Testing…' : 'Test connection'}
          </button>

          {test.data && !test.isPending && (
            test.data.ok
              ? <span className="text-xs" style={{ color: 'var(--color-success, #4a9)' }}>
                  ✓ Connection OK — {test.data.model_tested} in {test.data.latency_ms}ms
                </span>
              : <span className="text-xs" style={{ color: 'var(--color-danger, #d33)' }}>
                  ✗ {test.data.error}
                </span>
          )}
          {update.isSuccess && !dirty && !test.data && (
            <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
              Saved — applies to the next LLM call.
            </span>
          )}
          {update.isError && (
            <span className="text-xs" style={{ color: 'var(--color-danger, #d33)' }}>
              {(update.error as Error)?.message ?? 'Failed to save.'}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}


function ModelsSection() {
  const { data, isLoading } = useModelSettings();
  const update = useUpdateModelSettings();

  const [writer, setWriter] = useState<string>('');
  const [reviewer, setReviewer] = useState<string>('');

  useEffect(() => {
    if (data) {
      setWriter(data.writer_model);
      setReviewer(data.reviewer_model);
    }
  }, [data]);

  if (isLoading || !data) {
    return <div className="skel rounded-xl" style={{ height: '280px' }} />;
  }

  const dirty = writer !== data.writer_model || reviewer !== data.reviewer_model;

  const save = () => update.mutate({
    writer_model: writer,
    reviewer_model: reviewer,
  });

  return (
    <div className="space-y-4">
      <div
        className="rounded-xl p-5"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-rule)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text-bright)' }}>
          Model selection
        </h3>
        <p className="text-xs mb-4" style={{ color: 'var(--color-text-dim)' }}>
          Only models verified to respond on the configured endpoint are shown.
          Changes apply to every skill — the Writer model handles enhancement / fix / runbook
          generation; the Reviewer model handles review / 6R classification / grouping.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <ModelSelect
            label="Writer model"
            hint="Enhancement, fix, runbook, resource generation — prefers a capable model."
            value={writer}
            onChange={setWriter}
            models={data.available}
          />
          <ModelSelect
            label="Reviewer model"
            hint="Review, 6R classification, grouping refinement — smaller/faster is fine."
            value={reviewer}
            onChange={setReviewer}
            models={data.available}
          />
        </div>

        <div
          className="rounded-lg p-3 mb-4"
          style={{ background: 'var(--color-well)', border: '1px dashed var(--color-fence)' }}
        >
          <div className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
            <strong style={{ color: 'var(--color-text-bright)' }}>Runtime:</strong>{' '}
            all skills run through the agent runtime (<code style={{ fontFamily: 'var(--font-mono)' }}>openai-agents</code> SDK)
            with a bounded writer→reviewer loop. Max iterations is picked per job on the skill-run form.
            See <a href="https://github.com/gablyu-oci/oci-iaas-migration/blob/main/docs/agent-architecture.md" target="_blank" rel="noreferrer" style={{ color: 'var(--color-ember)' }}>docs/agent-architecture.md</a> for
            the tool registry + workflow reference.
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={!dirty || update.isPending}
            className="btn btn-primary"
            style={{ opacity: (!dirty || update.isPending) ? 0.5 : 1 }}
          >
            {update.isPending ? 'Saving…' : dirty ? 'Save' : 'Saved'}
          </button>
          {update.isSuccess && !dirty && (
            <span className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
              Updated — next LLM call uses the new models.
            </span>
          )}
          {update.isError && (
            <span className="text-xs" style={{ color: 'var(--color-danger, #d33)' }}>
              {(update.error as Error)?.message ?? 'Failed to save.'}
            </span>
          )}
        </div>
      </div>

      <div
        className="rounded-xl p-4"
        style={{
          background: 'var(--color-well)',
          border: '1px dashed var(--color-fence)',
        }}
      >
        <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
          <strong style={{ color: 'var(--color-text-bright)' }}>{data.available.length}</strong> models
          reachable on the current endpoint. Reasoning models (GPT-5.x, o-series, Grok *-reasoning)
          are labeled and routed through the right token field automatically.
        </p>
      </div>
    </div>
  );
}

function AccountSection() {
  return (
    <div className="space-y-4">
      <div className="rounded-xl p-5"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-bright)' }}>Account Settings</h3>
        <div className="rounded-lg p-4 text-center"
          style={{ background: 'var(--color-well)', border: '1px dashed var(--color-fence)' }}>
          <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
            Account settings will be available in a future release.
          </p>
        </div>
      </div>
    </div>
  );
}

function NotificationsSection() {
  return (
    <div className="space-y-4">
      <div className="rounded-xl p-5"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-bright)' }}>Notification Preferences</h3>
        <div className="rounded-lg p-4 text-center"
          style={{ background: 'var(--color-well)', border: '1px dashed var(--color-fence)' }}>
          <p className="text-xs" style={{ color: 'var(--color-text-dim)' }}>
            Notification settings will be available in a future release.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function Settings() {
  const [activeSection, setActiveSection] = useState<SettingsSection>('credentials');

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h1 className="page-title" style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem' }}>Settings</h1>
        <p className="page-subtitle">Configure platform preferences</p>
      </div>

      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>
        <aside style={{ width: '220px', flexShrink: 0, position: 'sticky', top: '1.5rem' }}>
          <nav className="rounded-xl overflow-hidden"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-rule)', boxShadow: 'var(--shadow-card)' }}>
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--color-rule)' }}>
              <p className="text-xs font-semibold" style={{ color: 'var(--color-text-dim)' }}>Configuration</p>
            </div>
            <div className="p-2">
              {NAV_ITEMS.map((item) => {
                const isActive = activeSection === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setActiveSection(item.id)}
                    className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors"
                    style={{
                      background: isActive ? 'var(--color-ember-dim)' : 'transparent',
                      color: isActive ? 'var(--color-ember)' : 'var(--color-text-dim)',
                      border: 'none', cursor: 'pointer',
                      fontFamily: 'var(--font-sans)',
                      fontSize: '0.8125rem',
                      fontWeight: isActive ? 600 : 400,
                      marginBottom: '1px',
                    }}
                    onMouseEnter={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'var(--color-well)'; }}
                    onMouseLeave={(e) => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
                  >
                    <span style={{ opacity: isActive ? 1 : 0.7 }}>{item.icon}</span>
                    {item.label}
                  </button>
                );
              })}
            </div>
          </nav>
        </aside>

        <main className="flex-1 min-w-0">
          {activeSection === 'credentials' && <CredentialsSection />}
          {activeSection === 'models' && <ModelsSection />}
          {activeSection === 'account' && <AccountSection />}
          {activeSection === 'notifications' && <NotificationsSection />}
        </main>
      </div>
    </div>
  );
}
