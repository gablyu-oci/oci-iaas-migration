import { BrowserRouter, Routes, Route, Navigate, NavLink, Outlet, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
import Resources from './pages/Resources';
import TranslationJobNew from './pages/TranslationJobNew';
import TranslationJobList from './pages/TranslationJobList';
import TranslationJobProgress from './pages/TranslationJobProgress';
import TranslationJobResults from './pages/TranslationJobResults';
import MigrationPlan from './pages/MigrationPlan';
import WorkloadDetail from './pages/WorkloadDetail';
import MigrationDetail from './pages/MigrationDetail';
import MigrationSynthesisResults from './pages/MigrationSynthesisResults';
import AssessmentDetail from './pages/AssessmentDetail';
import Migrations from './pages/Migrations';
import Connections from './pages/Connections';

function ProtectedRoute({ children }: { children: ReactNode }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/* ─── Nav config ──────────────────────────────────────────────────── */

const NAV_LINKS = [
  { to: '/dashboard',   label: 'Overview'     },
  { to: '/resources',   label: 'Resources'    },
  { to: '/connections', label: 'Connections'  },
];

/* ─── Layout ──────────────────────────────────────────────────────── */

function Layout() {
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('token');
    window.location.href = '/login';
  };

  return (
    <div className="min-h-screen flex">
      {/* ─── Sidebar ─────────────────────────────────────────────── */}
      <aside
        className="w-[232px] flex flex-col flex-shrink-0"
        style={{
          background: 'var(--color-surface)',
          borderRight: '1px solid var(--color-rule)',
        }}
      >
        {/* Brand */}
        <div
          className="flex items-center gap-3 px-5 py-5"
          style={{ borderBottom: '1px solid var(--color-rule)' }}
        >
          <div
            className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
            style={{
              background: 'var(--color-ember)',
              color: '#fff',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.6rem',
              fontWeight: 700,
              letterSpacing: '0.05em',
            }}
          >
            OCI
          </div>
          <div>
            <p style={{
              fontFamily: 'var(--font-display)',
              fontSize: '0.8125rem',
              fontWeight: 600,
              color: 'var(--color-text-bright)',
              lineHeight: 1.2,
              letterSpacing: '-0.01em',
            }}>
              Migration
            </p>
            <p style={{
              fontSize: '0.625rem',
              color: 'var(--color-rail)',
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              fontWeight: 500,
              marginTop: 1,
            }}>
              AWS &rarr; Oracle Cloud
            </p>
          </div>
        </div>

        {/* ── Flat nav ────────────────────────────────────────────── */}
        <nav className="flex-1 overflow-y-auto py-3 px-3" aria-label="Main navigation">
          <div className="space-y-0.5">
            {NAV_LINKS.map((route) => {
              const active = location.pathname === route.to || location.pathname.startsWith(route.to + '/');
              return (
                <NavLink
                  key={route.to}
                  to={route.to}
                  className="flex items-center gap-2.5 px-2 py-[6px] rounded text-xs font-medium transition-all"
                  style={{
                    color: active ? 'var(--color-ember)' : 'var(--color-text-dim)',
                    background: active ? 'var(--color-ember-dim)' : 'transparent',
                  }}
                  onMouseEnter={(e) => {
                    if (!active) {
                      e.currentTarget.style.color = 'var(--color-text-bright)';
                      e.currentTarget.style.background = 'var(--color-well)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!active) {
                      e.currentTarget.style.color = 'var(--color-text-dim)';
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  <span style={{
                    width: 4,
                    height: 4,
                    borderRadius: '50%',
                    background: active ? 'var(--color-ember)' : 'var(--color-fence)',
                    flexShrink: 0,
                    transition: 'background 0.15s',
                  }} />
                  {route.label}
                </NavLink>
              );
            })}
          </div>

          {/* Separator + Settings */}
          <div style={{ borderTop: '1px solid var(--color-rule)', margin: '8px 8px 6px' }} />
          <NavLink
            to="/settings"
            className="flex items-center gap-2.5 px-2 py-[6px] rounded text-xs font-medium transition-all"
            style={{
              color: location.pathname === '/settings' ? 'var(--color-ember)' : 'var(--color-text-dim)',
              background: location.pathname === '/settings' ? 'var(--color-ember-dim)' : 'transparent',
            }}
            onMouseEnter={(e) => {
              if (location.pathname !== '/settings') {
                e.currentTarget.style.color = 'var(--color-text-bright)';
                e.currentTarget.style.background = 'var(--color-well)';
              }
            }}
            onMouseLeave={(e) => {
              if (location.pathname !== '/settings') {
                e.currentTarget.style.color = 'var(--color-text-dim)';
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            <svg style={{ width: 14, height: 14 }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            </svg>
            Settings
          </NavLink>
        </nav>

        {/* Sign Out */}
        <div style={{ padding: 8, borderTop: '1px solid var(--color-rule)' }}>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-2 py-[6px] rounded text-xs font-medium transition-all"
            style={{ color: 'var(--color-text-dim)', background: 'transparent', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--color-error)';
              e.currentTarget.style.background = 'rgba(220,38,38,0.04)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--color-text-dim)';
              e.currentTarget.style.background = 'transparent';
            }}
          >
            <svg style={{ width: 14, height: 14 }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Sign Out
          </button>
        </div>
      </aside>

      {/* ─── Main Content ────────────────────────────────────────── */}
      <main className="flex-1 overflow-auto" style={{ background: 'var(--color-void)' }}>
        <div className="p-8 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

/* ─── Placeholder pages ───────────────────────────────────────────── */

function ComingSoonPage({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="page-title">{title}</h1>
        <p className="page-subtitle">{sub}</p>
      </div>
      <div className="panel">
        <div className="empty-state" style={{ padding: '4rem 2rem' }}>
          <p style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', fontWeight: 600, color: 'var(--color-text-bright)', fontStyle: 'italic' }}>
            Coming soon
          </p>
          <p style={{ color: 'var(--color-text-dim)', fontSize: '0.8125rem', marginTop: 8, maxWidth: 340, marginLeft: 'auto', marginRight: 'auto' }}>
            This phase unlocks once workloads are assessed and migration plans generated.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ─── Routes ──────────────────────────────────────────────────────── */

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/migrations" element={<Migrations />} />
          <Route path="/migrations/:id" element={<MigrationDetail />} />
          <Route path="/migrations/:id/plan" element={<MigrationSynthesisResults />} />
          <Route path="/resources" element={<Resources />} />
          <Route path="/connections" element={<Connections />} />
          <Route path="/assessments/:assessmentId" element={<AssessmentDetail />} />
          <Route path="/workloads/:workloadId" element={<WorkloadDetail />} />
          <Route path="/plans/:planId" element={<MigrationPlan />} />
          <Route path="/translation-jobs" element={<TranslationJobList />} />
          <Route path="/translation-jobs/new" element={<TranslationJobNew />} />
          <Route path="/translation-jobs/:id" element={<TranslationJobProgress />} />
          <Route path="/translation-jobs/:id/results" element={<TranslationJobResults />} />
          <Route path="/migrate/execution" element={<ComingSoonPage title="Migration Execution" sub="Execute migration waves and track progress" />} />
          <Route path="/migrate/waves" element={<ComingSoonPage title="Wave Planning" sub="Organize workloads into migration waves" />} />
          <Route path="/validation" element={<ComingSoonPage title="Validation" sub="Post-migration testing and verification" />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
