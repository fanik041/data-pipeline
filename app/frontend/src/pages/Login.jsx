// What this file does: Login gate — validates credentials against /auth/login (Azure SQL creds).
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { auth } from '../api.js'
import { Zap, Eye, EyeOff, AlertCircle } from 'lucide-react'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm]       = useState({ username: '', password: '' })
  const [showPw, setShowPw]   = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await auth.login(form.username, form.password)
      login(res.username, res.access_token)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err.detail?.trace || err.message || 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-base)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Ambient glow blobs */}
      <div style={{
        position: 'absolute', top: '15%', left: '20%',
        width: 600, height: 600, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(59,130,246,.07) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', bottom: '10%', right: '15%',
        width: 400, height: 400, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(245,158,11,.05) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      {/* Grid lines */}
      <div style={{
        position: 'absolute', inset: 0, opacity: .03,
        backgroundImage: 'linear-gradient(var(--blue) 1px, transparent 1px), linear-gradient(90deg, var(--blue) 1px, transparent 1px)',
        backgroundSize: '60px 60px',
        pointerEvents: 'none',
      }} />

      {/* Login card */}
      <div className="fade-up" style={{
        width: '100%', maxWidth: 420,
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        padding: '40px 40px 36px',
        boxShadow: '0 0 60px rgba(0,0,0,.5), 0 0 0 1px rgba(59,130,246,.06)',
        position: 'relative',
        zIndex: 1,
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 10,
            background: 'var(--blue)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 20px var(--blue-glow)',
          }}>
            <Zap size={22} color="#fff" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 20, letterSpacing: '.01em' }}>CMIA</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', letterSpacing: '.08em' }}>
              CAPITAL MARKETS INTELLIGENCE
            </div>
          </div>
        </div>

        <h1 style={{ fontSize: 18, fontWeight: 600, marginBottom: 6 }}>Sign in</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 28 }}>
          Use your Azure SQL credentials to access the platform.
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Username */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 6, letterSpacing: '.04em' }}>
              USERNAME
            </label>
            <input
              className="input"
              type="text"
              value={form.username}
              onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
              placeholder="admin"
              autoComplete="username"
              required
            />
          </div>

          {/* Password */}
          <div>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 6, letterSpacing: '.04em' }}>
              PASSWORD
            </label>
            <div style={{ position: 'relative' }}>
              <input
                className="input"
                type={showPw ? 'text' : 'password'}
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="••••••••"
                autoComplete="current-password"
                required
                style={{ paddingRight: 40 }}
              />
              <button
                type="button"
                onClick={() => setShowPw(v => !v)}
                style={{
                  position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
                  padding: 4,
                }}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: 8,
              padding: '10px 12px',
              background: 'var(--red-glow)',
              border: '1px solid rgba(239,68,68,.25)',
              borderRadius: 8,
              fontSize: 12,
              color: '#FCA5A5',
            }}>
              <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1, color: 'var(--red)' }} />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !form.username || !form.password}
            className="btn btn-primary"
            style={{ width: '100%', height: 42, marginTop: 4, fontSize: 14, fontWeight: 600 }}
          >
            {loading ? <><span className="spinner" /> Authenticating…</> : 'Sign in'}
          </button>
        </form>

        <div style={{ marginTop: 24, padding: '12px 14px', background: 'var(--bg-elevated)', borderRadius: 8, fontSize: 12, color: 'var(--text-muted)' }}>
          <span style={{ color: 'var(--amber)', fontFamily: 'var(--font-mono)' }}>ℹ</span>{' '}
          Credentials are validated against the Azure SQL source DB.
          Your role permissions apply to all queries.
        </div>
      </div>
    </div>
  )
}
