import { useState } from 'react';

type SettingsSection = 'account' | 'notifications';

const NAV_ITEMS: { id: SettingsSection; label: string; icon: JSX.Element }[] = [
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
  const [activeSection, setActiveSection] = useState<SettingsSection>('account');

  return (
    <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h1 className="page-title" style={{ fontFamily: 'var(--font-display)', fontSize: '1.75rem' }}>Settings</h1>
        <p className="page-subtitle">Configure platform preferences</p>
      </div>

      <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-start' }}>
        <aside style={{ width: '200px', flexShrink: 0, position: 'sticky', top: '1.5rem' }}>
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
          {activeSection === 'account' && <AccountSection />}
          {activeSection === 'notifications' && <NotificationsSection />}
        </main>
      </div>
    </div>
  );
}
