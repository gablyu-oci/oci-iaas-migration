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
import Migrations from './pages/Migrations';

function ProtectedRoute({ children }: { children: ReactNode }) {
  const token = localStorage.getItem('token');
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

const NAV_ITEMS = [
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    to: '/migrations',
    label: 'Migrations',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  {
    to: '/resources',
    label: 'Resources',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2" />
      </svg>
    ),
  },
  {
    to: '/translation-jobs',
    label: 'Translation Jobs',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    to: '/settings',
    label: 'Settings',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      </svg>
    ),
  },
];

function Layout() {
  const location = useLocation();

  const handleLogout = () => {
    localStorage.removeItem('token');
    window.location.href = '/login';
  };

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--color-void)' }}>
      {/* Sidebar */}
      <aside
        className="w-56 flex flex-col flex-shrink-0 relative"
        style={{
          background: 'var(--color-surface)',
          borderRight: '1px solid var(--color-rule)',
        }}
      >
        {/* Brand */}
        <div
          className="flex items-center gap-2.5 px-5 py-4"
          style={{ borderBottom: '1px solid var(--color-rule)' }}
        >
          {/* Monogram */}
          <div
            className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0 text-xs font-bold"
            style={{
              background: 'rgba(249,115,22,0.1)',
              border: '1px solid rgba(249,115,22,0.25)',
              color: 'var(--color-ember)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            OCI
          </div>
          <div>
            <p className="text-xs font-semibold leading-none" style={{ color: '#0f172a' }}>
              Migration Tool
            </p>
            <p className="text-[0.625rem] leading-none mt-0.5" style={{ color: '#94a3b8' }}>
              AWS → OCI
            </p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 space-y-0.5 px-2" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => {
            const active =
              location.pathname === item.to ||
              location.pathname.startsWith(item.to + '/');
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className="flex items-center gap-2.5 px-3 py-2 rounded text-xs font-medium transition-all duration-100 relative group"
                style={
                  active
                    ? {
                        background: 'rgba(249,115,22,0.08)',
                        color: 'var(--color-ember)',
                        borderLeft: '2px solid var(--color-ember)',
                        paddingLeft: '0.625rem',
                      }
                    : {
                        color: '#64748b',
                        borderLeft: '2px solid transparent',
                        paddingLeft: '0.625rem',
                      }
                }
                onMouseEnter={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.color = '#334155';
                    (e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.04)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    (e.currentTarget as HTMLElement).style.color = '#64748b';
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {item.icon}
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        {/* Logout */}
        <div
          className="p-2"
          style={{ borderTop: '1px solid var(--color-rule)' }}
        >
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded text-xs font-medium transition-colors duration-100"
            style={{ color: '#64748b' }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.color = '#334155';
              (e.currentTarget as HTMLElement).style.background = 'rgba(0,0,0,0.04)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.color = '#64748b';
              (e.currentTarget as HTMLElement).style.background = 'transparent';
            }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/migrations" element={<Migrations />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/resources" element={<Resources />} />
          <Route path="/translation-jobs" element={<TranslationJobList />} />
          <Route path="/translation-jobs/new" element={<TranslationJobNew />} />
          <Route path="/translation-jobs/:id" element={<TranslationJobProgress />} />
          <Route path="/translation-jobs/:id/results" element={<TranslationJobResults />} />
          <Route path="/plans/:planId" element={<MigrationPlan />} />
          <Route path="/workloads/:workloadId" element={<WorkloadDetail />} />
          <Route path="/migrations/:id" element={<MigrationDetail />} />
          <Route path="/migrations/:id/plan" element={<MigrationSynthesisResults />} />
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
