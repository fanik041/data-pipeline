// What this file does: Market Data page — symbol selector, date range, price chart + table.
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { api } from '../api.js'
import { Search, Calendar } from 'lucide-react'
import {
  ResponsiveContainer, ComposedChart, Area, Bar, XAxis, YAxis,
  Tooltip, CartesianGrid, Legend
} from 'recharts'

const TODAY = new Date().toISOString().split('T')[0]
const TWO_WEEKS_AGO = new Date(Date.now() - 14 * 86400000).toISOString().split('T')[0]

const SYMBOLS = ['AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','JPM','JNJ','V',
  'WMT','PG','XOM','BAC','HD','CVX','KO','ABBV','PFE','MRK']

function PriceTip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  return (
    <div style={{ background:'var(--bg-elevated)', border:'1px solid var(--border)', borderRadius:8, padding:'10px 14px', fontSize:12 }}>
      <div style={{ color:'var(--text-muted)', marginBottom:6 }}>{d?.date}</div>
      {[
        ['Open',  d?.open,   'var(--text-primary)'],
        ['High',  d?.high,   'var(--green)'],
        ['Low',   d?.low,    'var(--red)'],
        ['Close', d?.close,  'var(--blue)'],
      ].map(([k, v, c]) => (
        <div key={k} style={{ display:'flex', justifyContent:'space-between', gap:16, color:c }}>
          <span style={{ color:'var(--text-muted)' }}>{k}</span>
          <span className="mono">{v != null ? `$${Number(v).toFixed(2)}` : '—'}</span>
        </div>
      ))}
      <div style={{ display:'flex', justifyContent:'space-between', gap:16, marginTop:4, color:'var(--amber)' }}>
        <span style={{ color:'var(--text-muted)' }}>Volume</span>
        <span className="mono">{d?.volume != null ? Number(d.volume).toLocaleString() : '—'}</span>
      </div>
    </div>
  )
}

export default function MarketData() {
  const { backend } = useAuth()
  const [symbol, setSymbol]   = useState('AAPL')
  const [input,  setInput]    = useState('AAPL')
  const [start,  setStart]    = useState(TWO_WEEKS_AGO)
  const [end,    setEnd]      = useState(TODAY)
  const [prices, setPrices]   = useState([])
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  async function load(sym, s, e) {
    setLoading(true)
    setError(null)
    try {
      const data = await api.prices(sym, backend, s, e)
      // Recharts needs ascending date order
      setPrices([...data].reverse())
    } catch (err) {
      setError(err.message)
      setPrices([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(symbol, start, end) }, [symbol, backend, start, end])

  function handleSearch(e) {
    e.preventDefault()
    const sym = input.trim().toUpperCase()
    if (sym) { setSymbol(sym); setInput(sym) }
  }

  const change = prices.length >= 2
    ? prices[prices.length - 1].close - prices[0].close
    : null
  const changePct = prices.length >= 2 && prices[0].close
    ? (change / prices[0].close) * 100
    : null

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Market Data</h1>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
          OHLCV price history · <span className="mono" style={{ color:'var(--blue)' }}>{backend.toUpperCase()}</span>
        </p>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {/* Symbol search */}
        <div>
          <label style={{ display:'block', fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em', marginBottom:6 }}>SYMBOL</label>
          <form onSubmit={handleSearch} style={{ display:'flex', gap:6 }}>
            <input
              className="input"
              value={input}
              onChange={e => setInput(e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
              style={{ width: 120, fontFamily:'var(--font-mono)', fontWeight:600 }}
            />
            <button type="submit" className="btn btn-primary" style={{ padding:'8px 12px' }}>
              <Search size={14} />
            </button>
          </form>
        </div>
        {/* Quick pick */}
        <div>
          <label style={{ display:'block', fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em', marginBottom:6 }}>QUICK PICK</label>
          <select className="select" value={symbol} onChange={e => { setSymbol(e.target.value); setInput(e.target.value) }} style={{ fontFamily:'var(--font-mono)' }}>
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        {/* Date range */}
        <div>
          <label style={{ display:'block', fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em', marginBottom:6 }}>FROM</label>
          <input className="input" type="date" value={start} onChange={e => setStart(e.target.value)} style={{ width:160 }} />
        </div>
        <div>
          <label style={{ display:'block', fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em', marginBottom:6 }}>TO</label>
          <input className="input" type="date" value={end} onChange={e => setEnd(e.target.value)} style={{ width:160 }} />
        </div>
      </div>

      {/* Stats strip */}
      {prices.length > 0 && (
        <div style={{
          display:'flex', gap:24, padding:'12px 20px', marginBottom:20,
          background:'var(--bg-surface)', borderRadius:10, border:'1px solid var(--border)',
          flexWrap:'wrap',
        }}>
          <div>
            <div style={{ fontSize:11, color:'var(--text-muted)', letterSpacing:'.06em' }}>SYMBOL</div>
            <div style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:18, color:'var(--blue)' }}>{symbol}</div>
          </div>
          <div>
            <div style={{ fontSize:11, color:'var(--text-muted)', letterSpacing:'.06em' }}>LATEST CLOSE</div>
            <div style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:18 }}>
              ${prices[prices.length - 1]?.close?.toFixed(2)}
            </div>
          </div>
          {change != null && (
            <div>
              <div style={{ fontSize:11, color:'var(--text-muted)', letterSpacing:'.06em' }}>PERIOD CHANGE</div>
              <div style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:18, color: change >= 0 ? 'var(--green)' : 'var(--red)' }}>
                {change >= 0 ? '+' : ''}{change.toFixed(2)} ({changePct?.toFixed(2)}%)
              </div>
            </div>
          )}
          <div>
            <div style={{ fontSize:11, color:'var(--text-muted)', letterSpacing:'.06em' }}>DATA POINTS</div>
            <div style={{ fontFamily:'var(--font-mono)', fontWeight:700, fontSize:18 }}>{prices.length}</div>
          </div>
          <div>
            <div style={{ fontSize:11, color:'var(--text-muted)', letterSpacing:'.06em' }}>DATE RANGE</div>
            <div style={{ fontFamily:'var(--font-mono)', fontSize:13, marginTop:4 }}>
              {prices[0]?.date} → {prices[prices.length-1]?.date}
            </div>
          </div>
        </div>
      )}

      {/* Chart */}
      <div className="card" style={{ marginBottom: 20 }}>
        {loading && (
          <div style={{ display:'flex', alignItems:'center', gap:10, color:'var(--text-muted)', height:300, justifyContent:'center' }}>
            <div className="spinner" /> Loading {symbol} prices…
          </div>
        )}
        {error && !loading && (
          <div style={{ color:'var(--red)', padding:32, textAlign:'center' }}>
            ⚠ {error}
          </div>
        )}
        {!loading && !error && prices.length > 0 && (
          <>
            <div style={{ marginBottom:16, display:'flex', justifyContent:'space-between' }}>
              <h2 style={{ fontSize:14, fontWeight:600 }}>{symbol} — Close Price & Volume</h2>
              <div style={{ fontSize:12, color:'var(--text-muted)' }}>{backend === 'azure' ? 'reports.v_daily_prices_enriched' : 'CMIA_DW.MARTS.V_PRICES_ENRICHED'}</div>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={prices} margin={{ left: 0, right: 10 }}>
                <defs>
                  <linearGradient id="closeGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#3B82F6" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#3B82F6" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize:10, fill:'var(--text-muted)', fontFamily:'var(--font-mono)' }}
                  axisLine={false} tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="price"
                  tick={{ fontSize:10, fill:'var(--text-muted)', fontFamily:'var(--font-mono)' }}
                  axisLine={false} tickLine={false}
                  tickFormatter={v => `$${v.toFixed(0)}`}
                  domain={['auto', 'auto']}
                  width={60}
                />
                <YAxis
                  yAxisId="vol"
                  orientation="right"
                  tick={{ fontSize:10, fill:'var(--text-muted)', fontFamily:'var(--font-mono)' }}
                  axisLine={false} tickLine={false}
                  tickFormatter={v => `${(v/1e6).toFixed(0)}M`}
                  width={50}
                />
                <Tooltip content={<PriceTip />} />
                <Bar yAxisId="vol" dataKey="volume" fill="var(--amber)" opacity={0.25} radius={[2,2,0,0]} name="Volume" />
                <Area yAxisId="price" type="monotone" dataKey="close" stroke="var(--blue)" strokeWidth={2}
                  fill="url(#closeGrad)" dot={false} name="Close" activeDot={{ r:4, fill:'var(--blue)' }} />
              </ComposedChart>
            </ResponsiveContainer>
          </>
        )}
        {!loading && !error && prices.length === 0 && (
          <div style={{ height:300, display:'flex', alignItems:'center', justifyContent:'center', color:'var(--text-muted)' }}>
            No data found for {symbol} in this date range.
          </div>
        )}
      </div>

      {/* Data table */}
      {prices.length > 0 && (
        <div className="card">
          <h2 style={{ fontSize:14, fontWeight:600, marginBottom:16 }}>Raw Data</h2>
          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
              <thead>
                <tr style={{ borderBottom:'1px solid var(--border)' }}>
                  {['Date','Open','High','Low','Close','Volume'].map(h => (
                    <th key={h} style={{ textAlign: h==='Date'?'left':'right', padding:'8px 12px', fontSize:11, color:'var(--text-muted)', fontWeight:600, letterSpacing:'.06em', whiteSpace:'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...prices].reverse().slice(0, 30).map((p, i) => (
                  <tr key={i} style={{ borderBottom:'1px solid var(--border)' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-surface)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ padding:'8px 12px', fontFamily:'var(--font-mono)' }}>{p.date}</td>
                    <td style={{ padding:'8px 12px', fontFamily:'var(--font-mono)', textAlign:'right' }}>${Number(p.open).toFixed(2)}</td>
                    <td style={{ padding:'8px 12px', fontFamily:'var(--font-mono)', textAlign:'right', color:'var(--green)' }}>${Number(p.high).toFixed(2)}</td>
                    <td style={{ padding:'8px 12px', fontFamily:'var(--font-mono)', textAlign:'right', color:'var(--red)' }}>${Number(p.low).toFixed(2)}</td>
                    <td style={{ padding:'8px 12px', fontFamily:'var(--font-mono)', textAlign:'right', color:'var(--blue)', fontWeight:600 }}>${Number(p.close).toFixed(2)}</td>
                    <td style={{ padding:'8px 12px', fontFamily:'var(--font-mono)', textAlign:'right', color:'var(--amber)' }}>{Number(p.volume).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
