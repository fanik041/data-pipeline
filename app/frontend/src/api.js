// =============================================================================
// FILE: src/api.js
// What this file does: Typed API client — all HTTP calls to the FastAPI backend.
// Which services: FastAPI on localhost:8000 (proxied via /api in dev via vite.config.js)
// Tech layer: Frontend data layer — all components import from here, never use fetch directly
// =============================================================================

// In dev: Vite proxies /api → localhost:8000 (see vite.config.js)
// In production: VITE_API_URL is set in Azure Static Web Apps → Configuration
const BASE = import.meta.env.VITE_API_URL ?? '/api'

function authHeaders() {
  const token = localStorage.getItem('cmia_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function get(path, params = {}) {
  const qs = new URLSearchParams(params).toString()
  const url = `${BASE}${path}${qs ? '?' + qs : ''}`
  const res = await fetch(url, { headers: authHeaders() })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw Object.assign(new Error(err?.detail?.error || 'Request failed'), { status: res.status, detail: err.detail })
  }
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw Object.assign(new Error(err?.detail?.error || 'Request failed'), { status: res.status, detail: err.detail })
  }
  return res.json()
}

// Timing wrapper — returns { data, ms }
async function timed(fn) {
  const t0 = performance.now()
  const data = await fn()
  return { data, ms: Math.round(performance.now() - t0) }
}

// Auth
export const auth = {
  login: (username, password) => post('/auth/login', { username, password }),
}

// Market data
export const api = {
  health:   (backend)              => get('/health',            { backend }),
  symbols:  (backend)              => get('/symbols',           { backend }),
  prices:   (symbol, backend, start, end) =>
    get(`/prices/${symbol}`, { backend, ...(start && { start }), ...(end && { end }) }),
  predict:  (symbol, backend)      => get(`/predict/${symbol}`, { backend }),
  sector:   (sector, backend)      => get(`/sector/${encodeURIComponent(sector)}`, { backend }),
  summary:  (symbol, backend)      => get(`/summary/${symbol}`, { backend }),
}

// Comparison helper — runs same query on both backends in parallel, returns timing
export async function compareBackends(queryFn) {
  const [azure, snowflake] = await Promise.allSettled([
    timed(() => queryFn('azure')),
    timed(() => queryFn('snowflake')),
  ])
  return {
    azure:     azure.status === 'fulfilled'    ? azure.value    : { data: null, ms: null, error: azure.reason?.message },
    snowflake: snowflake.status === 'fulfilled' ? snowflake.value : { data: null, ms: null, error: snowflake.reason?.message },
  }
}
