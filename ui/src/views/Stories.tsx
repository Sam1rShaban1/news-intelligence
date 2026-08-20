import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Section, Card, SentimentChip, LangBadge, LoadingDots, SkelStoryCards, EmptyState } from '../components/Layout'

const DAYS_OPTIONS = [3, 7, 14, 30]

function StoryDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const [story, setStory] = useState<any>(null)
  const [error, setError] = useState(false)
  const [timeline, setTimeline] = useState<any>(null)
  const [timelineErr, setTimelineErr] = useState(false)

  useEffect(() => {
    setStory(null)
    setError(false)
    api.story(id)
      .then(setStory)
      .catch(() => setError(true))
  }, [id])

  useEffect(() => {
    setTimeline(null)
    setTimelineErr(false)
    api.storyTimeline(id)
      .then(setTimeline)
      .catch(() => setTimelineErr(true))
  }, [id])

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 100, background: 'rgba(245,245,240,0.92)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: 24, overflowY: 'auto' }}
      onClick={onClose}
    >
      <div
        style={{ background: '#f5f5f0', border: '2px solid #0a0a0a', boxShadow: '6px 6px 0 #0a0a0a', maxWidth: 680, width: '100%', padding: 0 }}
        onClick={e => e.stopPropagation()}
      >
        {!story && !error ? <LoadingDots /> : error ? (
          <div style={{ padding: 24 }}>
            <EmptyState msg="COULD NOT LOAD STORY — CHECK BACKEND CONNECTION" />
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <button onClick={onClose} style={{ padding: '5px 14px', border: '1px solid #0a0a0a', background: '#0a0a0a', color: '#f5f5f0', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer' }}>CLOSE</button>
            </div>
          </div>
        ) : (
          <>
            <div style={{ padding: '16px 20px', borderBottom: '2px solid #0a0a0a', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 8, letterSpacing: '0.15em', color: '#555550', marginBottom: 6 }}>▤ STORY / EVENT CLUSTER</div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 8px', lineHeight: 1.3 }}>{story.title}</h2>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <SentimentChip label={story.dominant_sentiment} />
                  <span style={{ fontSize: 9, color: '#555550' }}>{story.member_count} ARTICLES</span>
                  {story.first_seen && <span style={{ fontSize: 9, color: '#555550' }}>{story.first_seen.slice(0, 10)} → {story.last_seen?.slice(0, 10)}</span>}
                </div>
              </div>
              <a href={api.storyPdfUrl(String(story.id))} target="_blank" rel="noreferrer"
                style={{ fontSize: 9, padding: '3px 10px', border: '1px solid #0a0a0a', background: '#f5f5f0', letterSpacing: '0.1em', color: '#0a0a0a', textDecoration: 'none', cursor: 'pointer', fontWeight: 700 }}>
                PDF
              </a>
              <a href={api.exportStoryUrl(String(story.id), 'csv')} target="_blank" rel="noreferrer"
                style={{ fontSize: 9, padding: '3px 10px', border: '1px solid #0a0a0a', background: '#f5f5f0', letterSpacing: '0.1em', color: '#0a0a0a', textDecoration: 'none', cursor: 'pointer', fontWeight: 700 }}>
                CSV
              </a>
              <a href={api.exportStoryUrl(String(story.id), 'json')} target="_blank" rel="noreferrer"
                style={{ fontSize: 9, padding: '3px 10px', border: '1px solid #0a0a0a', background: '#f5f5f0', letterSpacing: '0.1em', color: '#0a0a0a', textDecoration: 'none', cursor: 'pointer', fontWeight: 700 }}>
                JSON
              </a>
              <button onClick={onClose} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
            </div>
            <div>
              {story.members?.length === 0 ? <EmptyState msg="NO MEMBER ARTICLES" /> :
               story.members?.map((m: any, i: number) => (
                <div key={m.id} style={{ padding: '12px 20px', borderBottom: i < story.members.length - 1 ? '1px solid #d4d4cc' : 'none' }}>
                  <a href={m.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, fontWeight: 700, color: '#0a0a0a', textDecoration: 'none', display: 'block', marginBottom: 4 }}>{m.title}</a>
                  {m.summary && <p style={{ fontSize: 10, color: '#555550', margin: '0 0 6px', lineHeight: 1.5 }}>{m.summary}</p>}
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    {m.source && <span style={{ fontSize: 8, color: '#555550' }}>{m.source}</span>}
                    {m.language && <LangBadge lang={m.language} />}
                    {m.sentiment_label && <SentimentChip label={m.sentiment_label} />}
                    <span style={{ fontSize: 8, color: '#aaa', marginLeft: 'auto' }}>{m.discovered_at?.slice(0, 10)}</span>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ borderTop: '2px solid #0a0a0a', marginTop: 14, padding: '16px 20px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', marginBottom: 10 }}>TIMELINE</div>
              {timelineErr ? <EmptyState msg="COULD NOT LOAD TIMELINE" /> : !timeline ? <LoadingDots /> : (
                <>
                  {timeline.timeline?.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6, height: 90, marginBottom: 12 }}>
                      {timeline.timeline.map((t: any) => {
                        const max = Math.max(1, ...timeline.timeline.map((x: any) => x.count))
                        const h = Math.round((t.count / max) * 80)
                        const neg = t.neg > t.pos
                        return (
                          <div key={t.date} title={`${t.date}: ${t.count} articles`}
                            style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: 3 }}>
                            <span style={{ fontSize: 8, fontVariantNumeric: 'tabular-nums' }}>{t.count}</span>
                            <div style={{ width: '100%', height: h, background: neg ? '#555550' : '#0a0a0a' }} />
                            <span style={{ fontSize: 7, color: '#555550', transform: 'rotate(-45deg)', whiteSpace: 'nowrap' }}>{t.date?.slice(5)}</span>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  {timeline.articles?.length > 0 && (
                    <div>
                      {timeline.articles.map((a: any, i: number) => (
                        <div key={a.id} style={{ padding: '8px 0', borderBottom: i < timeline.articles.length - 1 ? '1px solid #d4d4cc' : 'none', display: 'flex', gap: 8, alignItems: 'center' }}>
                          <span style={{ fontSize: 8, color: '#555550', width: 64, flexShrink: 0 }}>{a.published_date?.slice(0, 10) ?? a.discovered_at?.slice(0, 10)}</span>
                          <a href={a.url} target="_blank" rel="noreferrer" style={{ flex: 1, fontSize: 11, fontWeight: 600, color: '#0a0a0a', textDecoration: 'none' }}>{a.title}</a>
                          {a.sentiment_label && <SentimentChip label={a.sentiment_label} />}
                          {a.language && <LangBadge lang={a.language} />}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export function Stories() {
  const [days, setDays] = useState(7)
  const [sentFilter, setSentFilter] = useState('')
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    setData(null)
    setError(false)
    const opts: any = { days, limit: 20 }
    if (sentFilter) opts.sentiment = sentFilter
    api.stories(opts)
      .then(d => { setData(d); setError(false) })
      .catch(() => setError(true))
  }, [days, sentFilter])

  const stories = data?.stories ?? []

  const maxDays = Math.max(1, ...stories.map((s: any) =>
    s.first_seen && s.last_seen
      ? Math.round((new Date(s.last_seen).getTime() - new Date(s.first_seen).getTime()) / 86400000)
      : 1
  ))

  return (
    <div>
      <Section title="STORY CLUSTERS" sub={data ? `${data.total} DETECTED` : ''}>
        <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'flex', border: '1px solid #0a0a0a' }}>
            {DAYS_OPTIONS.map((d, i) => (
              <button key={d} onClick={() => setDays(d)}
                style={{ padding: '4px 10px', border: 'none', borderRight: i < DAYS_OPTIONS.length - 1 ? '1px solid #0a0a0a' : 'none', background: days === d ? '#0a0a0a' : 'transparent', color: days === d ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
                {d}D
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', border: '1px solid #0a0a0a' }}>
            {(['', 'positive', 'neutral', 'negative'] as const).map((s, i) => (
              <button key={s} onClick={() => setSentFilter(s)}
                style={{ padding: '4px 10px', border: 'none', borderRight: i < 3 ? '1px solid #0a0a0a' : 'none', background: sentFilter === s ? '#0a0a0a' : 'transparent', color: sentFilter === s ? '#f5f5f0' : '#0a0a0a', fontSize: 9, letterSpacing: '0.08em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
                {s === '' ? 'ALL' : s.toUpperCase().slice(0, 3)}
              </button>
            ))}
          </div>
        </div>

        {!data && !error ? <SkelStoryCards count={6} /> : error ? <EmptyState msg="COULD NOT REACH API — CHECK BACKEND CONNECTION" /> : stories.length === 0 ? <EmptyState msg="NO STORIES IN RANGE" /> : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {stories.map((s: any) => {
              const totalDays = s.first_seen && s.last_seen
                ? Math.max(1, Math.round((new Date(s.last_seen).getTime() - new Date(s.first_seen).getTime()) / 86400000))
                : 1
              return (
                <button key={s.id} onClick={() => setSelectedId(s.id)}
                  style={{ background: '#efefea', border: '1px solid #0a0a0a', boxShadow: '3px 3px 0 #0a0a0a', padding: '14px', cursor: 'pointer', textAlign: 'left', fontFamily: 'Space Mono, monospace', transition: 'transform 0.1s' }}
                  onMouseEnter={e => (e.currentTarget.style.transform = 'translate(-2px,-2px)')}
                  onMouseLeave={e => (e.currentTarget.style.transform = '')}>
                  <div style={{ display: 'flex', gap: 6, marginBottom: 6, alignItems: 'center' }}>
                    <SentimentChip label={s.dominant_sentiment} />
                    {s.language && <LangBadge lang={s.language} />}
                    <span style={{ fontSize: 8, color: '#555550', marginLeft: 'auto' }}>{s.member_count} ART.</span>
                  </div>
                  <h3 style={{ fontSize: 12, fontWeight: 700, margin: '0 0 6px', lineHeight: 1.4 }}>{s.title}</h3>
                  {s.summary && (
                    <p style={{ fontSize: 10, color: '#555550', margin: '0 0 8px', lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{s.summary}</p>
                  )}
                  {s.top_entities?.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
                      {s.top_entities.slice(0, 4).map((e: any) => (
                        <span key={e.id} style={{ fontSize: 8, padding: '1px 5px', background: '#d4d4cc', border: '1px solid #0a0a0a' }}>{e.text}</span>
                      ))}
                    </div>
                  )}
                  <div style={{ fontSize: 8, color: '#555550', marginBottom: 4 }}>
                    {s.first_seen?.slice(0, 10)} → {s.last_seen?.slice(0, 10)} · {totalDays}D
                  </div>
                  <div style={{ height: 3, background: '#d4d4cc' }}>
                    <div style={{ height: '100%', width: `${Math.round((totalDays / maxDays) * 100)}%`, background: 'repeating-linear-gradient(90deg, #0a0a0a, #0a0a0a 2px, transparent 2px, transparent 4px)' }} />
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </Section>

      {selectedId && <StoryDetail id={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  )
}
