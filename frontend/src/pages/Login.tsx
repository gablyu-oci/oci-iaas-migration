import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useLogin } from '../api/hooks/useAuth';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const login = useLogin();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ email, password }, { onSuccess: () => navigate('/dashboard') });
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center relative"
      style={{ background: 'var(--color-void)' }}
    >
      {/* Subtle grid background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(148,163,184,0.3) 1px, transparent 1px),
            linear-gradient(90deg, rgba(148,163,184,0.3) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
          maskImage: 'radial-gradient(ellipse 70% 70% at 50% 50%, black 40%, transparent 100%)',
        }}
      />

      {/* Card */}
      <div
        className="relative w-full max-w-sm mx-4 rounded-xl overflow-hidden"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-fence)',
          boxShadow: 'var(--shadow-modal)',
        }}
      >
        {/* Top accent bar */}
        <div className="h-0.5 w-full" style={{ background: 'var(--color-ember)' }} />

        <div className="px-8 py-8">
          {/* Brand */}
          <div className="mb-8 text-center">
            <div
              className="inline-flex items-center justify-center w-10 h-10 rounded-lg mb-4 text-sm font-bold"
              style={{
                background: 'rgba(249,115,22,0.12)',
                border: '1px solid rgba(249,115,22,0.25)',
                color: 'var(--color-ember)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              OCI
            </div>
            <h1 className="text-base font-semibold" style={{ color: '#0f172a' }}>
              OCI Migration Tool
            </h1>
            <p className="text-xs mt-1" style={{ color: '#64748b' }}>
              Sign in to your account
            </p>
          </div>

          {login.isError && (
            <div className="alert alert-error mb-5" role="alert">
              {(login.error as any)?.response?.data?.detail || 'Login failed. Please try again.'}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="field-label">Email</label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                className="field-input"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <label htmlFor="login-password" className="field-label">Password</label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="field-input"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              disabled={login.isPending}
              className="btn btn-primary btn-lg w-full mt-2"
            >
              {login.isPending ? (
                <>
                  <span className="spinner" />
                  Signing in…
                </>
              ) : 'Sign In'}
            </button>
          </form>

          <p className="mt-5 text-center text-xs" style={{ color: '#64748b' }}>
            No account?{' '}
            <Link to="/register" style={{ color: 'var(--color-ember)' }} className="font-medium hover:opacity-80 transition-opacity">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
