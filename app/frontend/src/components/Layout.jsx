// What this file does: App shell — sidebar nav + top bar + outlet for page content.
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import {
  LayoutDashboard, LineChart, BrainCircuit,
  PieChart, GitCompare, LogOut, Zap
} from 'lucide-react'

const NAV = [
  { to: '/dashboard',  label: 'Dashboard',   icon: LayoutDashboard },
  { to: '/market',     label: 'Market Data',  icon: LineChart },
  { to: '/predictor',  label: 'Predictor',    icon: BrainCircuit },
  { to: '/sectors',    label: 'Sectors',      icon: PieChart },
  { to: '/comparison', label: 'DB Compare',   icon: GitCompare },
]

export default function Layout() {
  const { user, logout, backend, setBackend } = useAuth()

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* ── Sidebar ── */}
      <aside style={{
        width: 220,
        flexShrink: 0,
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 0',
      }}>
        {/* Logo */}
        <div style={{ padding: '0 20px 28px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 34, height: 34, borderRadius: 8,
              background: 'var(--blue)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 16px var(--blue-glow)',
            }}>
              <Zap size={18} color="#fff" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: '.02em' }}>CMIA</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '.06em' }}>MARKETS INTEL</div>
            </div>
          </div>
        </div>

        {/* Nav links */}
        <nav style={{ flex: 1, padding: '0 10px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '9px 12px',
                borderRadius: 8,
                textDecoration: 'none',
                fontSize: 13.5,
                fontWeight: isActive ? 600 : 400,
                color: isActive ? '#fff' : 'var(--text-secondary)',
                background: isActive ? 'var(--blue)' : 'transparent',
                boxShadow: isActive ? '0 0 12px var(--blue-glow)' : 'none',
                transition: 'all 180ms ease',
              })}
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Backend toggle */}
        <div style={{ padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, letterSpacing: '.06em' }}>DB BACKEND</div>
          <div style={{
            display: 'flex',
            background: 'var(--bg-elevated)',
            borderRadius: 8,
            padding: 3,
            border: '1px solid var(--border)',
          }}>
            {['azure', 'snowflake'].map(b => (
              <button
                key={b}
                onClick={() => setBackend(b)}
                style={{
                  flex: 1,
                  padding: '5px 0',
                  borderRadius: 6,
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: 600,
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '.04em',
                  background: backend === b ? 'var(--blue)' : 'transparent',
                  color: backend === b ? '#fff' : 'var(--text-muted)',
                  transition: 'all 180ms ease',
                  boxShadow: backend === b ? '0 0 8px var(--blue-glow)' : 'none',
                }}
              >
                {b === 'azure' ? 'AZ' : 'SF'}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, textAlign: 'center' }}>
            {backend === 'azure' ? '↳ Azure SQL (OLTP)' : '↳ Snowflake (OLAP)'}
          </div>
        </div>

        {/* User + logout */}
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500 }}>{user?.username}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Administrator</div>
          </div>
          <button onClick={logout} className="btn btn-ghost" style={{ padding: '6px 8px' }} title="Logout">
            <LogOut size={15} />
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main style={{ flex: 1, overflowY: 'auto', background: 'var(--bg-base)' }}>
        <Outlet />
      </main>
    </div>
  )
}
