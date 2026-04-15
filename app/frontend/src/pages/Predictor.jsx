// What this file does: Predictor page — ML signal breakdown for a single symbol.
import { useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { api } from '../api.js'
import { Search, TrendingUp, TrendingDown, Activity } from 'lucide-react'

const SYMBOLS = ['AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','JPM','JNJ','V',
  'WMT','PG','XOM','BAC','HD','CVX','KO','ABBV','PFE','MRK']

function Gauge({ label, value, min, max, low, high, unit = '', invert = false }) {
  const clampedValue = value != null ? Math.max(min, Math.min(max, value)) : null
  const pct = clampedValue != null ? ((clampedValue - min) / (max - min)) * 100 : null

  let color = 'var(--blue)'
  if (clampedValue != null) {
    if (invert) {
      color = clampedValue > high ? 'var(--red)' : clampedValue < low ? 'var(--green)' : 'var(--amber)'
    } else {
      color = clampedValue > high ? 'var(--red)' : clampedValue < low ? 'var(--green)' : 'var(--amber)'
    }
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline' }}>
        <span style={{ fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em' }}>{label}</span>
        <span style={{ fontFamily:'var(--font-mono)', fontWeight:600, fontSize:16, color }}>
          {value != null ? `${Number(value).toFixed(2)}${unit}` : '—'}
        </span>
      </div>
      <div style={{ height:6, background:'var(--bg-elevated)', borderRadius:3, overflow:'hidden' }}>
        {pct != null && (
          <div style={{
            height:'100%', width:`${pct}%`,
            background: `linear-gradient(90deg, var(--blue-dim), ${color})`,
            borderRadius:3,
            transition:'width 600ms ease',
          }} />
        )}
      </div>
      <div style={{ display:'flex', justifyContent:'space-between', fontSize:10, color:'var(--text-muted)' }}>
        <span className="mono">{min}{unit}</span>
        <span className="mono">{max}{unit}</span>
      </div>
    </div>
  )
}

function MetricRow({ label, value, color, mono = true }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 0', borderBottom:'1px solid var(--border)' }}>
      <span style={{ fontSize:13, color:'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontFamily: mono ? 'var(--font-mono)' : 'var(--font-sans)', fontWeight:600, color: color || 'var(--text-primary)' }}>
        {value ?? '—'}
      </span>
    </div>
  )
}

export default function Predictor() {
  const { backend } = useAuth()
  const [symbol,  setSymbol]  = useState('AAPL')
  const [input,   setInput]   = useState('AAPL')
  const [signal,  setSignal]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  async function load(sym) {
    setLoading(true)
    setError(null)
    try {
      const data = await api.predict(sym, backend)
      setSignal(data)
    } catch (err) {
      setError(err.message)
      setSignal(null)
    } finally {
      setLoading(false)
    }
  }

  function handleSearch(e) {
    e.preventDefault()
    const sym = input.trim().toUpperCase()
    if (sym) { setSymbol(sym); setInput(sym); load(sym) }
  }

  function handleSelect(sym) {
    setSymbol(sym)
    setInput(sym)
    load(sym)
  }

  // Load on first render
  useState(() => { load('AAPL') }, [])

  const isBull = signal?.target_next_day_up === 1

  return (
    <div style={{ padding:'28px 32px', maxWidth:900 }}>
      <div style={{ marginBottom:24 }}>
        <h1 style={{ fontSize:22, fontWeight:700 }}>ML Predictor</h1>
        <p style={{ fontSize:13, color:'var(--text-secondary)', marginTop:2 }}>
          Next-day direction signal from technical indicators · <span className="mono" style={{ color:'var(--blue)' }}>{backend.toUpperCase()}</span>
        </p>
      </div>

      {/* Controls */}
      <div style={{ display:'flex', gap:12, marginBottom:24, flexWrap:'wrap', alignItems:'flex-end' }}>
        <div>
          <label style={{ display:'block', fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em', marginBottom:6 }}>SYMBOL</label>
          <form onSubmit={handleSearch} style={{ display:'flex', gap:6 }}>
            <input
              className="input"
              value={input}
              onChange={e => setInput(e.target.value.toUpperCase())}
              style={{ width:120, fontFamily:'var(--font-mono)', fontWeight:600 }}
              placeholder="e.g. AAPL"
            />
            <button type="submit" className="btn btn-primary" style={{ padding:'8px 12px' }}>
              <Search size={14} />
            </button>
          </form>
        </div>
        <div>
          <label style={{ display:'block', fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em', marginBottom:6 }}>QUICK SELECT</label>
          <select className="select" value={symbol} onChange={e => handleSelect(e.target.value)} style={{ fontFamily:'var(--font-mono)' }}>
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {loading && (
        <div style={{ display:'flex', alignItems:'center', gap:10, color:'var(--text-muted)', padding:40 }}>
          <div className="spinner" /> Fetching signal for {symbol}…
        </div>
      )}
      {error && !loading && (
        <div style={{ color:'var(--red)', padding:24, background:'var(--red-glow)', borderRadius:10, border:'1px solid rgba(239,68,68,.2)' }}>
          ⚠ {error}
        </div>
      )}

      {signal && !loading && (
        <div className="fade-up" style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20 }}>
          {/* Signal verdict */}
          <div className="card" style={{
            gridColumn:'1/-1',
            border: isBull ? '1px solid rgba(16,185,129,.3)' : '1px solid rgba(239,68,68,.3)',
            background: isBull ? 'rgba(16,185,129,.04)' : 'rgba(239,68,68,.04)',
            display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:16,
          }}>
            <div style={{ display:'flex', alignItems:'center', gap:20 }}>
              <div style={{
                width:64, height:64, borderRadius:16,
                background: isBull ? 'var(--green-glow)' : 'var(--red-glow)',
                border: `2px solid ${isBull ? 'var(--green)' : 'var(--red)'}`,
                display:'flex', alignItems:'center', justifyContent:'center',
                boxShadow: `0 0 24px ${isBull ? 'var(--green-glow)' : 'var(--red-glow)'}`,
              }}>
                {isBull
                  ? <TrendingUp size={28} color="var(--green)" />
                  : <TrendingDown size={28} color="var(--red)" />}
              </div>
              <div>
                <div style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:28, color: isBull ? 'var(--green)' : 'var(--red)' }}>
                  {isBull ? 'BUY' : 'SELL'}
                </div>
                <div style={{ fontSize:13, color:'var(--text-secondary)' }}>Next-day direction prediction</div>
              </div>
            </div>
            <div style={{ textAlign:'right' }}>
              <div style={{ fontFamily:'var(--font-mono)', fontSize:22, fontWeight:700 }}>{signal.symbol}</div>
              <div style={{ fontSize:13, color:'var(--text-muted)' }}>as of {signal.date}</div>
              <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:4 }}>{backend === 'azure' ? 'reports.v_latest_features' : 'CMIA_DW.MARTS.V_LATEST_FEATURES'}</div>
            </div>
          </div>

          {/* Momentum gauges */}
          <div className="card">
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:20 }}>
              <Activity size={15} color="var(--blue)" />
              <h2 style={{ fontSize:14, fontWeight:600 }}>Momentum Indicators</h2>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
              <Gauge label="RSI-14"       value={signal.rsi_14}       min={0}   max={100} low={30}  high={70} />
              <Gauge label="BB POSITION"  value={signal.bb_position}  min={0}   max={1}   low={0.2} high={0.8} />
            </div>
          </div>

          {/* Trend metrics */}
          <div className="card">
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:20 }}>
              <Activity size={15} color="var(--amber)" />
              <h2 style={{ fontSize:14, fontWeight:600 }}>Trend & Volatility</h2>
            </div>
            <div>
              <MetricRow label="MACD"        value={signal.macd?.toFixed(4)}       color="var(--blue)" />
              <MetricRow label="MACD Signal" value={signal.macd_signal?.toFixed(4)} color="var(--text-secondary)" />
              <MetricRow label="MA-5"        value={signal.ma_5 != null ? `$${signal.ma_5.toFixed(2)}` : null} />
              <MetricRow label="MA-20"       value={signal.ma_20 != null ? `$${signal.ma_20.toFixed(2)}` : null} />
              <MetricRow
                label="MA Crossover"
                value={
                  signal.ma_5 != null && signal.ma_20 != null
                    ? signal.ma_5 > signal.ma_20 ? 'Golden Cross ↑' : 'Death Cross ↓'
                    : '—'
                }
                color={
                  signal.ma_5 != null && signal.ma_20 != null
                    ? signal.ma_5 > signal.ma_20 ? 'var(--green)' : 'var(--red)'
                    : undefined
                }
                mono={false}
              />
              <MetricRow label="Volatility 20D" value={signal.volatility_20d?.toFixed(4)} color="var(--amber)" />
            </div>
          </div>

          {/* Interpretation card */}
          <div className="card" style={{ gridColumn:'1/-1', background:'var(--bg-elevated)', borderColor:'var(--border-light)' }}>
            <h2 style={{ fontSize:14, fontWeight:600, marginBottom:12 }}>Signal Interpretation</h2>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:16, fontSize:12, color:'var(--text-secondary)' }}>
              <div>
                <div style={{ fontWeight:600, color:'var(--text-primary)', marginBottom:4 }}>RSI {signal.rsi_14?.toFixed(1)}</div>
                {signal.rsi_14 == null ? <span>No data</span>
                  : signal.rsi_14 > 70 ? <span style={{ color:'var(--red)' }}>Overbought — potential reversal</span>
                  : signal.rsi_14 < 30 ? <span style={{ color:'var(--green)' }}>Oversold — potential bounce</span>
                  : <span>Neutral zone (30–70)</span>}
              </div>
              <div>
                <div style={{ fontWeight:600, color:'var(--text-primary)', marginBottom:4 }}>MACD {signal.macd?.toFixed(3)}</div>
                {signal.macd == null ? <span>No data</span>
                  : signal.macd > (signal.macd_signal ?? 0)
                    ? <span style={{ color:'var(--green)' }}>MACD above signal — bullish momentum</span>
                    : <span style={{ color:'var(--red)' }}>MACD below signal — bearish momentum</span>}
              </div>
              <div>
                <div style={{ fontWeight:600, color:'var(--text-primary)', marginBottom:4 }}>BB Position {signal.bb_position?.toFixed(3)}</div>
                {signal.bb_position == null ? <span>No data</span>
                  : signal.bb_position > 0.8 ? <span style={{ color:'var(--red)' }}>Near upper band — stretched</span>
                  : signal.bb_position < 0.2 ? <span style={{ color:'var(--green)' }}>Near lower band — potential bounce</span>
                  : <span>Mid-band — consolidating</span>}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
