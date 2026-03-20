import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useRegister } from '../api/hooks/useAuth';

export default function Register() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [localError, setLocalError] = useState('');
  const navigate = useNavigate();
  const register = useRegister();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError('');
    if (password !== confirmPassword) { setLocalError('Passwords do not match.'); return; }
    if (password.length < 6) { setLocalError('Password must be at least 6 characters.'); return; }
    register.mutate({ email, password }, { onSuccess: () => navigate('/dashboard') });
  };

  const errorMessage =
    localError ||
    (register.isError
      ? (register.error as any)?.response?.data?.detail || 'Registration failed. Please try again.'
      : '');

  return (
    <div
      className="min-h-screen flex items-center justify-center relative"
      style={{ background: 'var(--color-void)' }}
    >
      {/* Grid bg */}
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

      <div
        className="relative w-full max-w-sm mx-4 rounded-xl overflow-hidden"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-fence)',
          boxShadow: 'var(--shadow-modal)',
        }}
      >
        <div className="h-0.5 w-full" style={{ background: 'var(--color-ember)' }} />

        <div className="px-8 py-8">
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
              Create Account
            </h1>
            <p className="text-xs mt-1" style={{ color: '#64748b' }}>
              Get started with OCI Migration Tool
            </p>
          </div>

          {errorMessage && (
            <div className="alert alert-error mb-5" role="alert">{errorMessage}</div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="register-email" className="field-label">Email</label>
              <input
                id="register-email"
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
              <label htmlFor="register-password" className="field-label">Password</label>
              <input
                id="register-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="field-input"
                placeholder="Min. 6 characters"
              />
            </div>
            <div>
              <label htmlFor="register-confirm" className="field-label">Confirm Password</label>
              <input
                id="register-confirm"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={6}
                className="field-input"
                placeholder="••••••••"
              />
            </div>
            <button
              type="submit"
              disabled={register.isPending}
              className="btn btn-primary btn-lg w-full mt-2"
            >
              {register.isPending ? (
                <>
                  <span className="spinner" />
                  Creating account…
                </>
              ) : 'Create Account'}
            </button>
          </form>

          <p className="mt-5 text-center text-xs" style={{ color: '#64748b' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: 'var(--color-ember)' }} className="font-medium hover:opacity-80 transition-opacity">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
