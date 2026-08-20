import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'
import { Section, Card, EmptyState, SentimentChip, LangBadge } from '../components/Layout'

const LANGS = ['mk', 'sq', 'en', 'tr']

export function Alerts() {
  const [rules, setRules] = useState<any[] | null>(null)
  const [alerts, setAlerts] = useState<any | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  // new-rule form
  const [name, setName] = useState('')
  const [query, setQuery] = useState('')
  const [entityId, setEntityId] = useState('')
  const [langs, setLangs] = useState<string[]>([])
  const [minSent, setMinSent] = useState('')
  const [busy, setBusy] = useState(false)
  const [formErr, setFormErr] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setErr('')
    Promise.all([
      api.alertRules().catch(e => { setErr(String(e.message || e)); return [] }),
      api.alerts({ limit: 50 }).catch(() => null),
    ])
      .then(([rs, al]) => {
        setRules(rs as any[])
        setAlerts(al)
        setLoading(false)
      })
      .catch(() => { setErr('COULD NOT LOAD ALERTS'); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  const toggleLang = (l: string) =>
    setLangs(prev => prev.includes(l) ? prev.filter(x => x !== l) : [...prev, l])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormErr('')
    if (!name.trim()) { setFormErr('NAME IS REQUIRED'); return }
    if (!query.trim() && !entityId.trim()) { setFormErr('PROVIDE A KEYWORD QUERY OR ENTITY ID'); return }
    setBusy(true)
    try {
      await api.createAlertRule({
        name: name.trim(),
        query: query.trim() || undefined,
        entity_node_id: entityId.trim() ? Number(entityId) : undefined,
        languages: langs.length ? langs : undefined,
        min_sentiment: minSent.trim() ? Number(minSent) : undefined,
      })
      setName(''); setQuery(''); setEntityId(''); setLangs([]); setMinSent('')
      load()
    } catch (e: any) {
      setFormErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  const del = async (id: number) => {
    await api.deleteAlertRule(id).catch(() => {})
    load()
  }

  const markRead = async (id: number) => {
    await api.markAlertRead(id).catch(() => {})
    load()
  }

  const markAll = async () => {
    await api.markAllAlertsRead().catch(() => {})
    load()
  }

  const unread = alerts?.alerts?.filter((a: any) => !a.read).length ?? 0

  return (
    <div>
      <Section title="ALERTS" sub={unread ? `${unread} UNREAD` : 'UP TO DATE'}>
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', marginBottom: 10 }}>NEW ALERT RULE</div>
          <form onSubmit={submit}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
              <label style={{ flex: '1 1 160px', fontSize: 8, letterSpacing: '0.12em', color: '#555550' }}>
                NAME
                <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Corruption watch"
                  style={{ width: '100%', marginTop: 3, padding: '5px 8px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 10, fontFamily: 'Space Mono, monospace', outline: 'none' }} />
              </label>
              <label style={{ flex: '1 1 160px', fontSize: 8, letterSpacing: '0.12em', color: '#555550' }}>
                KEYWORD QUERY
                <input value={query} onChange={e => setQuery(e.target.value)} placeholder="corruption, minister..."
                  style={{ width: '100%', marginTop: 3, padding: '5px 8px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 10, fontFamily: 'Space Mono, monospace', outline: 'none' }} />
              </label>
              <label style={{ flex: '1 1 120px', fontSize: 8, letterSpacing: '0.12em', color: '#555550' }}>
                ENTITY NODE ID
                <input value={entityId} onChange={e => setEntityId(e.target.value)} placeholder="optional"
                  style={{ width: '100%', marginTop: 3, padding: '5px 8px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 10, fontFamily: 'Space Mono, monospace', outline: 'none' }} />
              </label>
              <label style={{ flex: '1 1 90px', fontSize: 8, letterSpacing: '0.12em', color: '#555550' }}>
                MIN SENTIMENT
                <input value={minSent} onChange={e => setMinSent(e.target.value)} placeholder="-1 .. 1"
                  style={{ width: '100%', marginTop: 3, padding: '5px 8px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 10, fontFamily: 'Space Mono, monospace', outline: 'none' }} />
              </label>
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 8, letterSpacing: '0.12em', color: '#555550', marginRight: 4 }}>LANGS</span>
              {LANGS.map(l => (
                <button type="button" key={l} onClick={() => toggleLang(l)}
                  style={{ padding: '2px 7px', border: '1px solid #0a0a0a', background: langs.includes(l) ? '#0a0a0a' : '#f5f5f0', color: langs.includes(l) ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer', fontWeight: 700 }}>
                  {l.toUpperCase()}
                </button>
              ))}
              <button type="submit" disabled={busy}
                style={{ marginLeft: 'auto', padding: '5px 16px', border: '1px solid #0a0a0a', background: '#0a0a0a', color: '#f5f5f0', fontSize: 9, letterSpacing: '0.12em', fontFamily: 'Space Mono, monospace', cursor: 'pointer', fontWeight: 700 }}>
                {busy ? 'SAVING…' : 'CREATE RULE'}
              </button>
            </div>
            {formErr && <div style={{ marginTop: 8, fontSize: 9, color: '#a00', letterSpacing: '0.08em' }}>⚠ {formErr}</div>}
          </form>
        </Card>

        {err && <EmptyState msg={err} />}

        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', margin: '4px 0 8px' }}>
          RULES ({rules?.length ?? 0})
        </div>
        {loading ? (
          <EmptyState msg="LOADING…" />
        ) : !rules || rules.length === 0 ? (
          <EmptyState msg="NO ALERT RULES YET" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 18 }}>
            {rules!.map((r: any) => (
              <Card key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 700 }}>{r.name}</div>
                  <div style={{ fontSize: 8, color: '#555550', letterSpacing: '0.08em', marginTop: 2 }}>
                    {r.query ? `“${r.query}”` : r.entity_node_id ? `ENTITY #${r.entity_node_id}` : 'any'}
                    {r.languages?.length ? ` · ${r.languages.join(',')}` : ''}
                    {r.min_sentiment != null ? ` · sent≥${r.min_sentiment}` : ''}
                    {r.last_checked_at ? ` · checked ${new Date(r.last_checked_at).toLocaleString()}` : ''}
                  </div>
                </div>
                <button onClick={() => del(r.id)}
                  style={{ padding: '3px 10px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer' }}>
                  DELETE
                </button>
              </Card>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', margin: '8px 0' }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em' }}>FIRED ALERTS ({alerts?.total ?? 0})</div>
          {unread > 0 && (
            <button onClick={markAll}
              style={{ padding: '3px 12px', border: '1px solid #0a0a0a', background: '#0a0a0a', color: '#f5f5f0', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer' }}>
              MARK ALL READ
            </button>
          )}
        </div>
        {!alerts || !alerts.alerts || alerts.alerts.length === 0 ? (
          <EmptyState msg="NO ALERTS FIRED" />
        ) : (
          <Card style={{ padding: 0 }}>
            {alerts.alerts.map((a: any, i: number) => (
              <div key={a.id} style={{ padding: '10px 12px', borderBottom: i < alerts.alerts.length - 1 ? '1px solid #d4d4cc' : 'none', display: 'flex', gap: 10, alignItems: 'center', background: a.read ? 'transparent' : '#d4d4cc' }}>
                <div style={{ flex: 1 }}>
                  <a href={a.article?.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, fontWeight: 700, color: '#0a0a0a', textDecoration: 'none' }}>{a.article?.title}</a>
                  <div style={{ fontSize: 8, color: '#555550', letterSpacing: '0.08em', marginTop: 2 }}>
                    RULE: {a.rule?.name}
                    {a.article?.source_name ? ` · ${a.article.source_name}` : ''}
                    {a.article?.language ? ` · ${a.article.language}` : ''}
                  </div>
                </div>
                {a.article?.sentiment_label && <SentimentChip label={a.article.sentiment_label} />}
                {a.article?.language && <LangBadge lang={a.article.language} />}
                {!a.read && (
                  <button onClick={() => markRead(a.id)}
                    style={{ padding: '3px 10px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer' }}>
                    READ
                  </button>
                )}
              </div>
            ))}
          </Card>
        )}
      </Section>
    </div>
  )
}
