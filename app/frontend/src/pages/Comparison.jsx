// What this file does: DB Comparison page — runs the same query on Azure SQL AND Snowflake
//                      in parallel, shows response times side by side. This is the migration
//                      payoff story: Snowflake (OLAP) should outperform Azure SQL (OLTP)
//                      on analytical queries at scale.
// INTERVIEW POINT: "I built a comparison tab that hits both backends simultaneously and
//   renders the timing delta — that's how we quantify the migration payoff."
import { useState } from 'react'
import { compareBackends, api } from '../api.js'
import { GitCompare, Zap, Clock, CheckCircle, XCircle } from 'lucide-react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, CartesianGrid } from 'recharts'

const QUERIES = [
  { id: 'symbols',  label: 'List All Symbols',    desc: 'ref.symbols JOIN ref.sectors', fn: (b) => api.symbols(b) },
  { id: 'predict',  label: 'Predict AAPL',         desc: 'v_latest_features WHERE symbol=AAPL', fn: (b) => api.predict('AAPL', b) },
  { id: 'prices',   label: 'AAPL Prices (14d)',    desc: 'v_daily_prices_enriched WHERE …', fn: (b) => api.prices('AAPL', b) },
  { id: 'sector',   label: 'Technology Sector',    desc: 'v_latest_features WHERE sector=Technology', fn: (b) => api.sector('Technology', b) },
]

function TimingBar({ azureMs, snowflakeMs }) {
  if (!azureMs || !snowflakeMs) return null
  const max = Math.max(azureMs, snowflakeMs)
  return (
    <div style={{ marginTop:16 }}>
      <ResponsiveContainer width="100%" height={80}>
        <BarChart
          layout="vertical"
          data={[
            { name:'Azure SQL', ms:azureMs,     fill:'#3B82F6' },
            { name:'Snowflake', ms:snowflakeMs, fill:'#06B6D4' },
          ]}
          margin={{ left:0, right:40, top:0, bottom:0 }}
        >
          <XAxis type="number" tick={{ fontSize:10, fill:'var(--text-muted)' }} tickFormatter={v => `${v}ms`} domain={[0, Math.ceil(max * 1.2)]} />
          <YAxis type="category" dataKey="name" tick={{ fontSize:11, fill:'var(--text-secondary)', fontFamily:'var(--font-mono)' }} width={80} />
          <Tooltip formatter={(v) => [`${v} ms`, 'Latency']} contentStyle={{ background:'var(--bg-elevated)', border:'1px solid var(--border)', fontSize:12 }} />
          <Bar dataKey="ms" radius={[0,4,4,0]}>
            {[{ fill:'#3B82F6' },{ fill:'#06B6D4' }].map((entry, i) => (
              <Cell key={i} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function ResultCard({ query, result }) {
  if (!result) return null
  const { azure, snowflake } = result
  const winner = azure.ms != null && snowflake.ms != null
    ? azure.ms < snowflake.ms ? 'azure' : 'snowflake'
    : null
  const delta = azure.ms != null && snowflake.ms != null
    ? Math.abs(azure.ms - snowflake.ms)
    : null

  return (
    <div className="card fade-up" style={{ marginBottom:20 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:16, flexWrap:'wrap', gap:8 }}>
        <div>
          <h3 style={{ fontSize:15, fontWeight:600 }}>{query.label}</h3>
          <div style={{ fontSize:11, color:'var(--text-muted)', fontFamily:'var(--font-mono)', marginTop:3 }}>{query.desc}</div>
        </div>
        {delta != null && winner && (
          <div style={{
            padding:'4px 12px', borderRadius:20, fontSize:12, fontWeight:600,
            background: winner === 'snowflake' ? 'var(--green-glow)' : 'var(--blue-muted)',
            color: winner === 'snowflake' ? 'var(--green)' : 'var(--blue)',
            border: `1px solid ${winner === 'snowflake' ? 'rgba(16,185,129,.3)' : 'var(--blue-glow)'}`,
          }}>
            {winner === 'snowflake' ? '❄ Snowflake faster' : '☁ Azure faster'} by {delta}ms
          </div>
        )}
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
        {/* Azure */}
        <div style={{
          padding:'14px 16px', borderRadius:8,
          background: winner === 'azure' ? 'var(--blue-muted)' : 'var(--bg-elevated)',
          border: `1px solid ${winner === 'azure' ? 'var(--blue)' : 'var(--border)'}`,
        }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
            <div style={{ width:8, height:8, borderRadius:'50%', background:'#3B82F6' }} />
            <span style={{ fontSize:12, fontWeight:600, color:'var(--text-secondary)' }}>AZURE SQL</span>
            {winner === 'azure' && <Zap size={12} color="var(--blue)" />}
          </div>
          {azure.error ? (
            <div style={{ display:'flex', alignItems:'center', gap:6, color:'var(--red)', fontSize:13 }}>
              <XCircle size={14} /> {azure.error}
            </div>
          ) : (
            <>
              <div style={{ fontFamily:'var(--font-mono)', fontSize:24, fontWeight:700, color: winner==='azure' ? 'var(--blue)' : 'var(--text-primary)' }}>
                {azure.ms}<span style={{ fontSize:14, color:'var(--text-muted)', marginLeft:4 }}>ms</span>
              </div>
              <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:4 }}>
                {Array.isArray(azure.data) ? `${azure.data.length} rows` : '1 row'} · OLTP source
              </div>
            </>
          )}
        </div>

        {/* Snowflake */}
        <div style={{
          padding:'14px 16px', borderRadius:8,
          background: winner === 'snowflake' ? 'rgba(6,182,212,.08)' : 'var(--bg-elevated)',
          border: `1px solid ${winner === 'snowflake' ? '#06B6D4' : 'var(--border)'}`,
        }}>
          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
            <div style={{ width:8, height:8, borderRadius:'50%', background:'#06B6D4' }} />
            <span style={{ fontSize:12, fontWeight:600, color:'var(--text-secondary)' }}>SNOWFLAKE</span>
            {winner === 'snowflake' && <Zap size={12} color="#06B6D4" />}
          </div>
          {snowflake.error ? (
            <div style={{ display:'flex', alignItems:'center', gap:6, color:'var(--red)', fontSize:13 }}>
              <XCircle size={14} /> {snowflake.error}
            </div>
          ) : (
            <>
              <div style={{ fontFamily:'var(--font-mono)', fontSize:24, fontWeight:700, color: winner==='snowflake' ? '#06B6D4' : 'var(--text-primary)' }}>
                {snowflake.ms}<span style={{ fontSize:14, color:'var(--text-muted)', marginLeft:4 }}>ms</span>
              </div>
              <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:4 }}>
                {Array.isArray(snowflake.data) ? `${snowflake.data.length} rows` : '1 row'} · OLAP target
              </div>
            </>
          )}
        </div>
      </div>

      <TimingBar azureMs={azure.ms} snowflakeMs={snowflake.ms} />
    </div>
  )
}

export default function Comparison() {
  const [results, setResults]   = useState({})
  const [running, setRunning]   = useState({})
  const [runAll,  setRunAll]    = useState(false)

  async function runQuery(query) {
    setRunning(r => ({ ...r, [query.id]: true }))
    try {
      const result = await compareBackends(query.fn)
      setResults(r => ({ ...r, [query.id]: result }))
    } finally {
      setRunning(r => ({ ...r, [query.id]: false }))
    }
  }

  async function runAllQueries() {
    setRunAll(true)
    await Promise.allSettled(QUERIES.map(q => runQuery(q)))
    setRunAll(false)
  }

  return (
    <div style={{ padding:'28px 32px', maxWidth:900 }}>
      <div style={{ marginBottom:24 }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6 }}>
          <GitCompare size={20} color="var(--blue)" />
          <h1 style={{ fontSize:22, fontWeight:700 }}>DB Comparison</h1>
        </div>
        <p style={{ fontSize:13, color:'var(--text-secondary)' }}>
          Runs the same query against Azure SQL (OLTP) and Snowflake (OLAP) simultaneously.
          Shows end-to-end latency including network + query execution — the migration payoff story.
        </p>
      </div>

      {/* Architecture callout */}
      <div style={{
        padding:'14px 18px', borderRadius:10,
        background:'var(--amber-glow)', border:'1px solid rgba(245,158,11,.25)',
        marginBottom:24, fontSize:13, color:'var(--text-secondary)',
        display:'flex', gap:12, alignItems:'flex-start',
      }}>
        <span style={{ color:'var(--amber)', fontSize:16, flexShrink:0 }}>ℹ</span>
        <div>
          <strong style={{ color:'var(--amber)' }}>Interview Talking Point:</strong> Azure SQL uses row-level scans on normalised OLTP tables.
          Snowflake uses micro-partition pruning on columnar OLAP data — the same query returns faster
          as data volume grows. This page demonstrates that delta in real time.
        </div>
      </div>

      {/* Query buttons */}
      <div style={{ display:'flex', gap:10, marginBottom:24, flexWrap:'wrap' }}>
        <button className="btn btn-primary" onClick={runAllQueries} disabled={runAll}>
          {runAll ? <><span className="spinner" /> Running all…</> : <><Zap size={14} /> Run All Queries</>}
        </button>
        {QUERIES.map(q => (
          <button key={q.id} className="btn btn-ghost" onClick={() => runQuery(q)} disabled={running[q.id]}>
            {running[q.id] ? <span className="spinner" /> : <Clock size={13} />}
            {q.label}
          </button>
        ))}
      </div>

      {/* Results */}
      {QUERIES.map(q => results[q.id] && (
        <ResultCard key={q.id} query={q} result={results[q.id]} />
      ))}

      {Object.keys(results).length === 0 && (
        <div style={{ color:'var(--text-muted)', fontSize:14, padding:'40px 0', textAlign:'center' }}>
          Run a query above to compare Azure SQL vs Snowflake response times.
        </div>
      )}
    </div>
  )
}
