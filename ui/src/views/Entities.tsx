import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../lib/api'
import { Section, Card, LangBadge, SentimentChip, LoadingDots, SkelEntityCards, EmptyState } from '../components/Layout'

const LABEL_FILTERS = ['ALL', 'PER', 'ORG', 'LOC']
const LABEL_GLYPHS: Record<string, string> = { PER: '●', ORG: '■', LOC: '◆' }
const PAGE_SIZE = 20

export function EntityDrawer({ entity, onClose, onSelectNode }: { entity: any; onClose: () => void; onSelectNode?: (id: number) => void }) {
  const [dossier, setDossier] = useState<any>(null)
  const [tab, setTab] = useState<'overview' | 'articles'>('overview')
  const [watched, setWatched] = useState(false)
  const [watchBusy, setWatchBusy] = useState(false)

  useEffect(() => {
    if (!entity) return
    setDossier(null)
    setWatched(false)
    api.entityDossier(String(entity.id))
      .then((r: any) => setDossier(r))
      .catch(() => setDossier({ error: true }))
    api.watchlist()
      .then((r: any) => {
        const ids = new Set((r.items ?? []).map((i: any) => i.node_id))
        setWatched(ids.has(entity.id))
      })
      .catch(() => {})
  }, [entity?.id])

  const toggleWatch = async () => {
    setWatchBusy(true)
    try {
      if (watched) await api.removeWatchlist(entity.id)
      else await api.addWatchlist(entity.id)
      setWatched(w => !w)
    } catch {
      /* ignore */
    } finally {
      setWatchBusy(false)
    }
  }

  if (!entity) return null
  const ent = dossier?.entity ?? entity
  const sent = dossier?.sentiment_distribution ?? {}
  const langs = dossier?.language_distribution ?? {}
  const maxSent = Math.max(1, ...Object.values(sent as Record<string, number>))
  const maxLang = Math.max(1, ...Object.values(langs as Record<string, number>))

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', justifyContent: 'flex-end' }}
      onClick={onClose}
    >
      <div
        style={{ width: '100%', maxWidth: 460, height: '100%', background: '#f5f5f0', borderLeft: '2px solid #0a0a0a', boxShadow: '-6px 0 0 #0a0a0a', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ padding: '14px 16px', borderBottom: '2px solid #0a0a0a', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 8, letterSpacing: '0.15em', color: '#555550', marginBottom: 4 }}>
              {LABEL_GLYPHS[ent.label] ?? '○'} {ent.label} / ENTITY
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.2 }}>{ent.text}</div>
            {ent.aliases?.length > 0 && (
              <div style={{ fontSize: 9, color: '#555550', marginTop: 3 }}>AKA: {ent.aliases.join(', ')}</div>
            )}
            <div style={{ fontSize: 9, marginTop: 6, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <span><span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>{ent.mention_count ?? 0}</span><span style={{ color: '#555550', marginLeft: 4 }}>MENTIONS</span></span>
              {dossier?.first_seen && <span style={{ color: '#555550' }}>FIRST {dossier.first_seen.slice(0, 10)}</span>}
              {dossier?.last_seen && <span style={{ color: '#555550' }}>LAST {dossier.last_seen.slice(0, 10)}</span>}
            </div>
            {ent.wikidata_url && (
              <a href={ent.wikidata_url} target="_blank" rel="noreferrer" style={{ fontSize: 9, color: '#0a0a0a', textDecoration: 'underline', marginTop: 4, display: 'inline-block' }}>
                WIKIDATA {ent.wikidata_id}
              </a>
            )}
          </div>
          <button onClick={onClose} style={{ fontSize: 18, background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>×</button>
        </div>

        <div style={{ padding: '8px 16px', borderBottom: '1px solid #0a0a0a' }}>
          <button onClick={toggleWatch} disabled={watchBusy}
            style={{ padding: '5px 12px', border: '1px solid #0a0a0a', background: watched ? '#0a0a0a' : '#f5f5f0', color: watched ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer', fontWeight: 700 }}>
            {watched ? '★ IN WATCHLIST' : '☆ ADD TO WATCHLIST'}
          </button>
        </div>

        <div style={{ display: 'flex', borderBottom: '1px solid #0a0a0a' }}>
          {(['overview', 'articles'] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              style={{ flex: 1, padding: '8px 0', border: 'none', borderRight: t === 'overview' ? '1px solid #0a0a0a' : 'none', background: tab === t ? '#0a0a0a' : 'transparent', color: tab === t ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.12em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
              {t.toUpperCase()}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, padding: 14 }}>
          {tab === 'overview' ? (
            dossier === null ? <LoadingDots /> :
            dossier.error ? <EmptyState msg="COULD NOT LOAD DOSSIER" /> :
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {Object.keys(sent).length > 0 && (
                <div>
                  <div style={{ fontSize: 9, letterSpacing: '0.12em', color: '#555550', marginBottom: 6 }}>SENTIMENT MIX</div>
                  {Object.entries(sent as Record<string, number>).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 8, width: 52, textTransform: 'uppercase' }}>{k.slice(0, 3)}</span>
                      <div style={{ flex: 1, height: 8, background: '#d4d4cc' }}>
                        <div style={{ height: '100%', width: `${(v / maxSent) * 100}%`, background: '#0a0a0a' }} />
                      </div>
                      <span style={{ fontSize: 9, fontVariantNumeric: 'tabular-nums', width: 28, textAlign: 'right' }}>{v}</span>
                    </div>
                  ))}
                </div>
              )}
              {Object.keys(langs).length > 0 && (
                <div>
                  <div style={{ fontSize: 9, letterSpacing: '0.12em', color: '#555550', marginBottom: 6 }}>LANGUAGE MIX</div>
                  {Object.entries(langs as Record<string, number>).map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 8, width: 52, textTransform: 'uppercase' }}>{k}</span>
                      <div style={{ flex: 1, height: 8, background: '#d4d4cc' }}>
                        <div style={{ height: '100%', width: `${(v / maxLang) * 100}%`, background: '#555550' }} />
                      </div>
                      <span style={{ fontSize: 9, fontVariantNumeric: 'tabular-nums', width: 28, textAlign: 'right' }}>{v}</span>
                    </div>
                  ))}
                </div>
              )}
              {dossier.related_entities?.length > 0 && (
                <div>
                  <div style={{ fontSize: 9, letterSpacing: '0.12em', color: '#555550', marginBottom: 6 }}>RELATED ENTITIES</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {dossier.related_entities.map((r: any) => (
                      <button key={r.node_id} onClick={() => onSelectNode?.(r.node_id)}
                        style={{ fontSize: 9, padding: '3px 8px', border: '1px solid #0a0a0a', background: '#efefea', cursor: 'pointer', fontFamily: 'Space Mono, monospace' }}>
                        {LABEL_GLYPHS[r.label] ?? '○'} {r.text}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            dossier === null ? <LoadingDots /> :
            (dossier.recent_articles ?? []).length === 0 ? <EmptyState msg="NO ARTICLES FOUND" /> :
            (dossier.recent_articles ?? []).map((a: any, i: number) => (
              <div key={a.id} style={{ padding: '10px 0', borderBottom: '1px solid #d4d4cc' }}>
                <a href={a.url} target="_blank" rel="noreferrer" style={{ fontSize: 11, fontWeight: 600, color: '#0a0a0a', textDecoration: 'none', display: 'block', marginBottom: 4 }}>{a.title}</a>
                <div style={{ display: 'flex', gap: 6 }}>
                  {a.language && <LangBadge lang={a.language} />}
                  {a.sentiment_label && <SentimentChip label={a.sentiment_label} />}
                  <span style={{ fontSize: 8, color: '#555550', marginLeft: 'auto' }}>{a.published_date?.slice(0, 10)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export function Entities() {
  const [label, setLabel] = useState('ALL')
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [nodes, setNodes] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(false)
  const debounceTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const acRef = useRef<AbortController | null>(null)

  useEffect(() => {
    clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => setDebouncedQ(q), 300)
    return () => clearTimeout(debounceTimer.current)
  }, [q])

  useEffect(() => {
    acRef.current?.abort()
    acRef.current = new AbortController()
    const ac = acRef.current
    setLoading(true)
    setError(false)
    setOffset(0)
    const opts: any = { limit: PAGE_SIZE, offset: 0 }
    if (label !== 'ALL') opts.label = label
    if (debouncedQ) opts.q = debouncedQ
    api.entities(opts)
      .then((r: any) => { if (!ac.signal.aborted) { setNodes(r.nodes ?? []); setTotal(r.total ?? 0); setLoading(false) } })
      .catch(() => { if (!ac.signal.aborted) { setNodes([]); setTotal(0); setError(true); setLoading(false) } })
    return () => ac.abort()
  }, [label, debouncedQ])

  const handleLoadMore = useCallback(() => {
    const nextOffset = offset + PAGE_SIZE
    setLoadingMore(true)
    const opts: any = { limit: PAGE_SIZE, offset: nextOffset }
    if (label !== 'ALL') opts.label = label
    if (debouncedQ) opts.q = debouncedQ
    api.entities(opts)
      .then((r: any) => { setNodes(prev => [...prev, ...(r.nodes ?? [])]); setOffset(nextOffset); setLoadingMore(false) })
      .catch(() => setLoadingMore(false))
  }, [offset, label, debouncedQ])

  const maxMentions = Math.max(...nodes.map((n: any) => n.mention_count), 1)

  return (
    <div>
      <Section title="ENTITY DIRECTORY" sub={`SHOWING ${nodes.length} OF ${total}`}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 0, border: '1px solid #0a0a0a' }}>
            {LABEL_FILTERS.map((l, i) => (
              <button key={l} onClick={() => setLabel(l)}
                style={{ padding: '5px 12px', border: 'none', borderRight: i < LABEL_FILTERS.length - 1 ? '1px solid #0a0a0a' : 'none', background: label === l ? '#0a0a0a' : 'transparent', color: label === l ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
                {l === 'ALL' ? l : `${LABEL_GLYPHS[l]} ${l}`}
              </button>
            ))}
          </div>
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="FILTER BY NAME..."
            style={{ padding: '5px 10px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 9, letterSpacing: '0.06em', fontFamily: 'Space Mono, monospace', outline: 'none' }} />
        </div>

        {loading ? <SkelEntityCards count={8} /> : error ? <EmptyState msg="COULD NOT REACH API — CHECK BACKEND CONNECTION" /> : nodes.length === 0 ? <EmptyState msg="NO ENTITIES FOUND" /> : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
              {nodes.map((n: any) => {
                const barPct = (n.mention_count / maxMentions) * 100
                return (
                  <button key={n.id} onClick={() => setSelected(n)}
                    style={{ background: '#efefea', border: '1px solid #0a0a0a', boxShadow: '2px 2px 0 #0a0a0a', padding: '10px 12px', cursor: 'pointer', textAlign: 'left', fontFamily: 'Space Mono, monospace', transition: 'transform 0.1s' }}
                    onMouseEnter={e => (e.currentTarget.style.transform = 'translate(-1px,-1px)')}
                    onMouseLeave={e => (e.currentTarget.style.transform = '')}>
                    <div style={{ fontSize: 8, color: '#555550', marginBottom: 4, letterSpacing: '0.1em' }}>{LABEL_GLYPHS[n.label] ?? '○'} {n.label}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6, lineHeight: 1.2 }}>{n.text}</div>
                    <div style={{ height: 4, background: '#d4d4cc', marginBottom: 4 }}>
                      <div style={{ height: '100%', width: `${barPct}%`, background: '#0a0a0a' }} />
                    </div>
                    <div style={{ fontSize: 9, color: '#555550' }}>
                      <span style={{ fontWeight: 700, color: '#0a0a0a', fontVariantNumeric: 'tabular-nums' }}>{n.mention_count}</span> MENTIONS
                    </div>
                  </button>
                )
              })}
            </div>

            {nodes.length < total && (
              <div style={{ marginTop: 16, textAlign: 'center' }}>
                <button onClick={handleLoadMore} disabled={loadingMore}
                  style={{ padding: '7px 20px', border: '1px solid #0a0a0a', background: loadingMore ? '#d4d4cc' : '#0a0a0a', color: loadingMore ? '#555550' : '#f5f5f0', fontSize: 9, letterSpacing: '0.14em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: loadingMore ? 'not-allowed' : 'pointer' }}>
                  {loadingMore ? 'LOADING_' : `LOAD MORE (${total - nodes.length} REMAINING)`}
                </button>
              </div>
            )}
          </>
        )}
      </Section>

      {selected && <EntityDrawer entity={selected} onClose={() => setSelected(null)} onSelectNode={(id) => setSelected({ id })} />}
    </div>
  )
}
