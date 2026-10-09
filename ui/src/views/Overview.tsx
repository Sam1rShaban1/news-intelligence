import { useEffect, useState, useMemo } from 'react'
import { api } from '../lib/api'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Legend, Tooltip,
  type ChartConfig,
} from '../components/dither-kit'
import {
  Section, Card, KpiTile, SentimentChip, LangBadge,
  SkelKpiRow, SkelChartArea, SkelArticleRows, EmptyState,
} from '../components/Layout'
import type { View } from '../components/Layout'

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
function shortDate(iso?: string): string {
  if (!iso) return ''
  const m = Number(iso.slice(5, 7)) - 1
  const d = Number(iso.slice(8, 10))
  if (Number.isNaN(m) || Number.isNaN(d)) return iso.slice(0, 10)
  return `${MONTHS[m]} ${d}`
}

// 0 = all time (see /analytics/overview?days=0)
const DAYS_OPTIONS = [0, 7, 30, 90, 365]
const INTERVAL_OPTIONS = ['day', 'week', 'month'] as const

function daysLabel(d: number): string {
  return d === 0 ? 'ALL' : `${d}D`
}

/** Pick a bucket size that keeps the chart readable for the chosen window. */
function autoInterval(d: number): typeof INTERVAL_OPTIONS[number] {
  if (d === 0 || d > 180) return 'month'
  if (d > 30) return 'week'
  return 'day'
}

const segBtn = (active: boolean) => ({
  padding: '4px 10px',
  border: 'none',
  background: active ? '#0a0a0a' : 'transparent',
  color: active ? '#f5f5f0' : '#0a0a0a',
  fontSize: 9,
  letterSpacing: '0.1em',
  fontFamily: 'Space Mono, monospace',
  fontWeight: 700,
  cursor: 'pointer',
} as const)

export function Overview({ search: _search, onNav }: { search: string; onNav?: (v: View) => void }) {
  const [days, setDays] = useState(0)
  const [interval, setInterval] = useState<typeof INTERVAL_OPTIONS[number]>('month')
  const [data, setData] = useState<any>(null)
  const [dataError, setDataError] = useState(false)
  const [recentArticles, setRecentArticles] = useState<any[] | null>(null)
  const [articleStats, setArticleStats] = useState<{ total: number; analyzed: number } | null>(null)
  const [watchlist, setWatchlist] = useState<any[] | null>(null)
  const [alerts, setAlerts] = useState<any>(null)

  // Time-series panel — refetches whenever the window or bucket size changes.
  useEffect(() => {
    const ac = new AbortController()
    setData(null)
    api.overview({ days, interval })
      .then(d => { if (!ac.signal.aborted) { setData(d); setDataError(false) } })
      .catch(() => { if (!ac.signal.aborted) setDataError(true) })
    return () => ac.abort()
  }, [days, interval])

  // Everything else is window-independent — fetched once.
  useEffect(() => {
    const ac = new AbortController()
    api.search({ sort: 'recent', limit: 6 })
      .then((r: any) => { if (!ac.signal.aborted) setRecentArticles(r.results ?? []) })
      .catch(() => { if (!ac.signal.aborted) setRecentArticles([]) })
    Promise.all([
      api.articles({ limit: 1 }),
      api.articles({ status: 'analyzed', limit: 1 }),
    ]).then(([all, done]: any) => {
      if (!ac.signal.aborted) setArticleStats({ total: all.total ?? 0, analyzed: done.total ?? 0 })
    }).catch(() => { if (!ac.signal.aborted) setArticleStats(null) })
    api.watchlist().then((r: any) => { if (!ac.signal.aborted) setWatchlist(r.items ?? []) }).catch(() => {})
    api.alerts({ limit: 5 }).then((r: any) => { if (!ac.signal.aborted) setAlerts(r) }).catch(() => {})
    return () => ac.abort()
  }, [])

  const sentConfig: ChartConfig = {
    positive: { label: 'Positive', color: 'green' },
    neutral:  { label: 'Neutral',  color: 'blue' },
    negative: { label: 'Negative', color: 'red' },
  }

  const langConfig: ChartConfig = {
    mk: { label: 'MK', color: 'blue' },
    sq: { label: 'SQ', color: 'orange' },
    en: { label: 'EN', color: 'purple' },
    tr: { label: 'TR', color: 'pink' },
  }

  const sentData = useMemo(() =>
    (data?.sentiment_over_time ?? []).map((r: any) => ({
      date: shortDate(r.bucket),
      positive: r.pos ?? 0,
      negative: r.neg ?? 0,
      neutral: r.neutral ?? 0,
    })), [data])

  const langData = useMemo(() =>
    (data?.language_mix ?? []).map((r: any) => ({
      date: shortDate(r.bucket),
      mk: r.mk ?? 0, sq: r.sq ?? 0, en: r.en ?? 0, tr: r.tr ?? 0,
    })), [data])

  const trending = useMemo(() => data?.trending_entities ?? [], [data])

  const { totalPos, totalNeg, totalNeu, totalSent } = useMemo(() => {
    const pos = sentData.reduce((s: number, r: any) => s + r.positive, 0)
    const neg = sentData.reduce((s: number, r: any) => s + r.negative, 0)
    const neu = sentData.reduce((s: number, r: any) => s + r.neutral, 0)
    return { totalPos: pos, totalNeg: neg, totalNeu: neu, totalSent: pos + neg + neu || 1 }
  }, [sentData])

  return (
    <div>
      <Section
        title="SITUATION REPORT"
        sub={`AS OF ${new Date().toISOString().slice(0, 10)}`}
      >
        <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 8, color: '#555550', letterSpacing: '0.1em' }}>WINDOW</span>
          <div style={{ display: 'flex', border: '1px solid #0a0a0a' }}>
            {DAYS_OPTIONS.map((d, i) => (
              <button
                key={d}
                onClick={() => { setDays(d); setInterval(autoInterval(d)) }}
                style={{ ...segBtn(days === d), borderRight: i < DAYS_OPTIONS.length - 1 ? '1px solid #0a0a0a' : 'none' }}
              >
                {daysLabel(d)}
              </button>
            ))}
          </div>
          <span style={{ fontSize: 8, color: '#555550', letterSpacing: '0.1em' }}>BUCKET</span>
          <div style={{ display: 'flex', border: '1px solid #0a0a0a' }}>
            {INTERVAL_OPTIONS.map((iv, i) => (
              <button
                key={iv}
                onClick={() => setInterval(iv)}
                style={{ ...segBtn(interval === iv), borderRight: i < INTERVAL_OPTIONS.length - 1 ? '1px solid #0a0a0a' : 'none' }}
              >
                {iv.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        {!data && !dataError ? (
          <SkelKpiRow count={6} />
        ) : dataError ? (
          <EmptyState msg="COULD NOT REACH API — CHECK BACKEND CONNECTION" />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
            <KpiTile
              label="ARTICLES"
              value={articleStats ? articleStats.total.toLocaleString() : '—'}
              sub={articleStats
                ? `${articleStats.analyzed.toLocaleString()} ANALYZED · ${Math.max(0, articleStats.total - articleStats.analyzed).toLocaleString()} IN PIPELINE`
                : 'TOTAL / PROCESSED'}
            />
            <KpiTile label={`ARTICLES (${daysLabel(days)})`} value={(totalPos + totalNeg + totalNeu).toLocaleString()} sub="SENTIMENT TRACKED" />
            <KpiTile label="POSITIVE" value={`${Math.round(totalPos / totalSent * 100)}%`} sub={`${totalPos} ARTICLES`} />
            <KpiTile label="NEUTRAL" value={`${Math.round(totalNeu / totalSent * 100)}%`} sub={`${totalNeu} ARTICLES`} />
            <KpiTile label="NEGATIVE" value={`${Math.round(totalNeg / totalSent * 100)}%`} sub={`${totalNeg} ARTICLES`} />
            <KpiTile label="ENTITIES" value={trending.length > 0 ? `${trending.length}+` : '—'} sub="TRENDING" />
            <KpiTile label="INTERVAL" value={(data.interval ?? '—').toUpperCase()} sub={`${days === 0 ? 'ALL TIME' : `${data.days}D WINDOW`}`} />
          </div>
        )}
      </Section>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Section title="SENTIMENT OVER TIME" sub={`${daysLabel(days)} WINDOW · ${(data?.interval ?? interval).toUpperCase()}`}>
          <Card>
            {!data && !dataError ? <SkelChartArea height={176} /> : sentData.length === 0 ? <EmptyState msg="NO DATA" /> : (
              <AreaChart data={sentData} config={sentConfig} bloom="off" className="h-44">
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip labelKey="date" />
                <Legend />
                <Area dataKey="negative" variant="solid" />
                <Area dataKey="positive" variant="hatched" />
                <Area dataKey="neutral" variant="dotted" />
              </AreaChart>
            )}
          </Card>
        </Section>

        <Section title="LANGUAGE MIX" sub={`${daysLabel(days)} WINDOW · ${(data?.interval ?? interval).toUpperCase()}`}>
          <Card>
            {!data && !dataError ? <SkelChartArea height={176} /> : langData.length === 0 ? <EmptyState msg="NO DATA" /> : (
              <BarChart data={langData} config={langConfig} bloom="off" className="h-44">
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip labelKey="date" />
                <Legend />
                <Bar dataKey="mk" variant="solid" />
                <Bar dataKey="sq" variant="hatched" />
                <Bar dataKey="en" variant="dotted" />
                <Bar dataKey="tr" variant="gradient" />
              </BarChart>
            )}
          </Card>
        </Section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Section title="TRENDING ENTITIES" sub="TOP 10 BY MENTION">
          <Card style={{ padding: 0 }}>
            {!data && !dataError ? <SkelArticleRows count={6} /> : trending.length === 0 ? <EmptyState msg="NO TRENDING ENTITIES" /> : (
              trending.slice(0, 10).map((e: any, i: number) => (
                <div
                  key={i}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 14px',
                    borderBottom: i < Math.min(trending.length, 10) - 1 ? '1px solid #d4d4cc' : 'none',
                  }}
                >
                  <span style={{ fontSize: 9, color: '#555550', width: 16, fontVariantNumeric: 'tabular-nums' }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span style={{ flex: 1, fontSize: 11, fontWeight: 700 }}>{e.text}</span>
                  <span style={{ fontSize: 8, padding: '1px 4px', border: '1px solid #0a0a0a', letterSpacing: '0.1em', color: '#555550' }}>
                    {e.label}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 700, fontVariantNumeric: 'tabular-nums', width: 32, textAlign: 'right' }}>
                    {e.mentions}
                  </span>
                </div>
              ))
            )}
          </Card>
        </Section>

        <Section title="RECENT ARTICLES" sub="LATEST FROM PIPELINE">
          <Card style={{ padding: 0 }}>
            {recentArticles === null ? <SkelArticleRows count={5} /> :
             recentArticles.length === 0 ? <EmptyState msg="NO ARTICLES" /> :
             recentArticles.map((a: any, i: number) => (
              <a
                key={a.id}
                href={a.url && a.url !== '#' ? a.url : undefined}
                target="_blank"
                rel="noreferrer"
                style={{ display: 'block', padding: '9px 14px', borderBottom: i < recentArticles.length - 1 ? '1px solid #d4d4cc' : 'none', textDecoration: 'none', color: 'inherit' }}
              >
                <div style={{ fontSize: 11, fontWeight: 700, lineHeight: 1.3, marginBottom: 4 }}>{a.title}</div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  {a.source_name && <span style={{ fontSize: 8, color: '#555550', letterSpacing: '0.06em' }}>{a.source_name}</span>}
                  {a.language && <LangBadge lang={a.language} />}
                  {a.sentiment_label && <SentimentChip label={a.sentiment_label} />}
                  <span style={{ marginLeft: 'auto', fontSize: 8, color: '#555550' }}>{a.published_date?.slice(0, 10)}</span>
                </div>
              </a>
            ))}
          </Card>
        </Section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Section title="WATCHLIST" sub="MONITORED ENTITIES" onAction={onNav ? { label: 'OPEN', onClick: () => onNav('watchlist') } : undefined}>
          <Card style={{ padding: 0 }}>
            {watchlist === null ? <SkelArticleRows count={4} /> :
             watchlist.length === 0 ? <EmptyState msg="NO WATCHED ENTITIES — ADD FROM ENTITIES" /> :
             watchlist.slice(0, 6).map((w: any, i: number) => (
               <button key={w.id} onClick={() => onNav?.('watchlist')}
                 style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '8px 14px', border: 'none', borderBottom: i < Math.min(watchlist.length, 6) - 1 ? '1px solid #d4d4cc' : 'none', background: 'none', cursor: 'pointer', textAlign: 'left' }}>
                 <span style={{ fontSize: 9, color: '#555550', width: 16, fontVariantNumeric: 'tabular-nums' }}>{String(i + 1).padStart(2, '0')}</span>
                 <span style={{ flex: 1, fontSize: 11, fontWeight: 700 }}>{w.entity_text}</span>
                 <span style={{ fontSize: 8, padding: '1px 4px', border: '1px solid #0a0a0a', letterSpacing: '0.1em', color: '#555550' }}>{w.entity_label}</span>
                 {w.last_mentioned && <span style={{ fontSize: 8, color: '#555550', width: 48, textAlign: 'right' }}>{w.last_mentioned.slice(0, 10)}</span>}
               </button>
             ))}
          </Card>
        </Section>

        <Section title="ALERTS" sub="UNREAD / RECENT" onAction={onNav ? { label: 'OPEN', onClick: () => onNav('alerts') } : undefined}>
          <Card style={{ padding: 0 }}>
            {alerts === null ? <SkelArticleRows count={4} /> :
             (alerts.alerts?.length ?? 0) > 0 ? (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderBottom: '1px solid #d4d4cc' }}>
                  <span style={{ fontSize: 11, fontWeight: 700 }}>{alerts.alerts.filter((a: any) => !a.read).length} UNREAD</span>
                  <span style={{ fontSize: 8, color: '#555550', marginLeft: 'auto' }}>{alerts.alerts.length} TOTAL</span>
                </div>
                {alerts.alerts.slice(0, 5).map((a: any, i: number) => (
                  <button key={a.id} onClick={() => onNav?.('alerts')}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 14px', border: 'none', borderBottom: i < Math.min(alerts.alerts.length, 5) - 1 ? '1px solid #d4d4cc' : 'none', background: a.read ? 'none' : '#e8e8e0', cursor: 'pointer', textAlign: 'left' }}>
                    <span style={{ flex: 1, fontSize: 11, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.article?.title ?? '(untitled)'}</span>
                    <span style={{ fontSize: 8, color: '#555550' }}>{a.rule?.name}</span>
                    {a.created_at && <span style={{ fontSize: 8, color: '#555550', width: 48, textAlign: 'right' }}>{a.created_at.slice(0, 10)}</span>}
                  </button>
                ))}
              </>
            ) : <EmptyState msg="NO ALERTS YET" />}
          </Card>
        </Section>
      </div>
    </div>
  )
}
