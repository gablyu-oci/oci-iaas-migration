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
      {/* Decorative diagonals */}
      <div
        className="absolute inset-0 pointer-events-none overflow-hidden"
        style={{ opacity: 0.035 }}
      >
        <div style={{
          position: 'absolute',
          top: '-20%',
          right: '-10%',
          width: '60%',
          height: '140%',
          background: 'linear-gradient(135deg, var(--color-ember) 0%, transparent 60%)',
          transform: 'rotate(-12deg)',
        }} />
        <div style={{
          position: 'absolute',
          bottom: '-20%',
          left: '-10%',
          width: '50%',
          height: '120%',
          background: 'linear-gradient(-45deg, var(--color-ember) 0%, transparent 50%)',
          transform: 'rotate(8deg)',
        }} />
      </div>

      {/* Card */}
      <div
        className="relative w-full max-w-sm mx-4 rounded-lg overflow-hidden animate-slide-up"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-rule)',
          boxShadow: 'var(--shadow-modal)',
        }}
      >
        {/* Top accent */}
        <div style={{ height: 3, background: 'var(--color-ember)' }} />

        <div className="px-8 py-8">
          {/* Brand */}
          <div className="mb-8 text-center">
            <div
              className="inline-flex items-center justify-center w-10 h-10 rounded mb-4"
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
            <h1 style={{
              fontFamily: 'var(--font-display)',
              fontSize: '1.25rem',
              fontWeight: 600,
              color: 'var(--color-text-bright)',
              letterSpacing: '-0.01em',
            }}>
              Migration Platform
            </h1>
            <p style={{
              fontSize: '0.8125rem',
              color: 'var(--color-text-dim)',
              marginTop: 4,
            }}>
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
                <><span className="spinner" /> Signing in…</>
              ) : 'Sign In'}
            </button>
          </form>

          <p className="mt-5 text-center text-xs" style={{ color: 'var(--color-text-dim)' }}>
            No account?{' '}
            <Link
              to="/register"
              style={{ color: 'var(--color-ember)', fontWeight: 500 }}
              className="hover:opacity-80 transition-opacity"
            >
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
