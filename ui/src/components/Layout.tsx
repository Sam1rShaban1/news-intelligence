import { type ReactNode, type CSSProperties } from 'react'

export type View = 'overview' | 'explore' | 'sentiment' | 'entities' | 'graph' | 'stories'

const NAV = [
  { id: 'overview' as View, label: 'OVERVIEW', glyph: '◉' },
  { id: 'explore' as View, label: 'EXPLORE', glyph: '⊞' },
  { id: 'sentiment' as View, label: 'SENTIMENT', glyph: '◑' },
  { id: 'entities' as View, label: 'ENTITIES', glyph: '◈' },
  { id: 'graph' as View, label: 'GRAPH', glyph: '⬡' },
  { id: 'stories' as View, label: 'STORIES', glyph: '▤' },
]

interface LayoutProps {
  view: View
  onNav: (v: View) => void
  search: string
  onSearch: (s: string) => void
  online: boolean
  children: ReactNode
}

export function Layout({ view, onNav, search, onSearch, online, children }: LayoutProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', background: '#f5f5f0' }}>
      {/* Top bar */}
      <header
        style={{
          borderBottom: '2px solid #0a0a0a',
          background: '#f5f5f0',
          position: 'sticky',
          top: 0,
          zIndex: 50,
        }}
      >
        {/* Main header row */}
        <div style={{ display: 'flex', alignItems: 'center', padding: '8px 16px', gap: 16 }}>
          <div style={{ flexShrink: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.15em', lineHeight: 1 }}>
              ▣ NI/MK
            </div>
            <div style={{ fontSize: 8, letterSpacing: '0.08em', color: '#555550', marginTop: 1 }}>
              INTELLIGENCE BRIEFING
            </div>
          </div>
          <div style={{ flex: 1, position: 'relative' }}>
            <span style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: '#555550' }}>⌕</span>
            <input
              type="text"
              value={search}
              onChange={e => onSearch(e.target.value)}
              placeholder="SEARCH ARTICLES, ENTITIES, STORIES..."
              style={{
                width: '100%',
                maxWidth: 480,
                padding: '5px 8px 5px 24px',
                border: '1px solid #0a0a0a',
                background: '#efefea',
                fontSize: 10,
                letterSpacing: '0.06em',
                fontFamily: 'Space Mono, monospace',
                outline: 'none',
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 9, letterSpacing: '0.1em' }}>
            <span
              style={{
                width: 7,
                height: 7,
                background: '#0a0a0a',
                display: 'inline-block',
                animation: online ? 'blink 1.4s step-end infinite' : 'none',
              }}
            />
            {online ? 'LIVE' : 'MOCK DATA'}
          </div>
        </div>
        {/* Nav tabs — desktop */}
        <nav
          style={{
            display: 'flex',
            borderTop: '1px solid #0a0a0a',
            overflowX: 'auto',
          }}
          className="hide-on-mobile"
        >
          {NAV.map(n => (
            <button
              key={n.id}
              onClick={() => onNav(n.id)}
              style={{
                padding: '7px 18px',
                fontSize: 9,
                letterSpacing: '0.14em',
                fontFamily: 'Space Mono, monospace',
                fontWeight: 700,
                border: 'none',
                borderRight: '1px solid #0a0a0a',
                cursor: 'pointer',
                transition: 'background 0.1s',
                background: view === n.id ? '#0a0a0a' : 'transparent',
                color: view === n.id ? '#f5f5f0' : '#0a0a0a',
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ marginRight: 5, fontSize: 11 }}>{n.glyph}</span>
              {n.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Content */}
      <main style={{ flex: 1, padding: '20px 16px', maxWidth: 1200, margin: '0 auto', width: '100%' }}>
        {children}
      </main>

      {/* Bottom nav — mobile */}
      <nav
        style={{
          display: 'none',
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          background: '#f5f5f0',
          borderTop: '2px solid #0a0a0a',
          zIndex: 50,
        }}
        className="show-on-mobile"
      >
        {NAV.map(n => (
          <button
            key={n.id}
            onClick={() => onNav(n.id)}
            style={{
              flex: 1,
              padding: '10px 0 6px',
              fontSize: 16,
              border: 'none',
              cursor: 'pointer',
              background: view === n.id ? '#0a0a0a' : 'transparent',
              color: view === n.id ? '#f5f5f0' : '#0a0a0a',
            }}
          >
            <div>{n.glyph}</div>
            <div style={{ fontSize: 7, letterSpacing: '0.1em' }}>{n.label.slice(0, 3)}</div>
          </button>
        ))}
      </nav>

      <style>{`
        @media (max-width: 768px) {
          .hide-on-mobile { display: none !important; }
          .show-on-mobile { display: flex !important; }
          main { padding-bottom: 64px !important; }
        }
      `}</style>
    </div>
  )
}

export function Section({ title, sub, children, fill }: { title: string; sub?: string; children: ReactNode; fill?: boolean }) {
  return (
    <div style={{ marginBottom: fill ? 0 : 28, display: 'flex', flexDirection: 'column', flex: fill ? 1 : undefined, minHeight: fill ? 0 : undefined }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10, borderBottom: '2px solid #0a0a0a', paddingBottom: 6 }}>
        <h2 style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.18em', margin: 0 }}>{title}</h2>
        {sub && <span style={{ fontSize: 9, color: '#555550', letterSpacing: '0.1em' }}>{sub}</span>}
      </div>
      <div style={{ flex: fill ? 1 : undefined, minHeight: fill ? 0 : undefined, display: 'flex', flexDirection: 'column' }}>
        {children}
      </div>
    </div>
  )
}

export function Card({ children, style }: { children: ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      style={{
        border: '1px solid #0a0a0a',
        background: '#efefea',
        padding: 14,
        boxShadow: '3px 3px 0 #0a0a0a',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function KpiTile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div
      style={{
        border: '1px solid #0a0a0a',
        padding: '12px 14px',
        background: '#efefea',
        boxShadow: '2px 2px 0 #0a0a0a',
      }}
    >
      <div style={{ fontSize: 8, letterSpacing: '0.15em', color: '#555550', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      {sub && <div style={{ fontSize: 9, color: '#555550', marginTop: 4, letterSpacing: '0.06em' }}>{sub}</div>}
    </div>
  )
}

export function SentimentChip({ label }: { label: string }) {
  const norm = ({ pos: 'positive', neg: 'negative' } as Record<string, string>)[label] ?? label
  const map: Record<string, string> = {
    positive: '▲ POS',
    negative: '▼ NEG',
    neutral: '— NEU',
  }
  const bg: Record<string, string> = {
    positive: '#0a0a0a',
    negative: '#555550',
    neutral: '#d4d4cc',
  }
  const fg: Record<string, string> = {
    positive: '#f5f5f0',
    negative: '#f5f5f0',
    neutral: '#0a0a0a',
  }
  return (
    <span
      style={{
        fontSize: 8,
        padding: '2px 6px',
        background: bg[norm] ?? '#d4d4cc',
        color: fg[norm] ?? '#0a0a0a',
        letterSpacing: '0.1em',
        fontWeight: 700,
      }}
    >
      {map[norm] ?? norm.toUpperCase()}
    </span>
  )
}

export function LangBadge({ lang }: { lang: string }) {
  return (
    <span
      style={{
        fontSize: 8,
        padding: '1px 5px',
        border: '1px solid #0a0a0a',
        letterSpacing: '0.1em',
        fontWeight: 700,
        background: '#f5f5f0',
      }}
    >
      {lang.toUpperCase()}
    </span>
  )
}

export function EntityBadge({ label }: { label: string }) {
  const map: Record<string, string> = { PER: '●', ORG: '■', LOC: '◆' }
  return (
    <span style={{ fontSize: 9, color: '#555550', letterSpacing: '0.06em' }}>
      {map[label] ?? '○'} {label}
    </span>
  )
}

export function EmptyState({ msg }: { msg: string }) {
  return (
    <div
      style={{
        padding: '32px 0',
        textAlign: 'center',
        fontSize: 10,
        letterSpacing: '0.12em',
        color: '#555550',
        borderTop: '1px dashed #0a0a0a',
      }}
    >
      ▣ {msg}
    </div>
  )
}

export function LoadingDots() {
  return (
    <div style={{ padding: '32px 0', textAlign: 'center', fontSize: 11, letterSpacing: '0.2em', color: '#555550' }}>
      LOADING<span className="cursor-blink">_</span>
    </div>
  )
}

// ── Skeleton system ───────────────────────────────────────────────────────────

const SKEL_BG = 'repeating-linear-gradient(45deg,#d4d4cc,#d4d4cc 1px,#e4e4de 1px,#e4e4de 4px)'

export function Skel({ w = '100%', h = 14, style }: { w?: string | number; h?: string | number; style?: CSSProperties }) {
  return (
    <div style={{ width: w, height: h, background: SKEL_BG, animation: 'skel-pulse 1.6s ease-in-out infinite', flexShrink: 0, ...style }} />
  )
}

export function SkelKpiRow({ count = 6 }: { count?: number }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ border: '1px solid #0a0a0a', padding: '12px 14px', background: '#efefea', boxShadow: '2px 2px 0 #0a0a0a' }}>
          <Skel h={8} w="55%" style={{ marginBottom: 8 }} />
          <Skel h={24} w="70%" style={{ marginBottom: 6 }} />
          <Skel h={8} w="45%" />
        </div>
      ))}
    </div>
  )
}

export function SkelChartArea({ height = 176 }: { height?: number }) {
  const bars = [0.45, 0.7, 0.55, 0.85, 0.5, 0.65, 0.3]
  return (
    <div style={{ height, display: 'flex', alignItems: 'flex-end', gap: 6, padding: '0 4px 4px' }}>
      {bars.map((ratio, i) => (
        <Skel key={i} h={Math.round(height * ratio * 0.85)} style={{ flex: 1 }} />
      ))}
    </div>
  )
}

export function SkelArticleRows({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ padding: '12px 14px', borderBottom: '1px solid #d4d4cc' }}>
          <Skel h={13} style={{ marginBottom: 5 }} />
          <Skel h={10} w="72%" style={{ marginBottom: 7 }} />
          <div style={{ display: 'flex', gap: 6 }}>
            <Skel h={14} w={28} />
            <Skel h={14} w={42} />
            <Skel h={14} w={36} style={{ marginLeft: 'auto' }} />
          </div>
        </div>
      ))}
    </>
  )
}

export function SkelEntityCards({ count = 8 }: { count?: number }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 10 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ border: '1px solid #0a0a0a', background: '#efefea', boxShadow: '2px 2px 0 #0a0a0a', padding: '10px 12px' }}>
          <Skel h={8} w="35%" style={{ marginBottom: 6 }} />
          <Skel h={14} w="80%" style={{ marginBottom: 8 }} />
          <Skel h={4} style={{ marginBottom: 4 }} />
          <Skel h={9} w="40%" />
        </div>
      ))}
    </div>
  )
}

export function SkelStoryCards({ count = 6 }: { count?: number }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ border: '1px solid #0a0a0a', background: '#efefea', boxShadow: '3px 3px 0 #0a0a0a', padding: 14 }}>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <Skel h={18} w={42} />
            <Skel h={18} w={28} />
            <Skel h={18} w={40} style={{ marginLeft: 'auto' }} />
          </div>
          <Skel h={14} style={{ marginBottom: 5 }} />
          <Skel h={14} w="85%" style={{ marginBottom: 8 }} />
          <Skel h={10} style={{ marginBottom: 4 }} />
          <Skel h={10} w="70%" style={{ marginBottom: 10 }} />
          <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
            {[42, 52, 38].map(w => <Skel key={w} h={18} w={w} />)}
          </div>
          <Skel h={8} w="60%" style={{ marginBottom: 6 }} />
          <Skel h={3} />
        </div>
      ))}
    </div>
  )
}
