import { useEffect, useRef, useState, useCallback } from 'react'
import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide, forceX, forceY } from 'd3-force'
import { zoom, zoomIdentity } from 'd3-zoom'
import type { ZoomBehavior, ZoomTransform } from 'd3-zoom'
import { select } from 'd3-selection'
import louvain from 'louvain'
import { api } from '../lib/api'
import { Section, Card, SentimentChip, LangBadge, SkelChartArea, EmptyState } from '../components/Layout'

// ── Shapes per entity type ────────────────────────────────────────────────────
// PER  →  Circle           (a person is round, organic)
// ORG  →  Square/Rect      (an organisation is structured, institutional)
// LOC  →  Triangle         (a location is a map-pin / landmark shape)
// default → Diamond

type ColorMode = 'cluster' | 'type' | 'centrality'

const COLOR_MODE_LABELS: Record<ColorMode, string> = {
  cluster: 'CLUSTERS',
  type: 'ENTITY TYPE',
  centrality: 'CENTRALITY',
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

// Colorblind-safe palette (Okabe-Ito inspired) for auto-detected clusters
const CLUSTER_PALETTE: Rgb[] = [
  [40,  210, 110],
  [53,  143, 243],
  [240, 70,  70],
  [150, 110, 255],
  [255, 150, 50],
  [240, 90,  190],
  [40,  190, 190],
  [180, 200, 40],
  [120, 90,  200],
  [210, 120, 40],
]

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

interface GraphNode {
  id: string
  text: string
  label: string
  x: number
  y: number
  vx: number
  vy: number
  weight: number
  cluster: number
}
interface GraphEdge { source: string; target: string; weight: number }

interface ClusterInfo { index: number; repr: string; count: number }

function nodeColor(n: GraphNode, mode: ColorMode): { fg: Rgb; bg: Rgb; density: number; label: string } {
  const bg = COLORS.white
  if (mode === 'cluster') {
    const fg = CLUSTER_PALETTE[n.cluster % CLUSTER_PALETTE.length]
    return { fg, bg, density: 0.72, label: `CLUSTER ${n.cluster + 1}` }
  }
  if (mode === 'type') {
    if (n.label === 'PER') return { fg: COLORS.blue,   bg, density: 0.72, label: 'PERSON' }
    if (n.label === 'ORG') return { fg: COLORS.orange, bg, density: 0.72, label: 'ORG' }
    return { fg: COLORS.green, bg, density: 0.72, label: 'LOCATION' }
  }
  const d = Math.min(0.9, 0.2 + n.weight * 0.055)
  const fg: Rgb = d > 0.6 ? COLORS.red : d > 0.4 ? COLORS.orange : COLORS.blue
  return { fg, bg, density: d, label: d > 0.6 ? 'HIGH' : d > 0.4 ? 'MID' : 'LOW' }
}

function convexHull(points: { x: number; y: number }[]): { x: number; y: number }[] | null {
  if (points.length < 3) return null
  const pts = points.slice().sort((a, b) => (a.x === b.x ? a.y - b.y : a.x - b.x))
  const cross = (o: any, a: any, b: any) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
  const lower: any[] = []
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop()
    lower.push(p)
  }
  const upper: any[] = []
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i]
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop()
    upper.push(p)
  }
  lower.pop(); upper.pop()
  return lower.concat(upper)
}

function padHull(pts: { x: number; y: number }[], pad = 26) {
  const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length
  const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length
  return pts.map(p => {
    const dx = p.x - cx, dy = p.y - cy, d = Math.hypot(dx, dy) || 1
    return { x: p.x + (dx / d) * pad, y: p.y + (dy / d) * pad }
  })
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
  const [colorMode, setColorMode] = useState<ColorMode>('cluster')
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [everClicked, setEverClicked] = useState(false)
  const [sidebarArticles, setSidebarArticles] = useState<any[]>([])
  const [sidebarRelations, setSidebarRelations] = useState<any[]>([])
  const [sidebarLoading, setSidebarLoading] = useState(false)
  const [focusId, setFocusId] = useState<string | null>(null)

  // Animation / interaction refs
  const dimRef = useRef({ w: 900, h: 560, dpr: 1 })
  const graphRef = useRef<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null)
  const simRef = useRef<any>(null)
  const hoveredRef = useRef<GraphNode | null>(null)
  const selectedRef = useRef<GraphNode | null>(null)
  const colorModeRef = useRef<ColorMode>('cluster')
  const dirtyRef = useRef(true)
  const transformRef = useRef<ZoomTransform>(zoomIdentity)
  const zoomRef = useRef<ZoomBehavior<HTMLCanvasElement, unknown> | null>(null)
  const patternCache = useRef<Map<string, CanvasPattern>>(new Map())
  const bgPatternRef = useRef<CanvasPattern | null>(null)
  const topLabelRef = useRef<Set<string>>(new Set())
  const adjRef = useRef<Map<string, Set<string>>>(new Map())
  const hullsRef = useRef<Map<number, { x: number; y: number }[]>>(new Map())
  const clusterInfoRef = useRef<ClusterInfo[]>([])
  const anchorRef = useRef<Map<number, { x: number; y: number }>>(new Map())
  const maxNodeWRef = useRef(1)
  const focusRef = useRef<string | null>(null)
  const rafRef = useRef<number | undefined>(undefined)

  const clusterAnyNode = (c: number): string => {
    const n = graphRef.current?.nodes.find(x => x.cluster === c)
    return n ? n.id : ''
  }

  useEffect(() => { colorModeRef.current = colorMode; dirtyRef.current = true }, [colorMode])
  useEffect(() => { selectedRef.current = selected; dirtyRef.current = true }, [selected])
  useEffect(() => { focusRef.current = focusId; dirtyRef.current = true }, [focusId])

  const nodeRadius = (n: GraphNode) => 5 + (n.weight / (maxNodeWRef.current || 1)) * 14

  const recomputeHulls = useCallback(() => {
    const g = graphRef.current
    if (!g) return
    const byCluster = new Map<number, { x: number; y: number }[]>()
    for (const n of g.nodes) {
      if (n.cluster == null) continue
      if (!byCluster.has(n.cluster)) byCluster.set(n.cluster, [])
      byCluster.get(n.cluster)!.push({ x: n.x, y: n.y })
    }
    const hulls = new Map<number, { x: number; y: number }[]>()
    for (const [c, pts] of byCluster) {
      const h = convexHull(pts)
      if (h && h.length >= 3) hulls.set(c, padHull(h))
    }
    hullsRef.current = hulls
  }, [])

  // Fetch graph data + build / cluster / simulate
  useEffect(() => {
    setGraphError(false)
    setGraphData(null)
    graphRef.current = null
    simRef.current?.stop()

    api.graphCooccurrence({ limit: 400, min_weight: minWeight, label: labelFilter !== 'ALL' ? labelFilter : undefined })
      .then((r: any) => {
        const edges: GraphEdge[] = (r.edges ?? []).map((e: any) => ({
          source: String(e.source),
          target: String(e.target),
          weight: e.weight,
        }))
        const nodeMap = new Map<string, GraphNode>()
        for (const e of edges) {
          for (const [id, txt, lbl] of [
            [e.source, r.edges.find((x: any) => String(x.source) === e.source)?.source_text, r.edges.find((x: any) => String(x.source) === e.source)?.source_label],
            [e.target, r.edges.find((x: any) => String(x.target) === e.target)?.target_text, r.edges.find((x: any) => String(x.target) === e.target)?.target_label],
          ] as [string, string, string][]) {
            if (!nodeMap.has(id)) {
              nodeMap.set(id, { id, text: txt ?? id, label: lbl ?? 'MISC', x: 0, y: 0, vx: 0, vy: 0, weight: 0, cluster: 0 })
            }
          }
          nodeMap.get(e.source)!.weight += e.weight
          nodeMap.get(e.target)!.weight += e.weight
        }
        const nodes = Array.from(nodeMap.values())
        const maxNodeW = nodes.reduce((m, n) => Math.max(m, n.weight), 0) || 1
        maxNodeWRef.current = maxNodeW

        // ── Community detection (Louvain) ──
        const ids = nodes.map(n => n.id)
        const links = edges.map(e => ({ source: e.source, target: e.target, weight: e.weight }))
        let clusterOf = new Map<string, number>()
        try {
          const raw = (louvain as any).jLouvain().nodes(ids).edges(links)() as Record<string, number>
          clusterOf = new Map(Object.entries(raw).map(([k, v]) => [String(k), v as number]))
        } catch {
          nodes.forEach((n, i) => clusterOf.set(n.id, 0))
        }
        const unique = [...new Set(Array.from(clusterOf.values()))]
        const clusterIndex = new Map(unique.map((c, i) => [c, i]))
        nodes.forEach(n => { n.cluster = clusterIndex.get(clusterOf.get(n.id) ?? 0) ?? 0 })

        // cluster metadata (counts + representative term)
        const counts = new Map<number, number>()
        const repW = new Map<number, number>()
        const repT = new Map<number, string>()
        for (const n of nodes) {
          counts.set(n.cluster, (counts.get(n.cluster) ?? 0) + 1)
          if ((repW.get(n.cluster) ?? 0) < n.weight) { repW.set(n.cluster, n.weight); repT.set(n.cluster, n.text) }
        }
        clusterInfoRef.current = [...counts.keys()]
          .map(c => ({ index: c, count: counts.get(c)!, repr: repT.get(c) ?? '' }))
          .sort((a, b) => b.count - a.count)

        // adjacency for highlight
        const adj = new Map<string, Set<string>>()
        for (const e of edges) {
          if (!adj.has(e.source)) adj.set(e.source, new Set())
          if (!adj.has(e.target)) adj.set(e.target, new Set())
          adj.get(e.source)!.add(e.target)
          adj.get(e.target)!.add(e.source)
        }
        adjRef.current = adj

        const { w: W, h: H } = dimRef.current
        const K = clusterIndex.size
        const anchors = new Map<number, { x: number; y: number }>()
        const R = Math.min(W, H) * 0.32
        for (let k = 0; k < K; k++) {
          const ang = (k / Math.max(1, K)) * Math.PI * 2 - Math.PI / 2
          anchors.set(k, { x: W / 2 + R * Math.cos(ang), y: H / 2 + R * Math.sin(ang) })
        }
        anchorRef.current = anchors

        // seed positions near cluster anchor
        for (const n of nodes) {
          const a = anchors.get(n.cluster)!
          n.x = a.x + (Math.random() - 0.5) * 80
          n.y = a.y + (Math.random() - 0.5) * 80
        }

        const g = { nodes, edges }
        graphRef.current = g
        setGraphData(g)

        const maxW = edges.reduce((m, e) => Math.max(m, e.weight), 0) || 1
        const sim = forceSimulation(nodes as any)
          .force('link', forceLink(links as any).id((d: any) => d.id)
            .distance((d: any) => 28 + (1 - d.weight / maxW) * 64)
            .strength((d: any) => 0.05 + (d.weight / maxW) * 0.5))
          .force('charge', forceManyBody().strength(-160).distanceMax(320))
          .force('collide', forceCollide().radius((d: any) => nodeRadius(d as any) + 3).strength(0.85))
          .force('center', forceCenter(W / 2, H / 2))
          .force('x', forceX((d: any) => anchors.get((d as GraphNode).cluster)!.x).strength(0.06))
          .force('y', forceY((d: any) => anchors.get((d as GraphNode).cluster)!.y).strength(0.06))
        sim.velocityDecay(0.42).alpha(1).alphaDecay(0.05).alphaMin(0.01)
        sim.on('tick', () => { dirtyRef.current = true })
        sim.on('end', () => { recomputeHulls(); dirtyRef.current = true })
        // Pre-warm synchronously: run the layout to (near) convergence in one blocking
        // step so the graph appears settled immediately instead of animating for ~5s.
        sim.stop()
        for (let i = 0; i < 250; i++) sim.tick()
        recomputeHulls()
        dirtyRef.current = true
        // Short, subtle animated tail (~0.5s) so it still feels alive.
        sim.alpha(0.03).alphaDecay(0.08).alphaMin(0.005).restart()
        simRef.current = sim

        const top = [...nodes].sort((a, b) => b.weight - a.weight).slice(0, 22).map(n => n.id)
        topLabelRef.current = new Set(top)
        dirtyRef.current = true
      })
      .catch(() => setGraphError(true))
    api.graphStats().then(setStats).catch(() => setStats(null))
  }, [minWeight, labelFilter, recomputeHulls])

  // Responsive canvas sizing (DPR aware)
  useEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current
    if (!wrap || !canvas) return
    const apply = () => {
      const r = wrap.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const w = Math.max(320, Math.floor(r.width))
      const h = Math.max(320, Math.floor(r.height))
      dimRef.current = { w, h, dpr }
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      canvas.style.width = w + 'px'
      canvas.style.height = h + 'px'
      dirtyRef.current = true
      // re-center + reheat simulation on resize
      const sim = simRef.current
      if (sim) {
        const { w: W, h: H } = dimRef.current
        const K = anchorRef.current.size
        const R = Math.min(W, H) * 0.32
        const anchors = new Map<number, { x: number; y: number }>()
        for (let k = 0; k < K; k++) {
          const ang = (k / Math.max(1, K)) * Math.PI * 2 - Math.PI / 2
          anchors.set(k, { x: W / 2 + R * Math.cos(ang), y: H / 2 + R * Math.sin(ang) })
        }
        anchorRef.current = anchors
        sim.force('center', forceCenter(W / 2, H / 2))
        sim.force('x', forceX((d: any) => anchors.get((d as GraphNode).cluster)!.x).strength(0.06))
        sim.force('y', forceY((d: any) => anchors.get((d as GraphNode).cluster)!.y).strength(0.06))
        sim.alpha(0.12).alphaDecay(0.08).alphaMin(0.005).restart()
      }
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [graphData])

  // Render + simulation loop (always running; cheap when settled)
  useEffect(() => {
    if (!graphData || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')!
    if (!bgPatternRef.current) bgPatternRef.current = ctx.createPattern(makeBgTile(), 'repeat')

    // pan / zoom via d3-zoom
    const zb = zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.2, 8])
      .clickDistance(6)
      .on('zoom', (event) => { transformRef.current = event.transform; dirtyRef.current = true })
    zoomRef.current = zb
    const sel = select(canvas)
    sel.call(zb as any)

    const getPattern = (fg: Rgb, bg: Rgb, density: number) => {
      const key = `${fg.join()}|${bg.join()}|${density}`
      let p = patternCache.current.get(key)
      if (!p) { p = ctx.createPattern(makeDitherTile(fg, bg, density, 32), 'repeat')!; patternCache.current.set(key, p) }
      return p
    }
    const neighborsSet = (id: string | null): Set<string> | null => {
      if (!id) return null
      const s = new Set<string>([id])
      adjRef.current.get(id)?.forEach(x => s.add(x))
      return s
    }

    const renderFrame = () => {
      const { w: W, h: H, dpr } = dimRef.current
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, W, H)
      ctx.fillStyle = '#f5f5f0'
      ctx.fillRect(0, 0, W, H)
      if (bgPatternRef.current) { ctx.fillStyle = bgPatternRef.current; ctx.fillRect(0, 0, W, H) }

      const t = transformRef.current
      ctx.translate(t.x, t.y); ctx.scale(t.k, t.k)

      const g = graphRef.current
      if (!g) return
      const { nodes, edges } = g
      const nodeMap = new Map(nodes.map(n => [n.id, n]))
      const maxW = edges.reduce((m, e) => Math.max(m, e.weight), 0) || 1
      const maxNodeW = maxNodeWRef.current || 1

      const activeId = hoveredRef.current?.id ?? selectedRef.current?.id ?? null
      const highlight = neighborsSet(activeId)
      const focus = focusRef.current
      const visible = focus ? neighborsSet(focus) : null

      // ── Cluster hull regions ──
      for (const [c, pts] of hullsRef.current) {
        if (visible && !visible.has(clusterAnyNode(c))) continue
        ctx.beginPath()
        pts.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))
        ctx.closePath()
        const col = CLUSTER_PALETTE[c % CLUSTER_PALETTE.length]
        ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},0.10)`
        ctx.fill()
        ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},0.45)`
        ctx.setLineDash([4, 3]); ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([])
      }

      // ── Edges ──
      for (const e of edges) {
        const a = nodeMap.get(e.source), b = nodeMap.get(e.target)
        if (!a || !b) continue
        if (visible && !(visible.has(a.id) && visible.has(b.id))) continue
        const lw = 0.4 + (e.weight / maxW) * 2.2
        let alpha = 0.2 + (e.weight / maxW) * 0.45
        const isActive = highlight && highlight.has(a.id) && highlight.has(b.id)
        if (highlight && !isActive) alpha = 0.05
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

      // ── Nodes ──
      for (const n of nodes) {
        if (visible && !visible.has(n.id)) continue
        const r = nodeRadius(n)
        const color = nodeColor(n, colorModeRef.current)
        const isActive = n.id === isHov || n.id === isSel
        const dim = (highlight && !highlight.has(n.id)) ? 0.18 : 1

        ctx.save()
        ctx.translate(n.x, n.y)
        if (dim < 1) ctx.globalAlpha = dim
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

        // Labels: top nodes, active, neighbors of active
        const showLabel = n.id === isHov || n.id === isSel || topLabelRef.current.has(n.id) || (highlight && highlight.has(n.id) && !isActive)
        if (showLabel) {
          ctx.save()
          ctx.globalAlpha = dim < 1 ? dim : 1
          ctx.font = '700 9px "Space Mono", monospace'
          const tw = ctx.measureText(n.text).width
          const lx = n.x - tw / 2 - 5, ly = n.y - r - 17
          ctx.fillStyle = '#0a0a0a'; ctx.fillRect(lx, ly, tw + 10, 13)
          ctx.fillStyle = '#f5f5f0'; ctx.fillText(n.text, n.x - tw / 2, ly + 9)
          ctx.restore()
        }
      }
      ctx.globalAlpha = 1
    }

    const loop = () => {
      if (dirtyRef.current) { renderFrame(); dirtyRef.current = false }
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      sel.on('.zoom', null)
      simRef.current?.stop()
    }
  }, [graphData, recomputeHulls])

  const toWorld = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left, my = e.clientY - rect.top
    const t = transformRef.current
    return { x: (mx - t.x) / t.k, y: (my - t.y) / t.k }
  }

  const hitTest = useCallback((e: React.MouseEvent<HTMLCanvasElement>): GraphNode | null => {
    const g = graphRef.current
    if (!g) return null
    const { x, y } = toWorld(e)
    const maxNodeW = maxNodeWRef.current || 1
    return g.nodes.find(n => {
      const r = 6 + (n.weight / maxNodeW) * 14 + 5
      return Math.hypot(n.x - x, n.y - y) < r
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
    setSidebarArticles([]); setSidebarRelations([]); setSidebarLoading(true)
    api.entityArticles(found.id, 15)
      .then((r: any) => setSidebarArticles(r.articles ?? []))
      .catch(() => setSidebarArticles([]))
    api.entityRelations(found.id, 20)
      .then((r: any) => setSidebarRelations(r.relationships ?? []))
      .catch(() => setSidebarRelations([]))
      .finally(() => setSidebarLoading(false))
  }, [hitTest])

  const legendEntries: { label: string; fg: Rgb; density: number }[] = (() => {
    if (colorMode === 'type') return [
      { label: 'PERSON', fg: COLORS.blue, density: 0.72 },
      { label: 'ORGANISATION', fg: COLORS.orange, density: 0.72 },
      { label: 'LOCATION', fg: COLORS.green, density: 0.72 },
    ]
    if (colorMode === 'centrality') return [
      { label: 'LOW CENTRALITY', fg: COLORS.blue, density: 0.3 },
      { label: 'MID CENTRALITY', fg: COLORS.orange, density: 0.55 },
      { label: 'HIGH CENTRALITY', fg: COLORS.red, density: 0.8 },
    ]
    // cluster mode: list top clusters with representative term
    return clusterInfoRef.current.slice(0, 12).map(c => ({
      label: `${c.repr} · ${c.count}`,
      fg: CLUSTER_PALETTE[c.index % CLUSTER_PALETTE.length],
      density: 0.72,
    }))
  })()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Section title="ENTITY CO-OCCURRENCE GRAPH" sub="FORCE-DIRECTED · AUTO-CLUSTERED" fill>
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

          {selected && (
            <button onClick={() => setFocusId(focusId ? null : selected.id)}
              style={{ padding: '4px 10px', border: '1px solid #0a0a0a', background: focusId ? '#0a0a0a' : 'transparent', color: focusId ? '#f5f5f0' : '#0a0a0a', fontSize: 8, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
              {focusId ? 'SHOW ALL' : 'ISOLATE'}
            </button>
          )}
        </div>

        {graphError && <EmptyState msg="COULD NOT REACH API — CHECK BACKEND CONNECTION" />}
        {!graphData && !graphError && <SkelChartArea height={560} />}
        <Card style={{ flex: 1, minHeight: 0, display: graphError ? 'none' : 'flex', flexDirection: 'column', padding: 0, position: 'relative' }}>
          {graphData && (
            <div ref={wrapRef} style={{ width: '100%', height: '100%', flex: 1, minHeight: 0 }}>
              <canvas
                ref={canvasRef}
                style={{ width: '100%', height: '100%', display: 'block', cursor: hovered ? 'pointer' : 'grab' }}
                onMouseMove={handleMouseMove}
                onMouseLeave={() => { hoveredRef.current = null; setHovered(null); dirtyRef.current = true }}
                onClick={handleClick}
              />
            </div>
          )}

          <div style={{
            position: 'absolute', top: 10, left: 10,
            background: 'rgba(245,245,240,0.92)', border: '1px solid #0a0a0a',
            padding: '8px 10px', fontSize: 8, letterSpacing: '0.09em', maxHeight: 240, overflowY: 'auto',
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
            {colorMode === 'cluster' && clusterInfoRef.current.length > 12 && (
              <div style={{ marginTop: 3, color: '#555550' }}>+{clusterInfoRef.current.length - 12} more</div>
            )}
          </div>

          {!everClicked && !hovered && (
            <div style={{ position: 'absolute', bottom: 10, right: 10, fontSize: 8, letterSpacing: '0.12em', color: '#555550', pointerEvents: 'none' }}>
              SCROLL = ZOOM · DRAG = PAN · CLICK A NODE ▶
            </div>
          )}

          {hovered && (
            <div style={{ position: 'absolute', bottom: 10, left: 10, background: '#0a0a0a', color: '#f5f5f0', fontSize: 10, padding: '5px 10px', letterSpacing: '0.08em', pointerEvents: 'none' }}>
              {hovered.text} · {hovered.label} · {hovered.weight} co-occ. · {hovered.cluster + 1 >= 0 ? `CLUSTER ${hovered.cluster + 1}` : ''}
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
                  {selected.weight} CO-OCCURRENCES · CLUSTER {selected.cluster + 1} · CLICK OUTSIDE TO CLOSE
                </div>
              </div>
              <button onClick={() => setSelected(null)} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer', color: '#f5f5f0', padding: 2, lineHeight: 1, flexShrink: 0 }}>×</button>
            </div>

            <div style={{ padding: '8px 16px', borderBottom: '1px solid #d4d4cc', fontSize: 8, letterSpacing: '0.14em', color: '#555550', background: '#efefea', flexShrink: 0 }}>
              RELATIONSHIPS
            </div>
            <div style={{ flexShrink: 0 }}>
              {sidebarLoading ? (
                <div style={{ padding: '18px 16px', textAlign: 'center', fontSize: 10, letterSpacing: '0.15em', color: '#555550' }}>LOADING<span className="cursor-blink">_</span></div>
              ) : sidebarRelations.length === 0 ? (
                <div style={{ padding: '18px 16px', textAlign: 'center', fontSize: 10, letterSpacing: '0.12em', color: '#555550' }}>▣ NO RELATIONSHIPS FOUND</div>
              ) : (
                sidebarRelations.map((rel, i) => {
                  const isSubj = rel.subject === selected.text
                  const other = isSubj ? rel.object : rel.subject
                  const otherLbl = isSubj ? rel.object_label : rel.subject_label
                  return (
                    <div key={i} style={{ padding: '8px 16px', borderBottom: '1px solid #d4d4cc', fontSize: 11 }}>
                      <span style={{ fontWeight: 700, color: '#0a0a0a' }}>{other}</span>
                      <span style={{ fontSize: 8, color: '#777', margin: '0 6px' }}>{otherLbl}</span>
                      <span style={{ fontSize: 8, letterSpacing: '0.08em', background: '#0a0a0a', color: '#f5f5f0', padding: '1px 5px' }}>{rel.predicate}</span>
                      <span style={{ fontSize: 8, color: '#777', marginLeft: 6 }}>{isSubj ? '→' : '←'}</span>
                    </div>
                  )
                })
              )}
            </div>

            <div style={{ padding: '8px 16px', borderBottom: '1px solid #d4d4cc', fontSize: 8, letterSpacing: '0.14em', color: '#555550', background: '#efefea', flexShrink: 0 }}>
              ARTICLES MENTIONING THIS ENTITY
            </div>

            <div style={{ flex: 1 }}>
              {!sidebarLoading && sidebarArticles.length === 0 ? (
                <div style={{ padding: '18px 16px', textAlign: 'center', fontSize: 10, letterSpacing: '0.12em', color: '#555550' }}>▣ NO ARTICLES FOUND</div>
              ) : sidebarArticles.map((a, i) => (
                <div key={a.id} style={{ padding: '11px 16px', borderBottom: '1px solid #d4d4cc' }}>
                  <a href={a.url ?? '#'} target="_blank" rel="noreferrer" style={{ fontSize: 12, fontWeight: 700, color: '#0a0a0a', textDecoration: 'none', lineHeight: 1.35, display: 'block', marginBottom: 6 }}>{a.title}</a>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    {a.source_name && <span style={{ fontSize: 8, color: '#555550', letterSpacing: '0.06em' }}>{a.source_name}</span>}
                    {a.language && <LangBadge lang={a.language} />}
                    {a.sentiment_label && <SentimentChip label={a.sentiment_label} />}
                    <span style={{ fontSize: 8, color: '#aaa', marginLeft: 'auto' }}>{a.published_date?.slice(0, 10)}</span>
                  </div>
                </div>
              ))}
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
