import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

interface SourceRow {
  id: number
  name: string
  url: string
  rss_url: string | null
  enabled: boolean
  deleted: boolean
  article_count: number
  error_count: number
  last_error: string | null
  last_scanned_at: string | null
  credibility?: { score: number; grade: string } | null
}

const mono: React.CSSProperties = { fontFamily: 'Space Mono, monospace' }

export function Sources() {
  const [sources, setSources] = useState<SourceRow[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ name: '', url: '', rss_url: '', enabled: true })
  const [editing, setEditing] = useState<number | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    api.sources()
      .then((r: any) => setSources(r.sources ?? []))
      .catch(() => setErr('Could not reach API'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  const resetForm = () => {
    setForm({ name: '', url: '', rss_url: '', enabled: true })
    setEditing(null)
  }

  const submit = async () => {
    setErr(null)
    setMsg(null)
    if (!form.name || !form.url) {
      setErr('Name and site URL are required')
      return
    }
    try {
      if (editing != null) {
        await api.updateSource(String(editing), {
          name: form.name,
          url: form.url,
          rss_url: form.rss_url || undefined,
          enabled: form.enabled,
        })
        setMsg('Source updated')
      } else {
        await api.createSource({
          name: form.name,
          url: form.url,
          rss_url: form.rss_url || undefined,
          enabled: form.enabled,
        })
        setMsg('Source added')
      }
      resetForm()
      load()
    } catch (e: any) {
      setErr(e?.message || 'Save failed')
    }
  }

  const toggle = async (s: SourceRow) => {
    try {
      await api.updateSource(String(s.id), { enabled: !s.enabled })
      load()
    } catch (e: any) {
      setErr(e?.message || 'Update failed')
    }
  }

  const remove = async (s: SourceRow) => {
    if (!confirm(`Remove "${s.name}"? Articles are kept, fetching stops.`)) return
    try {
      await api.deleteSource(String(s.id))
      load()
    } catch (e: any) {
      setErr(e?.message || 'Remove failed')
    }
  }

  const test = async (s: SourceRow) => {
    setMsg(null)
    setErr(null)
    try {
      const r: any = await api.testSource(String(s.id))
      if (r?.ok) setMsg(`Feed OK — ${r.count} articles discovered`)
      else setErr(`Feed test failed: ${r?.error ?? 'unknown'}`)
    } catch (e: any) {
      setErr(e?.message || 'Feed test failed')
    }
  }

  const startEdit = (s: SourceRow) => {
    setEditing(s.id)
    setForm({ name: s.name, url: s.url, rss_url: s.rss_url ?? '', enabled: s.enabled })
  }

  return (
    <div style={{ padding: 16, ...mono, color: '#0a0a0a', fontSize: 12 }}>
      <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '0.04em', marginBottom: 4 }}>
        NEWS SOURCES
      </div>
      <div style={{ fontSize: 9, opacity: 0.6, marginBottom: 14, letterSpacing: '0.06em' }}>
        MANAGE RSS FEEDS — ADD, ENABLE / DISABLE, REMOVE (KEEPS ARTICLES)
      </div>

      {err && (
        <div style={{ border: '1px solid #0a0a0a', padding: '6px 8px', marginBottom: 10, background: '#e8e8e0' }}>
          {err}
        </div>
      )}
      {msg && (
        <div style={{ border: '1px solid #0a0a0a', padding: '6px 8px', marginBottom: 10 }}>{msg}</div>
      )}

      {/* Form */}
      <div
        style={{
          border: '1px solid #0a0a0a',
          padding: 10,
          marginBottom: 16,
          display: 'grid',
          gridTemplateColumns: '1fr 2fr 2fr auto auto',
          gap: 8,
          alignItems: 'center',
        }}
      >
        <input
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          style={inp}
        />
        <input
          placeholder="Site URL (https://…)"
          value={form.url}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
          style={inp}
        />
        <input
          placeholder="RSS URL (optional)"
          value={form.rss_url}
          onChange={(e) => setForm({ ...form, rss_url: e.target.value })}
          style={inp}
        />
        <label style={{ fontSize: 10, display: 'flex', gap: 4, alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          ENABLED
        </label>
        <button onClick={submit} style={btn}>
          {editing != null ? 'SAVE' : 'ADD'}
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div style={{ opacity: 0.6 }}>LOADING…</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '2px solid #0a0a0a' }}>
              <th style={th}>NAME</th>
              <th style={th}>SITE</th>
              <th style={th}>RSS</th>
              <th style={th}>ARTICLES</th>
              <th style={th}>CREDIBILITY</th>
              <th style={th}>STATUS</th>
              <th style={th}>LAST ERROR</th>
              <th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.id} style={{ borderBottom: '1px solid #0a0a0a' }}>
                <td style={td}>{s.name}</td>
                <td style={{ ...td, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.url}
                </td>
                <td style={{ ...td, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.rss_url ?? '—'}
                </td>
                <td style={td}>{s.article_count}</td>
                <td style={td}>
                  {s.credibility ? (
                    <span
                      style={{
                        border: '1px solid #0a0a0a',
                        padding: '1px 6px',
                        fontSize: 9,
                        fontWeight: 700,
                        background: credBg(s.credibility.grade),
                      }}
                    >
                      {s.credibility.grade} · {s.credibility.score}
                    </span>
                  ) : '—'}
                </td>
                <td style={td}>
                  <span
                    style={{
                      border: '1px solid #0a0a0a',
                      padding: '1px 5px',
                      fontSize: 9,
                      opacity: s.enabled && !s.deleted ? 1 : 0.5,
                    }}
                  >
                    {s.deleted ? 'REMOVED' : s.enabled ? 'ON' : 'OFF'}
                  </span>
                </td>
                <td style={{ ...td, color: s.last_error ? '#a00' : '#0a0a0a', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.last_error ?? '—'}
                </td>
                <td style={{ ...td, whiteSpace: 'nowrap' }}>
                  <button style={mini} onClick={() => toggle(s)} disabled={s.deleted}>
                    {s.enabled ? 'DISABLE' : 'ENABLE'}
                  </button>
                  <button style={mini} onClick={() => test(s)}>
                    TEST
                  </button>
                  <button style={mini} onClick={() => startEdit(s)} disabled={s.deleted}>
                    EDIT
                  </button>
                  <button style={mini} onClick={() => remove(s)}>
                    REMOVE
                  </button>
                </td>
              </tr>
            ))}
            {sources.length === 0 && (
              <tr>
                <td style={td} colSpan={8}>No sources yet — add one above.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}

const inp: React.CSSProperties = {
  fontFamily: 'Space Mono, monospace',
  fontSize: 11,
  padding: '5px 6px',
  border: '1px solid #0a0a0a',
  background: '#f5f5f0',
  color: '#0a0a0a',
}

const btn: React.CSSProperties = {
  fontFamily: 'Space Mono, monospace',
  fontSize: 10,
  padding: '6px 10px',
  border: '1px solid #0a0a0a',
  background: '#0a0a0a',
  color: '#f5f5f0',
  cursor: 'pointer',
  letterSpacing: '0.06em',
}

const mini: React.CSSProperties = {
  fontFamily: 'Space Mono, monospace',
  fontSize: 9,
  padding: '3px 6px',
  marginRight: 4,
  border: '1px solid #0a0a0a',
  background: '#f5f5f0',
  color: '#0a0a0a',
  cursor: 'pointer',
}

const th: React.CSSProperties = { padding: '5px 6px', fontSize: 9, letterSpacing: '0.06em', opacity: 0.7 }
const td: React.CSSProperties = { padding: '6px', verticalAlign: 'top' }

function credBg(grade: string): string {
  switch (grade) {
    case 'A': return '#0a0a0a'
    case 'B': return '#555550'
    case 'C': return '#888880'
    case 'D': return '#a0a090'
    default: return '#cfcfc6'
  }
}
