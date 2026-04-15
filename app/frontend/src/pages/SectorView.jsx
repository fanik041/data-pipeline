// What this file does: Sectors page — grid of sectors; click to see all symbols + signals.
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { api } from '../api.js'
import { ChevronRight, TrendingUp, TrendingDown } from 'lucide-react'

const SECTOR_ACCENT = [
  '#3B82F6','#10B981','#F59E0B','#EF4444','#8B5CF6',
  '#EC4899','#14B8A6','#F97316','#6366F1','#84CC16',
]

const ALL_SECTORS = [
  'Technology','Financial Services','Communication Services',
  'Consumer Cyclical','Healthcare','Industrials',
  'Energy','Utilities','Real Estate','Basic Materials','Consumer Defensive',
]

function SectorCard({ sector, accent, onClick, isSelected }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: isSelected ? `${accent}18` : 'var(--bg-surface)',
        border: `1px solid ${isSelected ? accent : 'var(--border)'}`,
        borderRadius: 10,
        padding: '16px 18px',
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'all 180ms ease',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: isSelected ? `0 0 16px ${accent}28` : 'none',
      }}
      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.borderColor = accent }}
      onMouseLeave={e => { if (!isSelected) e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      <div>
        <div style={{ width:10, height:10, borderRadius:'50%', background:accent, marginBottom:8 }} />
        <div style={{ fontSize:13, fontWeight:600, color:'var(--text-primary)' }}>{sector}</div>
      </div>
      <ChevronRight size={15} color={isSelected ? accent : 'var(--text-muted)'} />
    </button>
  )
}

export default function SectorView() {
  const { backend } = useAuth()
  const [selected, setSelected]   = useState(null)
  const [symbols,  setSymbols]    = useState([])
  const [loading,  setLoading]    = useState(false)
  const [error,    setError]      = useState(null)

  async function loadSector(sector) {
    if (selected === sector) { setSelected(null); setSymbols([]); return }
    setSelected(sector)
    setLoading(true)
    setError(null)
    try {
      const data = await api.sector(sector, backend)
      setSymbols(data)
    } catch (err) {
      setError(err.message)
      setSymbols([])
    } finally {
      setLoading(false)
    }
  }

  // Reset on backend switch
  useEffect(() => { setSelected(null); setSymbols([]) }, [backend])

  const bullish = symbols.filter(s => s.target_next_day_up === 1).length
  const bearish = symbols.filter(s => s.target_next_day_up === 0).length

  return (
    <div style={{ padding:'28px 32px', maxWidth:1100 }}>
      <div style={{ marginBottom:24 }}>
        <h1 style={{ fontSize:22, fontWeight:700 }}>Sector View</h1>
        <p style={{ fontSize:13, color:'var(--text-secondary)', marginTop:2 }}>
          Click a sector to see the latest ML signal for each symbol · <span className="mono" style={{ color:'var(--blue)' }}>{backend.toUpperCase()}</span>
        </p>
      </div>

      {/* Sector grid */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(200px, 1fr))', gap:12, marginBottom:28 }}>
        {ALL_SECTORS.map((sector, i) => (
          <SectorCard
            key={sector}
            sector={sector}
            accent={SECTOR_ACCENT[i % SECTOR_ACCENT.length]}
            isSelected={selected === sector}
            onClick={() => loadSector(sector)}
          />
        ))}
      </div>

      {/* Sector detail */}
      {selected && (
        <div className="card fade-up">
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:20, flexWrap:'wrap', gap:12 }}>
            <div>
              <h2 style={{ fontSize:16, fontWeight:700 }}>{selected}</h2>
              <p style={{ fontSize:13, color:'var(--text-secondary)', marginTop:2 }}>
                Latest prediction signal per symbol
              </p>
            </div>
            {!loading && symbols.length > 0 && (
              <div style={{ display:'flex', gap:12 }}>
                <span className="badge badge-green"><TrendingUp size={11} /> {bullish} Bullish</span>
                <span className="badge badge-red"><TrendingDown size={11} /> {bearish} Bearish</span>
              </div>
            )}
          </div>

          {loading && (
            <div style={{ display:'flex', alignItems:'center', gap:10, color:'var(--text-muted)', padding:24 }}>
              <div className="spinner" /> Loading {selected} symbols…
            </div>
          )}
          {error && !loading && (
            <div style={{ color:'var(--red)', fontSize:13, padding:'12px 16px', background:'var(--red-glow)', borderRadius:8 }}>
              ⚠ {error}
            </div>
          )}
          {!loading && !error && symbols.length === 0 && (
            <div style={{ color:'var(--text-muted)', fontSize:13, padding:16 }}>
              No active symbols found for this sector.
            </div>
          )}
          {!loading && !error && symbols.length > 0 && (
            <div style={{ overflowX:'auto' }}>
              <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
                <thead>
                  <tr style={{ borderBottom:'1px solid var(--border)' }}>
                    {['Symbol','Company','Signal Date','RSI-14','Signal'].map(h => (
                      <th key={h} style={{
                        textAlign: h==='RSI-14'||h==='Signal' ? 'right' : 'left',
                        padding:'8px 14px', fontSize:11, color:'var(--text-muted)',
                        fontWeight:600, letterSpacing:'.06em', whiteSpace:'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {symbols.map(sym => (
                    <tr key={sym.symbol} style={{ borderBottom:'1px solid var(--border)' }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-elevated)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                      <td style={{ padding:'10px 14px', fontFamily:'var(--font-mono)', fontWeight:700, color:'var(--blue)' }}>{sym.symbol}</td>
                      <td style={{ padding:'10px 14px', color:'var(--text-secondary)' }}>{sym.company_name}</td>
                      <td style={{ padding:'10px 14px', fontFamily:'var(--font-mono)', fontSize:12, color:'var(--text-muted)' }}>{sym.date}</td>
                      <td style={{ padding:'10px 14px', fontFamily:'var(--font-mono)', textAlign:'right' }}>
                        {sym.rsi_14 != null ? sym.rsi_14.toFixed(1) : '—'}
                      </td>
                      <td style={{ padding:'10px 14px', textAlign:'right' }}>
                        <span className={`badge ${sym.target_next_day_up === 1 ? 'badge-green' : 'badge-red'}`}>
                          {sym.target_next_day_up === 1
                            ? <><TrendingUp size={10}/> BUY</>
                            : <><TrendingDown size={10}/> SELL</>}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
