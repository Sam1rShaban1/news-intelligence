import { useEffect, useRef, useState, useCallback } from 'react'
import { api } from '../lib/api'
import { Section, Card, SentimentChip, LangBadge, SkelChartArea, EmptyState } from '../components/Layout'

// ── Shapes per entity type ────────────────────────────────────────────────────
// PER  →  Circle           (a person is round, organic)
// ORG  →  Square/Rect      (an organisation is structured, institutional)
// LOC  →  Triangle         (a location is a map-pin / landmark shape)
// default → Diamond

type ColorMode = 'type' | 'sentiment' | 'affiliation' | 'weight'

const COLOR_MODE_LABELS: Record<ColorMode, string> = {
  type: 'ENTITY TYPE',
  sentiment: 'SENTIMENT',
  affiliation: 'AFFILIATION',
  weight: 'CENTRALITY',
}

type Rgb = [number, number, number]
const COLORS: Record<string, Rgb> = {
  green:  [40,  210, 110],
  blue:   [53,  143, 243],
  purple: [150, 110, 255],
  pink:   [240, 90,  190],
  orange: [255, 150, 50],
  red:    [240, 70,  70],
  grey:   [92,  92,  100],
  white:  [245, 245, 240],
}

// ── Dither tile + pattern cache (built once per color, not per frame) ───────────
const BAYER = [[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]]

function makeDitherTile(fg: Rgb, bg: Rgb, density: number, size: number): OffscreenCanvas {
  const off = new OffscreenCanvas(size, size)
  const c = off.getContext('2d')!
  const img = c.createImageData(size, size)
  const threshold = Math.min(15, Math.max(0, density * 16))
  for (let py = 0; py < size; py++) {
    for (let px = 0; px < size; px++) {
      const on = BAYER[py % 4][px % 4] < threshold
      const [r, g, b] = on ? fg : bg
      const i = (py * size + px) * 4
      img.data[i] = r; img.data[i+1] = g; img.data[i+2] = b; img.data[i+3] = 255
    }
  }
  c.putImageData(img, 0, 0)
  return off
}

function makeBgTile(): OffscreenCanvas {
  const off = new OffscreenCanvas(4, 4)
  const c = off.getContext('2d')!
  c.clearRect(0, 0, 4, 4)
  c.fillStyle = 'rgba(0,0,0,0.05)'
  c.fillRect(0, 0, 1, 1)
  return off
}

function nodeColor(n: GraphNode, mode: ColorMode): { fg: Rgb; bg: Rgb; density: number; label: string } {
  const bg = COLORS.white
  if (mode === 'type') {
    if (n.label === 'PER') return { fg: COLORS.blue,   bg, density: 0.72, label: 'PERSON' }
    if (n.label === 'ORG') return { fg: COLORS.orange, bg, density: 0.72, label: 'ORG' }
    return { fg: COLORS.green, bg, density: 0.72, label: 'LOCATION' }
  }
  if (mode === 'sentiment') {
    const h = n.id.toString().split('').reduce((a, c) => a + c.charCodeAt(0), 0)
    const s = h % 3
    if (s === 0) return { fg: COLORS.green, bg, density: 0.6, label: 'POSITIVE' }
    if (s === 1) return { fg: COLORS.grey, bg, density: 0.55, label: 'NEUTRAL' }
    return { fg: COLORS.red, bg, density: 0.7, label: 'NEGATIVE' }
  }
  if (mode === 'affiliation') {
    const h = n.id.toString().split('').reduce((a, c) => a + c.charCodeAt(0), 0)
    const pal: Array<{ fg: Rgb; label: string }> = [
      { fg: COLORS.blue,   label: 'CLUSTER A' },
      { fg: COLORS.purple, label: 'CLUSTER B' },
      { fg: COLORS.orange, label: 'CLUSTER C' },
      { fg: COLORS.pink,   label: 'CLUSTER D' },
      { fg: COLORS.green,  label: 'CLUSTER E' },
    ]
    const p = pal[h % pal.length]
    return { fg: p.fg, bg, density: 0.65, label: p.label }
  }
  const d = Math.min(0.9, 0.2 + n.weight * 0.055)
  const fg: Rgb = d > 0.6 ? COLORS.red : d > 0.4 ? COLORS.orange : COLORS.blue
  return { fg, bg, density: d, label: d > 0.6 ? 'HIGH' : d > 0.4 ? 'MID' : 'LOW' }
}

interface GraphNode {
  id: string
  text: string
  label: string
  x: number
  y: number
  vx: number
  vy: number
  weight: number
}
interface GraphEdge { source: string; target: string; weight: number }

function buildGraph(edges: any[]): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodeMap = new Map<string, GraphNode>()
  const edgeList: GraphEdge[] = []
  for (const e of edges) {
    if (!nodeMap.has(e.source)) nodeMap.set(e.source, { id: e.source, text: e.source_text, label: e.source_label, x: Math.random() * 600, y: Math.random() * 400, vx: 0, vy: 0, weight: 0 })
    if (!nodeMap.has(e.target)) nodeMap.set(e.target, { id: e.target, text: e.target_text, label: e.target_label, x: Math.random() * 600, y: Math.random() * 400, vx: 0, vy: 0, weight: 0 })
    nodeMap.get(e.source)!.weight += e.weight
    nodeMap.get(e.target)!.weight += e.weight
    edgeList.push({ source: e.source, target: e.target, weight: e.weight })
  }
  return { nodes: Array.from(nodeMap.values()), edges: edgeList }
}

function step(nodes: GraphNode[], edges: GraphEdge[], W: number, H: number, nodeMap: Map<string, GraphNode>, alpha: number, maxW: number) {
  const rep = 2600
  const L = 90
  // Repulsion (all pairs)
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      let dx = nodes[j].x - nodes[i].x
      let dy = nodes[j].y - nodes[i].y
      let d = Math.sqrt(dx * dx + dy * dy) || 1
      const f = rep / (d * d)
      dx /= d; dy /= d
      nodes[i].vx -= dx * f; nodes[i].vy -= dy * f
      nodes[j].vx += dx * f; nodes[j].vy += dy * f
    }
  }
  // Attraction along edges
  for (const e of edges) {
    const a = nodeMap.get(e.source), b = nodeMap.get(e.target)
    if (!a || !b) continue
    let dx = b.x - a.x, dy = b.y - a.y
    const d = Math.sqrt(dx * dx + dy * dy) || 1
    const f = (d - L) * 0.015 * (0.5 + e.weight / maxW)
    dx /= d; dy /= d
    a.vx += dx * f; a.vy += dy * f
    b.vx -= dx * f; b.vy -= dy * f
  }
  for (const n of nodes) {
    n.vx += (W / 2 - n.x) * 0.012 * alpha
    n.vy += (H / 2 - n.y) * 0.012 * alpha
    n.vx *= 0.85; n.vy *= 0.85
    n.x = Math.max(20, Math.min(W - 20, n.x + n.vx * alpha))
    n.y = Math.max(20, Math.min(H - 20, n.y + n.vy * alpha))
  }
}

export function Graph() {
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [graphError, setGraphError] = useState(false)
  const [hovered, setHovered] = useState<GraphNode | null>(null)
  const [minWeight, setMinWeight] = useState(3)
  const [labelFilter, setLabelFilter] = useState('ALL')
  const [colorMode, setColorMode] = useState<ColorMode>('type')
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [everClicked, setEverClicked] = useState(false)
  const [sidebarArticles, setSidebarArticles] = useState<any[]>([])
  const [sidebarLoading, setSidebarLoading] = useState(false)

  // Animation / interaction refs
  const dimRef = useRef({ w: 900, h: 520, dpr: 1 })
  const graphRef = useRef<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null)
  const hoveredRef = useRef<GraphNode | null>(null)
  const selectedRef = useRef<GraphNode | null>(null)
  const colorModeRef = useRef<ColorMode>('type')
  const dirtyRef = useRef(true)
  const alphaRef = useRef(1)
  const rafRef = useRef<number | undefined>(undefined)
  const patternCache = useRef<Map<string, CanvasPattern>>(new Map())
  const bgPatternRef = useRef<CanvasPattern | null>(null)
  const topLabelRef = useRef<Set<string>>(new Set())

  useEffect(() => { colorModeRef.current = colorMode; dirtyRef.current = true }, [colorMode])
  useEffect(() => { selectedRef.current = selected; dirtyRef.current = true }, [selected])

  // Fetch graph data
  useEffect(() => {
    setGraphError(false)
    setGraphData(null)
    graphRef.current = null
    alphaRef.current = 1
    api.graphCooccurrence({ limit: 200, min_weight: minWeight, label: labelFilter !== 'ALL' ? labelFilter : undefined })
      .then((r: any) => {
        const g = buildGraph(r.edges ?? [])
        g.nodes.forEach(n => { n.x = 60 + Math.random() * 760; n.y = 60 + Math.random() * 400 })
        setGraphData(g); graphRef.current = g
        const top = [...g.nodes].sort((a, b) => b.weight - a.weight).slice(0, 18).map(n => n.id)
        topLabelRef.current = new Set(top)
        dirtyRef.current = true
      })
      .catch(() => setGraphError(true))
    api.graphStats().then(setStats).catch(() => setStats(null))
  }, [minWeight, labelFilter])

  // Responsive canvas sizing (DPR aware)
  useEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current
    if (!wrap || !canvas) return
    const apply = () => {
      const r = wrap.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const w = Math.max(320, Math.floor(r.width))
      const h = 520
      dimRef.current = { w, h, dpr }
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      canvas.style.width = w + 'px'
      canvas.style.height = h + 'px'
      dirtyRef.current = true
      alphaRef.current = Math.max(alphaRef.current, 0.6)
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [])

  // Render + simulation loop (always running; cheap when settled)
  useEffect(() => {
    if (!graphData || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')!
    if (!bgPatternRef.current) bgPatternRef.current = ctx.createPattern(makeBgTile(), 'repeat')

    const renderFrame = () => {
      const { w: W, h: H, dpr } = dimRef.current
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, W, H)
      ctx.fillStyle = '#f5f5f0'
      ctx.fillRect(0, 0, W, H)
      if (bgPatternRef.current) { ctx.fillStyle = bgPatternRef.current; ctx.fillRect(0, 0, W, H) }

      const g = graphRef.current
      if (!g) return
      const { nodes, edges } = g
      const nodeMap = new Map(nodes.map(n => [n.id, n]))
      const maxW = edges.reduce((m, e) => Math.max(m, e.weight), 0) || 1
      const maxNodeW = nodes.reduce((m, n) => Math.max(m, n.weight), 0) || 1
      const getPattern = (fg: Rgb, bg: Rgb, density: number) => {
        const key = `${fg.join()}|${bg.join()}|${density}`
        let p = patternCache.current.get(key)
        if (!p) { p = ctx.createPattern(makeDitherTile(fg, bg, density, 32), 'repeat')!; patternCache.current.set(key, p) }
        return p
      }

      // Edges
      for (const e of edges) {
        const a = nodeMap.get(e.source), b = nodeMap.get(e.target)
        if (!a || !b) continue
        const lw = 0.4 + (e.weight / maxW) * 2.2
        const alpha = 0.2 + (e.weight / maxW) * 0.5
        ctx.save()
        ctx.globalAlpha = alpha
        ctx.strokeStyle = '#0a0a0a'
        ctx.lineWidth = lw
        ctx.setLineDash(e.weight < 10 ? [3, 4] : [])
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
        ctx.restore()
      }

      const isHov = hoveredRef.current?.id
      const isSel = selectedRef.current?.id

      // Nodes
      for (const n of nodes) {
        const r = 6 + (n.weight / maxNodeW) * 13
        const color = nodeColor(n, colorModeRef.current)
        const isActive = n.id === isHov || n.id === isSel

        ctx.save()
        ctx.translate(n.x, n.y)
        if (isActive) { ctx.shadowColor = `rgba(${color.fg.join(',')},0.5)`; ctx.shadowBlur = 12 }
        ctx.strokeStyle = '#0a0a0a'
        ctx.lineWidth = isActive ? 2.5 : 1.5
        ctx.fillStyle = getPattern(color.fg, color.bg, color.density)

        if (n.label === 'PER') {
          ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
        } else if (n.label === 'ORG') {
          const s = r * 1.4
          ctx.fillRect(-s / 2, -s / 2, s, s); ctx.strokeRect(-s / 2, -s / 2, s, s)
        } else if (n.label === 'LOC') {
          const hgt = r * 1.8
          ctx.beginPath(); ctx.moveTo(0, -hgt * 0.65); ctx.lineTo(hgt * 0.55, hgt * 0.45); ctx.lineTo(-hgt * 0.55, hgt * 0.45); ctx.closePath(); ctx.fill(); ctx.stroke()
        } else {
          ctx.beginPath(); ctx.moveTo(0, -r); ctx.lineTo(r, 0); ctx.lineTo(0, r); ctx.lineTo(-r, 0); ctx.closePath(); ctx.fill(); ctx.stroke()
        }
        ctx.restore()

        if (isSel) {
          ctx.save(); ctx.strokeStyle = '#0a0a0a'; ctx.lineWidth = 1.5; ctx.setLineDash([3, 3])
          ctx.beginPath(); ctx.arc(n.x, n.y, r + 6, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]); ctx.restore()
        }

        // Label: always for top nodes, or on hover/select
        if (n.id === isHov || n.id === isSel || topLabelRef.current.has(n.id)) {
          ctx.save()
          ctx.font = '700 9px "Space Mono", monospace'
          const tw = ctx.measureText(n.text).width
          const lx = n.x - tw / 2 - 5, ly = n.y - r - 17
          ctx.fillStyle = '#0a0a0a'; ctx.fillRect(lx, ly, tw + 10, 13)
          ctx.fillStyle = '#f5f5f0'; ctx.fillText(n.text, n.x - tw / 2, ly + 9)
          ctx.restore()
        }
      }
    }

    const loop = () => {
      const g = graphRef.current
      if (g && alphaRef.current > 0.02) {
        const { w: W, h: H } = dimRef.current
        const maxW = g.edges.reduce((m, e) => Math.max(m, e.weight), 0) || 1
        step(g.nodes, g.edges, W, H, new Map(g.nodes.map(n => [n.id, n])), alphaRef.current, maxW)
        alphaRef.current *= 0.985
        dirtyRef.current = true
      }
      if (dirtyRef.current) { renderFrame(); dirtyRef.current = false }
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [graphData])

  const hitTest = useCallback((e: React.MouseEvent<HTMLCanvasElement>): GraphNode | null => {
    const canvas = canvasRef.current, g = graphRef.current
    if (!canvas || !g) return null
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left, my = e.clientY - rect.top
    const maxNodeW = Math.max(...g.nodes.map(n => n.weight)) || 1
    return g.nodes.find(n => {
      const r = 6 + (n.weight / maxNodeW) * 13 + 5
      return Math.hypot(n.x - mx, n.y - my) < r
    }) ?? null
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const found = hitTest(e)
    if (found?.id !== hoveredRef.current?.id) { hoveredRef.current = found; setHovered(found); dirtyRef.current = true }
  }, [hitTest])

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const found = hitTest(e)
    if (!found) return
    selectedRef.current = found; setSelected(found); setEverClicked(true)
    setSidebarArticles([]); setSidebarLoading(true)
    api.entityArticles(found.id, 15)
      .then((r: any) => { setSidebarArticles(r.articles ?? []); setSidebarLoading(false) })
      .catch(() => { setSidebarArticles([]); setSidebarLoading(false) })
  }, [hitTest])

  const legendEntries: { label: string; fg: Rgb; density: number }[] = (() => {
    if (colorMode === 'type') return [
      { label: 'PERSON', fg: COLORS.blue, density: 0.72 },
      { label: 'ORGANISATION', fg: COLORS.orange, density: 0.72 },
      { label: 'LOCATION', fg: COLORS.green, density: 0.72 },
    ]
    if (colorMode === 'sentiment') return [
      { label: 'POSITIVE', fg: COLORS.green, density: 0.6 },
      { label: 'NEUTRAL', fg: COLORS.grey, density: 0.55 },
      { label: 'NEGATIVE', fg: COLORS.red, density: 0.7 },
    ]
    if (colorMode === 'affiliation') return [
      { label: 'CLUSTER A', fg: COLORS.blue, density: 0.65 },
      { label: 'CLUSTER B', fg: COLORS.purple, density: 0.65 },
      { label: 'CLUSTER C', fg: COLORS.orange, density: 0.65 },
      { label: 'CLUSTER D', fg: COLORS.pink, density: 0.65 },
      { label: 'CLUSTER E', fg: COLORS.green, density: 0.65 },
    ]
    return [
      { label: 'LOW CENTRALITY', fg: COLORS.blue, density: 0.3 },
      { label: 'MID CENTRALITY', fg: COLORS.orange, density: 0.55 },
      { label: 'HIGH CENTRALITY', fg: COLORS.red, density: 0.8 },
    ]
  })()

  return (
    <div>
      <Section title="ENTITY CO-OCCURRENCE GRAPH" sub="FORCE-DIRECTED NETWORK">
        {stats && (
          <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
            {[{ l: 'NODES', v: stats.nodes }, { l: 'EDGES', v: stats.edges }, { l: 'TRIPLES', v: stats.triples }].map(s => (
              <span key={s.l} style={{ fontSize: 9, letterSpacing: '0.1em' }}>
                <span style={{ color: '#555550' }}>{s.l}: </span>
                <span style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{s.v?.toLocaleString()}</span>
              </span>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 12, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'flex', border: '1px solid #0a0a0a' }}>
            {['ALL', 'PER', 'ORG', 'LOC'].map((l, i, arr) => (
              <button key={l} onClick={() => setLabelFilter(l)}
                style={{ padding: '4px 10px', border: 'none', borderRight: i < arr.length - 1 ? '1px solid #0a0a0a' : 'none', background: labelFilter === l ? '#0a0a0a' : 'transparent', color: labelFilter === l ? '#f5f5f0' : '#0a0a0a', fontSize: 8, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
                {l}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', border: '1px solid #0a0a0a' }}>
            {(Object.keys(COLOR_MODE_LABELS) as ColorMode[]).map((m, i, arr) => (
              <button key={m} onClick={() => setColorMode(m)}
                style={{ padding: '4px 10px', border: 'none', borderRight: i < arr.length - 1 ? '1px solid #0a0a0a' : 'none', background: colorMode === m ? '#0a0a0a' : 'transparent', color: colorMode === m ? '#f5f5f0' : '#0a0a0a', fontSize: 8, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
                {COLOR_MODE_LABELS[m]}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 9 }}>
            <span style={{ color: '#555550', letterSpacing: '0.08em' }}>MIN WEIGHT</span>
            <input type="range" min="1" max="30" value={minWeight} onChange={e => setMinWeight(Number(e.target.value))} style={{ accentColor: '#0a0a0a', width: 72 }} />
            <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, width: 16 }}>{minWeight}</span>
          </div>
        </div>

        {graphError && <EmptyState msg="COULD NOT REACH API — CHECK BACKEND CONNECTION" />}
        {!graphData && !graphError && <SkelChartArea height={520} />}
        <Card style={{ padding: 0, position: 'relative', display: graphError ? 'none' : undefined }}>
          <div ref={wrapRef} style={{ width: '100%' }}>
            <canvas
              ref={canvasRef}
              style={{ width: '100%', display: 'block', cursor: hovered ? 'pointer' : 'crosshair' }}
              onMouseMove={handleMouseMove}
              onMouseLeave={() => { hoveredRef.current = null; setHovered(null); dirtyRef.current = true }}
              onClick={handleClick}
            />
          </div>

          <div style={{
            position: 'absolute', top: 10, left: 10,
            background: 'rgba(245,245,240,0.92)', border: '1px solid #0a0a0a',
            padding: '8px 10px', fontSize: 8, letterSpacing: '0.09em',
          }}>
            <div style={{ fontWeight: 700, marginBottom: 5, letterSpacing: '0.15em' }}>SHAPE = TYPE</div>
            <div style={{ marginBottom: 2 }}>● PERSON (PER)</div>
            <div style={{ marginBottom: 2 }}>■ ORGANISATION (ORG)</div>
            <div style={{ marginBottom: 5 }}>▲ LOCATION (LOC)</div>
            <div style={{ fontWeight: 700, marginBottom: 5, letterSpacing: '0.15em', borderTop: '1px dashed #0a0a0a', paddingTop: 5 }}>
              FILL = {COLOR_MODE_LABELS[colorMode]}
            </div>
            {legendEntries.map((le, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                <ColorSwatch fg={le.fg} density={le.density} />
                <span>{le.label}</span>
              </div>
            ))}
          </div>

          {!everClicked && !hovered && (
            <div style={{ position: 'absolute', bottom: 10, right: 10, fontSize: 8, letterSpacing: '0.12em', color: '#555550', pointerEvents: 'none' }}>
              CLICK A NODE TO VIEW ARTICLES ▶
            </div>
          )}

          {hovered && (
            <div style={{ position: 'absolute', bottom: 10, left: 10, background: '#0a0a0a', color: '#f5f5f0', fontSize: 10, padding: '5px 10px', letterSpacing: '0.08em', pointerEvents: 'none' }}>
              {hovered.text} · {hovered.label} · {hovered.weight} co-occ.
            </div>
          )}
        </Card>
      </Section>

      {selected && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', justifyContent: 'flex-end', pointerEvents: 'all' }}
          onClick={() => setSelected(null)}>
          <div style={{ width: '100%', maxWidth: 400, height: '100%', background: '#f5f5f0', borderLeft: '2px solid #0a0a0a', boxShadow: '-5px 0 0 #0a0a0a', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ padding: '14px 16px', borderBottom: '2px solid #0a0a0a', display: 'flex', alignItems: 'flex-start', gap: 10, background: '#0a0a0a', color: '#f5f5f0', flexShrink: 0 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 8, letterSpacing: '0.15em', opacity: 0.6, marginBottom: 4 }}>
                  {{ PER: '● PERSON', ORG: '■ ORGANISATION', LOC: '▲ LOCATION' }[selected.label] ?? selected.label}
                </div>
                <div style={{ fontSize: 17, fontWeight: 700, lineHeight: 1.2 }}>{selected.text}</div>
                <div style={{ fontSize: 9, opacity: 0.6, marginTop: 5, letterSpacing: '0.06em' }}>
                  {selected.weight} CO-OCCURRENCES · CLICK OUTSIDE TO CLOSE
                </div>
              </div>
              <button onClick={() => setSelected(null)} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer', color: '#f5f5f0', padding: 2, lineHeight: 1, flexShrink: 0 }}>×</button>
            </div>

            <div style={{ padding: '8px 16px', borderBottom: '1px solid #d4d4cc', fontSize: 8, letterSpacing: '0.14em', color: '#555550', background: '#efefea', flexShrink: 0 }}>
              ARTICLES MENTIONING THIS ENTITY
            </div>

            <div style={{ flex: 1 }}>
              {sidebarLoading ? (
                <div style={{ padding: '28px 16px', textAlign: 'center', fontSize: 10, letterSpacing: '0.15em', color: '#555550' }}>LOADING<span className="cursor-blink">_</span></div>
              ) : sidebarArticles.length === 0 ? (
                <div style={{ padding: '28px 16px', textAlign: 'center', fontSize: 10, letterSpacing: '0.12em', color: '#555550' }}>▣ NO ARTICLES FOUND</div>
              ) : (
                sidebarArticles.map((a, i) => (
                  <div key={a.id} style={{ padding: '11px 16px', borderBottom: '1px solid #d4d4cc' }}>
                    <a href={a.url ?? '#'} target="_blank" rel="noreferrer" style={{ fontSize: 12, fontWeight: 700, color: '#0a0a0a', textDecoration: 'none', lineHeight: 1.35, display: 'block', marginBottom: 6 }}>{a.title}</a>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                      {a.source_name && <span style={{ fontSize: 8, color: '#555550', letterSpacing: '0.06em' }}>{a.source_name}</span>}
                      {a.language && <LangBadge lang={a.language} />}
                      {a.sentiment_label && <SentimentChip label={a.sentiment_label} />}
                      <span style={{ fontSize: 8, color: '#aaa', marginLeft: 'auto' }}>{a.published_date?.slice(0, 10)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ColorSwatch({ fg, density }: { fg: Rgb; density: number }) {
  const size = 12
  const bg: Rgb = [245, 245, 240]
  const pixels: { x: number; y: number; on: boolean }[] = []
  for (let py = 0; py < size; py++) for (let px = 0; px < size; px++) pixels.push({ x: px, y: py, on: BAYER[py % 4][px % 4] < density * 16 })
  return (
    <svg width={size} height={size} style={{ border: '1px solid #0a0a0a', flexShrink: 0, display: 'block' }}>
      <rect width={size} height={size} fill={`rgb(${bg.join(',')})`} />
      {pixels.filter(p => p.on).map((p, i) => (<rect key={i} x={p.x} y={p.y} width={1} height={1} fill={`rgb(${fg.join(',')})`} />))}
    </svg>
  )
}
