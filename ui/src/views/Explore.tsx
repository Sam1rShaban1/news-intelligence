import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../lib/api'
import { Section, Card, SentimentChip, LangBadge, SkelArticleRows, EmptyState } from '../components/Layout'

const LANGS = ['mk', 'sq', 'en', 'tr']
const SENTIMENTS = ['positive', 'neutral', 'negative']
const SORTS = [{ v: 'rank', l: 'RELEVANCE' }, { v: 'recent', l: 'RECENT' }]

export function Explore({ initialQuery }: { initialQuery: string }) {
  const [q, setQ] = useState(initialQuery)
  const [lang, setLang] = useState<string[]>([])
  const [sentiment, setSentiment] = useState('')
  const [sort, setSort] = useState('rank')
  const [page, setPage] = useState(0)
  const [results, setResults] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const acRef = useRef<AbortController | null>(null)

  const limit = 10

  const doSearch = useCallback((overrides?: any) => {
    acRef.current?.abort()
    acRef.current = new AbortController()
    const ac = acRef.current
    setLoading(true)
    setError(false)
    const opts = {
      q: q || undefined,
      language: lang.length ? lang.join(',') : undefined,
      sentiment: sentiment || undefined,
      sort,
      limit,
      offset: page * limit,
      ...overrides,
    }
    api.search(opts)
      .then(r => { if (!ac.signal.aborted) { setResults(r); setLoading(false) } })
      .catch(() => { if (!ac.signal.aborted) { setResults(null); setError(true); setLoading(false) } })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, lang, sentiment, sort, page, limit])

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => { setPage(0); doSearch({ offset: 0 }) }, 350)
    return () => clearTimeout(timer.current)
  }, [q, lang, sentiment, sort])

  useEffect(() => { doSearch() }, [page])

  useEffect(() => { setQ(initialQuery) }, [initialQuery])

  const toggleLang = (l: string) =>
    setLang(prev => prev.includes(l) ? prev.filter(x => x !== l) : [...prev, l])

  return (
    <div>
      <Section title="ARTICLE EXPLORER" sub={results?.total ? `${results.total.toLocaleString()} RESULTS` : ''}>
        <Card style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 180 }}>
              <span style={{ position: 'absolute', left: 7, top: '50%', transform: 'translateY(-50%)', fontSize: 11 }}>⌕</span>
              <input
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="QUERY..."
                style={{ width: '100%', padding: '5px 8px 5px 22px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 10, letterSpacing: '0.06em', fontFamily: 'Space Mono, monospace', outline: 'none' }}
              />
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {LANGS.map(l => (
                <button key={l} onClick={() => toggleLang(l)}
                  style={{ padding: '3px 8px', border: '1px solid #0a0a0a', background: lang.includes(l) ? '#0a0a0a' : '#f5f5f0', color: lang.includes(l) ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer', fontWeight: 700 }}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
            <select value={sentiment} onChange={e => setSentiment(e.target.value)}
              style={{ padding: '4px 8px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 9, letterSpacing: '0.08em', fontFamily: 'Space Mono, monospace', cursor: 'pointer' }}>
              <option value="">ALL SENTIMENT</option>
              {SENTIMENTS.map(s => <option key={s} value={s}>{s.toUpperCase()}</option>)}
            </select>
            <div style={{ display: 'flex', gap: 4 }}>
              {SORTS.map(s => (
                <button key={s.v} onClick={() => setSort(s.v)}
                  style={{ padding: '3px 8px', border: '1px solid #0a0a0a', background: sort === s.v ? '#0a0a0a' : 'transparent', color: sort === s.v ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.08em', fontFamily: 'Space Mono, monospace', cursor: 'pointer' }}>
                  {s.l}
                </button>
              ))}
            </div>
          </div>
        </Card>

        {loading ? <SkelArticleRows count={6} /> : error ? (
          <EmptyState msg="COULD NOT REACH API — CHECK BACKEND CONNECTION" />
        ) : !results ? null : (
          <>
            <Card style={{ padding: 0 }}>
              {results.results?.length ? results.results.map((r: any, i: number) => (
                <div key={r.id} style={{ padding: '12px 14px', borderBottom: i < results.results.length - 1 ? '1px solid #d4d4cc' : 'none' }}>
                  <a href={r.url} target="_blank" rel="noreferrer"
                    style={{ fontSize: 13, fontWeight: 700, color: '#0a0a0a', textDecoration: 'none', lineHeight: 1.3, display: 'block', marginBottom: 5 }}>
                    {r.title}
                  </a>
                  {r.summary && <p style={{ fontSize: 10, color: '#555550', margin: '0 0 6px', lineHeight: 1.5 }}>{r.summary}</p>}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                    {r.source_name && <span style={{ fontSize: 9, color: '#555550' }}>{r.source_name}</span>}
                    {r.language && <LangBadge lang={r.language} />}
                    {r.sentiment_label && <SentimentChip label={r.sentiment_label} />}
                    {r.published_date && <span style={{ fontSize: 8, color: '#aaa' }}>{r.published_date.slice(0, 10)}</span>}
                    {r.entities?.length > 0 && (
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginLeft: 4 }}>
                        {r.entities.slice(0, 5).map((e: any, ei: number) => (
                          <span key={ei} style={{ fontSize: 8, padding: '1px 5px', background: '#d4d4cc', border: '1px solid #0a0a0a', letterSpacing: '0.06em' }}>
                            {e.text}
                          </span>
                        ))}
                      </div>
                    )}
                    {r.rank != null && (
                      <span style={{ marginLeft: 'auto', fontSize: 8, color: '#555550' }}>RANK {(r.rank * 100).toFixed(0)}</span>
                    )}
                  </div>
                </div>
              )) : <EmptyState msg="NO RESULTS — TRY DIFFERENT TERMS" />}
            </Card>

            {results.total > limit && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, fontSize: 10 }}>
                <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
                  style={{ padding: '4px 12px', border: '1px solid #0a0a0a', background: page === 0 ? '#d4d4cc' : '#0a0a0a', color: page === 0 ? '#555550' : '#f5f5f0', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: page === 0 ? 'not-allowed' : 'pointer' }}>
                  ◀ PREV
                </button>
                <span style={{ letterSpacing: '0.1em', color: '#555550' }}>
                  PAGE {page + 1} / {Math.ceil(results.total / limit)}
                </span>
                <button disabled={(page + 1) * limit >= results.total} onClick={() => setPage(p => p + 1)}
                  style={{ padding: '4px 12px', border: '1px solid #0a0a0a', background: (page + 1) * limit >= results.total ? '#d4d4cc' : '#0a0a0a', color: (page + 1) * limit >= results.total ? '#555550' : '#f5f5f0', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: (page + 1) * limit >= results.total ? 'not-allowed' : 'pointer' }}>
                  NEXT ▶
                </button>
              </div>
            )}
          </>
        )}
      </Section>
    </div>
  )
}
