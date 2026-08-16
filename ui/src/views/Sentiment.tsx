import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import {
  PieChart, Pie, Legend, Tooltip,
  BarChart, Bar, XAxis, YAxis,
  type ChartConfig,
} from '../components/dither-kit'
import { Section, Card, SentimentChip, LangBadge, SkelChartArea, SkelArticleRows, EmptyState } from '../components/Layout'

const LANGS = ['mk', 'sq', 'en', 'tr']
const LABEL_MAP: Record<string, string> = { pos: 'positive', neg: 'negative', neutral: 'neutral' }
const normLabel = (l: string) => LABEL_MAP[l] ?? l

export function Sentiment() {
  const [dist, setDist] = useState<any>(null)
  const [distError, setDistError] = useState(false)
  const [recent, setRecent] = useState<any[] | null>(null)

  useEffect(() => {
    api.sentimentDist()
      .then(d => { setDist(d); setDistError(false) })
      .catch(() => setDistError(true))
    api.sentimentRecent(12)
      .then((r: any) => setRecent(r.articles ?? []))
      .catch(() => setRecent([]))
  }, [])

  const pieConfig: ChartConfig = {
    positive: { label: 'Positive', color: 'green' },
    neutral:  { label: 'Neutral',  color: 'blue' },
    negative: { label: 'Negative', color: 'red' },
  }
  const byLangConfig: ChartConfig = {
    positive: { label: 'Positive', color: 'green' },
    neutral:  { label: 'Neutral',  color: 'blue' },
    negative: { label: 'Negative', color: 'red' },
  }

  const pieData = (dist?.distribution ?? []).map((item: any) => ({ name: normLabel(item.label), value: item.count }))
  const byLangData = LANGS.map(l => {
    const d = dist?.by_language?.[l] ?? {}
    return { lang: l.toUpperCase(), positive: d.positive ?? d.pos ?? 0, neutral: d.neutral ?? 0, negative: d.negative ?? d.neg ?? 0 }
  })

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Section title="OVERALL DISTRIBUTION" sub={dist ? `${dist.total_analyzed?.toLocaleString()} ANALYZED` : ''}>
          <Card>
            {!dist && !distError ? <SkelChartArea height={208} /> : distError ? <EmptyState msg="COULD NOT REACH API" /> : pieData.length === 0 ? <EmptyState msg="NO DATA" /> : (
              <PieChart data={pieData} config={pieConfig} dataKey="value" nameKey="name" innerRadius={0.4} bloom="off" className="h-52">
                <Pie variant="hatched" />
                <Legend />
                <Tooltip labelKey="name" />
              </PieChart>
            )}
          </Card>
        </Section>

        <Section title="BY LANGUAGE" sub="STACKED COUNTS">
          <Card>
            {!dist && !distError ? <SkelChartArea height={208} /> : distError ? <EmptyState msg="COULD NOT REACH API" /> : (
              <BarChart data={byLangData} config={byLangConfig} bloom="off" className="h-52">
                <XAxis dataKey="lang" />
                <YAxis />
                <Tooltip labelKey="lang" />
                <Legend />
                <Bar dataKey="positive" variant="dotted" />
                <Bar dataKey="neutral" variant="hatched" />
                <Bar dataKey="negative" variant="solid" />
              </BarChart>
            )}
          </Card>
        </Section>
      </div>

      <Section title="RECENT SENTIMENT FEED" sub="LATEST ANALYZED">
        <Card style={{ padding: 0 }}>
          {recent === null ? <SkelArticleRows count={6} /> : recent.length === 0 ? <EmptyState msg="NO RECENT ARTICLES" /> : (
            recent.map((a, i) => {
              const scoreVal = typeof a.score === 'number' ? a.score : 0
              const barW = Math.abs(scoreVal) * 100
              return (
                <div key={a.id}
                  style={{ padding: '10px 14px', borderBottom: i < recent.length - 1 ? '1px solid #d4d4cc' : 'none', display: 'grid', gridTemplateColumns: '1fr auto auto auto', gap: 10, alignItems: 'center' }}>
                  <a href={a.url} target="_blank" rel="noreferrer" style={{ fontSize: 11, fontWeight: 600, color: '#0a0a0a', textDecoration: 'none' }}>{a.title}</a>
                  <LangBadge lang={a.language} />
                  <SentimentChip label={normLabel(a.label)} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <div style={{ width: 60, height: 8, border: '1px solid #0a0a0a', position: 'relative', background: '#f5f5f0' }}>
                      <div style={{
                        position: 'absolute', top: 0, height: '100%',
                        width: `${barW / 2}%`,
                        background: scoreVal >= 0
                          ? 'repeating-linear-gradient(45deg, #0a0a0a, #0a0a0a 1px, transparent 1px, transparent 3px)'
                          : '#0a0a0a',
                        left: scoreVal >= 0 ? '50%' : `${50 - barW / 2}%`,
                      }} />
                      <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: '#0a0a0a' }} />
                    </div>
                    <span style={{ fontSize: 9, fontVariantNumeric: 'tabular-nums', color: '#555550', width: 34 }}>
                      {scoreVal >= 0 ? '+' : ''}{scoreVal.toFixed(2)}
                    </span>
                  </div>
                </div>
              )
            })
          )}
        </Card>
      </Section>
    </div>
  )
}
