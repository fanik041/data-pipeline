// What this file does: Dashboard — KPI cards, top signals, sector signal distribution.
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { api } from '../api.js'
import { TrendingUp, TrendingDown, BarChart2, Layers, RefreshCw } from 'lucide-react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell
} from 'recharts'

function KpiCard({ label, value, sub, accent, icon: Icon }) {
  return (
    <div className="card fade-up" style={{
      display: 'flex', flexDirection: 'column', gap: 12,
      borderLeft: `3px solid ${accent}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '.08em' }}>
          {label}
        </span>
        <div style={{
          width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: `${accent}18`,
        }}>
          <Icon size={16} color={accent} />
        </div>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 700, color: accent, lineHeight: 1 }}>
        {value ?? '—'}
      </div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

const SECTOR_COLORS = ['#3B82F6','#10B981','#F59E0B','#EF4444','#8B5CF6','#EC4899','#14B8A6','#F97316','#6366F1','#84CC16']

export default function Dashboard() {
  const { backend } = useAuth()
  const [symbols, setSymbols]   = useState([])
  const [signals, setSignals]   = useState([])
  const [loading, setLoading]   = useState(true)
  const [lastRefresh, setLastRefresh] = useState(null)

  async function load() {
    setLoading(true)
    try {
      const syms = await api.symbols(backend)
      setSymbols(syms)

      // load predictions for all symbols (first 20 to keep it snappy)
      const subset = syms.slice(0, 20)
      const results = await Promise.allSettled(
        subset.map(s => api.predict(s.symbol, backend))
      )
      const data = results
        .filter(r => r.status === 'fulfilled')
        .map(r => r.value)
      setSignals(data)
      setLastRefresh(new Date().toLocaleTimeString())
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [backend])

  const bullish = signals.filter(s => s.target_next_day_up === 1).length
  const bearish = signals.filter(s => s.target_next_day_up === 0).length
  const ratio   = signals.length ? Math.round((bullish / signals.length) * 100) : 0

  // sector aggregation for bar chart
  const sectorMap = {}
  symbols.forEach(s => {
    if (!sectorMap[s.sector]) sectorMap[s.sector] = 0
    sectorMap[s.sector]++
  })
  const sectorData = Object.entries(sectorMap).map(([sector, count]) => ({
    sector: sector.split(' ')[0], // first word for brevity
    count,
  }))

  // top bullish signals by RSI
  const topBullish = signals
    .filter(s => s.target_next_day_up === 1)
    .sort((a, b) => (b.rsi_14 ?? 0) - (a.rsi_14 ?? 0))
    .slice(0, 8)

  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) return null
    return (
      <div style={{ background:'var(--bg-elevated)', border:'1px solid var(--border)', borderRadius:8, padding:'8px 12px', fontSize:12 }}>
        <div style={{ color:'var(--text-secondary)' }}>{payload[0].payload.sector}</div>
        <div style={{ fontFamily:'var(--font-mono)', color:'var(--blue)', fontWeight:600 }}>{payload[0].value} symbols</div>
      </div>
    )
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>Dashboard</h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
            Market intelligence overview · <span className="mono" style={{ color: 'var(--blue)' }}>{backend.toUpperCase()}</span>
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {lastRefresh && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Updated {lastRefresh}</span>}
          <button className="btn btn-ghost" onClick={load} disabled={loading} style={{ gap: 6 }}>
            <RefreshCw size={14} className={loading ? 'spinner' : ''} style={loading ? { animation: 'spin .7s linear infinite' } : {}} />
            Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', padding: 32 }}>
          <div className="spinner" /> Loading market data from {backend}…
        </div>
      ) : (
        <>
          {/* KPI Row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 28 }}>
            <KpiCard label="SYMBOLS TRACKED"   value={symbols.length}    sub="Active equities"           accent="var(--blue)"  icon={BarChart2}   />
            <KpiCard label="SECTORS COVERED"   value={Object.keys(sectorMap).length} sub="Market segments" accent="var(--amber)" icon={Layers}     />
            <KpiCard label="BULLISH SIGNALS"   value={bullish}           sub={`${ratio}% of total`}     accent="var(--green)" icon={TrendingUp}  />
            <KpiCard label="BEARISH SIGNALS"   value={bearish}           sub={`${100-ratio}% of total`} accent="var(--red)"   icon={TrendingDown} />
          </div>

          {/* Mid row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 16, marginBottom: 28 }}>
            {/* Top Bullish Picks */}
            <div className="card">
              <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <h2 style={{ fontSize: 14, fontWeight: 600 }}>Top Bullish Signals</h2>
                <span className="badge badge-green">↑ BUY</span>
              </div>
              {topBullish.length === 0
                ? <p style={{ color:'var(--text-muted)', fontSize:13 }}>No bullish signals available.</p>
                : topBullish.map(sig => (
                  <div key={sig.symbol} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '8px 0', borderBottom: '1px solid var(--border)',
                  }}>
                    <div>
                      <div style={{ fontFamily:'var(--font-mono)', fontWeight:600, fontSize:13 }}>{sig.symbol}</div>
                      <div style={{ fontSize:11, color:'var(--text-muted)' }}>{sig.date}</div>
                    </div>
                    <div style={{ textAlign:'right' }}>
                      <div style={{ fontFamily:'var(--font-mono)', color:'var(--green)', fontWeight:600, fontSize:13 }}>
                        RSI {sig.rsi_14 != null ? sig.rsi_14.toFixed(1) : '—'}
                      </div>
                      <div style={{ fontSize:11, color:'var(--text-muted)' }}>
                        MACD {sig.macd != null ? sig.macd.toFixed(2) : '—'}
                      </div>
                    </div>
                  </div>
                ))
              }
            </div>

            {/* Sector distribution bar chart */}
            <div className="card">
              <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 20 }}>Symbol Distribution by Sector</h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={sectorData} margin={{ left: -10, bottom: 0 }}>
                  <XAxis
                    dataKey="sector"
                    tick={{ fontSize: 11, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
                    axisLine={false} tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                    axisLine={false} tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--bg-elevated)' }} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {sectorData.map((_, i) => (
                      <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Signal signal overview table */}
          <div className="card">
            <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>All Signal Predictions</h2>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Symbol','Sector','Date','RSI-14','MACD','BB Pos','Volatility','Signal'].map(h => (
                      <th key={h} style={{
                        textAlign: 'left', padding: '8px 12px', fontSize: 11,
                        color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '.06em', whiteSpace: 'nowrap'
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {signals.map(sig => (
                    <tr key={sig.symbol} style={{
                      borderBottom: '1px solid var(--border)',
                      transition: 'background var(--tx)',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-surface)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '9px 12px', fontFamily:'var(--font-mono)', fontWeight:600, color:'var(--blue)' }}>{sig.symbol}</td>
                      <td style={{ padding: '9px 12px', color:'var(--text-secondary)', fontSize:12 }}>{sig.date}</td>
                      <td style={{ padding: '9px 12px', color:'var(--text-secondary)', fontSize:12 }}>{sig.date}</td>
                      <td style={{ padding: '9px 12px', fontFamily:'var(--font-mono)' }}>{sig.rsi_14?.toFixed(1) ?? '—'}</td>
                      <td style={{ padding: '9px 12px', fontFamily:'var(--font-mono)' }}>{sig.macd?.toFixed(3) ?? '—'}</td>
                      <td style={{ padding: '9px 12px', fontFamily:'var(--font-mono)' }}>{sig.bb_position?.toFixed(3) ?? '—'}</td>
                      <td style={{ padding: '9px 12px', fontFamily:'var(--font-mono)' }}>{sig.volatility_20d?.toFixed(4) ?? '—'}</td>
                      <td style={{ padding: '9px 12px' }}>
                        <span className={`badge ${sig.target_next_day_up === 1 ? 'badge-green' : 'badge-red'}`}>
                          {sig.target_next_day_up === 1 ? '↑ BUY' : '↓ SELL'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
