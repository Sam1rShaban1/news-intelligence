import { useEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { zoom, zoomIdentity } from 'd3-zoom'
import type { ZoomBehavior, ZoomTransform } from 'd3-zoom'
import { select } from 'd3-selection'
import { api } from '../lib/api'
import GraphWorker from '../workers/graphLayout.worker.ts?worker&inline'
import { runLayout, reheat } from '../workers/layoutCore'
import { SentimentChip, LangBadge, EmptyState } from '../components/Layout'

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
  const [nodeLimit, setNodeLimit] = useState(400)
  const [labelFilter, setLabelFilter] = useState('ALL')
  const [colorMode, setColorMode] = useState<ColorMode>('cluster')
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [everClicked, setEverClicked] = useState(false)
  const [sidebarArticles, setSidebarArticles] = useState<any[]>([])
  const [sidebarRelations, setSidebarRelations] = useState<any[]>([])
  const [sidebarLoading, setSidebarLoading] = useState(false)
  const [nodeDetail, setNodeDetail] = useState<any | null>(null)
  const [focusId, setFocusId] = useState<string | null>(null)
  const [focusCluster, setFocusCluster] = useState<number | null>(null)
  const [, setLayoutTick] = useState(0)

  // Animation / interaction refs
  const dimRef = useRef({ w: 900, h: 560, dpr: 1 })
  const graphRef = useRef<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null)
  const workerRef = useRef<Worker | null>(null)
  const hoveredRef = useRef<GraphNode | null>(null)
  const selectedRef = useRef<GraphNode | null>(null)
  const colorModeRef = useRef<ColorMode>('cluster')
  const dirtyRef = useRef(true)
  const transformRef = useRef<ZoomTransform>(zoomIdentity)
  const userZoomedRef = useRef(false)
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
  const focusClusterRef = useRef<number | null>(null)
  const rafRef = useRef<number | undefined>(undefined)

  const clusterAnyNode = (c: number): string => {
    const n = graphRef.current?.nodes.find(x => x.cluster === c)
    return n ? n.id : ''
  }

  useEffect(() => { colorModeRef.current = colorMode; dirtyRef.current = true }, [colorMode])
  useEffect(() => { selectedRef.current = selected; dirtyRef.current = true }, [selected])
  useEffect(() => { focusRef.current = focusId; dirtyRef.current = true }, [focusId])
  useEffect(() => { focusClusterRef.current = focusCluster; dirtyRef.current = true }, [focusCluster])
  // When a node is isolated, keep the isolation locked to whatever node is
  // currently selected (so clicking another node re-focuses the isolate view).
  useEffect(() => { if (focusId && selected) setFocusId(selected.id) }, [selected])

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

  // Fetch graph data + hand off layout to a Web Worker (with main-thread fallback)
  useEffect(() => {
    setGraphError(false)
    setGraphData(null)
    graphRef.current = null
    userZoomedRef.current = false
    workerRef.current?.terminate()
    workerRef.current = null

    const controller = new AbortController()
    let cancelled = false
    let worker: Worker | null = null
    let stopFallback: (() => void) | null = null
    let layoutStarted = false
    let watchdog: any = null
    try {
      worker = new GraphWorker()
      workerRef.current = worker
      worker.onmessage = (ev: MessageEvent) => applyMessage(ev.data)
    } catch {
      worker = null
    }
    // If the worker never produces a layout (e.g. it failed to start), fall back
    // to running the same layout on the main thread so the graph still renders.
    if (worker) {
      watchdog = setTimeout(() => {
        if (layoutStarted || workerRef.current !== worker) return
        worker?.terminate()
        workerRef.current = null
        if (graphRef.current) {
          stopFallback = runLayout(
            graphRef.current.nodes as any,
            graphRef.current.edges as any,
            dimRef.current.w,
            dimRef.current.h,
            {
              onInit: (c, count) => applyMessage({ type: 'init', clusters: c, count }),
              onTick: (b) => applyMessage({ type: 'tick', buf: b }),
              onDone: (b) => applyMessage({ type: 'done', buf: b }),
            },
          )
        }
      }, 6000)
    }

    const applyMessage = (data: any) => {
      const g = graphRef.current
      if (!g) return
      if (data.type === 'init') {
        for (const n of g.nodes) n.cluster = data.clusters[n.id] ?? 0
        const { w: W, h: H } = dimRef.current
        const K = data.count
        const R = Math.min(W, H) * 0.32
        const anchors = new Map<number, { x: number; y: number }>()
        for (let k = 0; k < K; k++) {
          const ang = (k / Math.max(1, K)) * Math.PI * 2 - Math.PI / 2
          anchors.set(k, { x: W / 2 + R * Math.cos(ang), y: H / 2 + R * Math.sin(ang) })
        }
        anchorRef.current = anchors
        const counts = new Map<number, number>()
        const repW = new Map<number, number>()
        const repT = new Map<number, string>()
        for (const n of g.nodes) {
          counts.set(n.cluster, (counts.get(n.cluster) ?? 0) + 1)
          if ((repW.get(n.cluster) ?? 0) < n.weight) { repW.set(n.cluster, n.weight); repT.set(n.cluster, n.text) }
        }
        clusterInfoRef.current = [...counts.keys()]
          .map(c => ({ index: c, count: counts.get(c)!, repr: repT.get(c) ?? '' }))
          .sort((a, b) => b.count - a.count)
        const top = [...g.nodes].sort((a, b) => b.weight - a.weight).slice(0, 22).map(n => n.id)
        topLabelRef.current = new Set(top)
        dirtyRef.current = true
        setLayoutTick(t => t + 1) // re-render so the legend picks up the new clusters
        layoutStarted = true
        if (watchdog) clearTimeout(watchdog)
        } else if (data.type === 'tick') {
          const buf = data.buf as Float32Array
          const nodes = g.nodes
          for (let i = 0; i < nodes.length; i++) { nodes[i].x = buf[2 * i]; nodes[i].y = buf[2 * i + 1] }
          recomputeHulls()
          dirtyRef.current = true
        } else if (data.type === 'done') {
          const buf = data.buf as Float32Array
          const nodes = g.nodes
          for (let i = 0; i < nodes.length; i++) { nodes[i].x = buf[2 * i]; nodes[i].y = buf[2 * i + 1] }
          recomputeHulls()
          dirtyRef.current = true
          fitToView()
        }
    }

    api.graphCooccurrence(
      { node_limit: nodeLimit === 0 ? 0 : nodeLimit, min_weight: 1, label: labelFilter !== 'ALL' ? labelFilter : undefined },
      controller.signal,
    )
      .then((r: any) => {
        if (cancelled) return
        // One-pass node map (O(E), was O(E^2) via per-endpoint r.edges.find)
        const nodeInfo = new Map<string, { text: string; label: string }>()
        const cleanEdges: GraphEdge[] = []
        for (const e of (r.edges ?? [])) {
          const s = String(e.source), t = String(e.target)
          if (!nodeInfo.has(s)) nodeInfo.set(s, { text: e.source_text ?? s, label: e.source_label ?? 'MISC' })
          if (!nodeInfo.has(t)) nodeInfo.set(t, { text: e.target_text ?? t, label: e.target_label ?? 'MISC' })
          cleanEdges.push({ source: s, target: t, weight: e.weight })
        }
        const nodes: GraphNode[] = []
        const nodeMap = new Map<string, GraphNode>()
        for (const [id, info] of nodeInfo) {
          const n: GraphNode = { id, text: info.text, label: info.label, x: (Math.random() - 0.5) * 200, y: (Math.random() - 0.5) * 200, vx: 0, vy: 0, weight: 0, cluster: 0 }
          nodes.push(n); nodeMap.set(id, n)
        }
        for (const e of cleanEdges) { nodeMap.get(e.source)!.weight += e.weight; nodeMap.get(e.target)!.weight += e.weight }
        const maxNodeW = nodes.reduce((m, n) => Math.max(m, n.weight), 0) || 1
        maxNodeWRef.current = maxNodeW

        // adjacency for highlight
        const adj = new Map<string, Set<string>>()
        for (const e of cleanEdges) {
          if (!adj.has(e.source)) adj.set(e.source, new Set())
          if (!adj.has(e.target)) adj.set(e.target, new Set())
          adj.get(e.source)!.add(e.target)
          adj.get(e.target)!.add(e.source)
        }
        adjRef.current = adj

        const g = { nodes, edges: cleanEdges }
        graphRef.current = g
        setGraphData(g)
        if (worker) {
          worker.postMessage({
            type: 'start',
            nodes: nodes.map(n => ({ id: n.id, weight: n.weight })),
            edges: cleanEdges,
            width: dimRef.current.w,
            height: dimRef.current.h,
          })
        } else {
          // Fallback: run the same layout on the main thread (UI may briefly
          // freeze on very large graphs, but the graph still renders).
          stopFallback = runLayout(
            nodes as any,
            cleanEdges as any,
            dimRef.current.w,
            dimRef.current.h,
            {
              onInit: (clusters, count) => applyMessage({ type: 'init', clusters, count }),
              onTick: (buf) => applyMessage({ type: 'tick', buf }),
              onDone: (buf) => applyMessage({ type: 'done', buf }),
            },
          )
        }
      })
      .catch((e: any) => { if (!cancelled && e?.name !== 'AbortError') setGraphError(true) })
    api.graphStats(controller.signal)
      .then((s: any) => { if (!cancelled) setStats(s) })
      .catch(() => { if (!cancelled) setStats(null) })

    return () => {
      cancelled = true
      controller.abort()
      if (watchdog) clearTimeout(watchdog)
      worker?.terminate()
      stopFallback?.()
      if (workerRef.current === worker) workerRef.current = null
    }
  }, [nodeLimit, labelFilter, recomputeHulls])

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
      if (workerRef.current) workerRef.current.postMessage({ type: 'resize', width: w, height: h })
      else reheat(w, h)
      // keep the whole graph framed (unless the user has manually panned/zoomed)
      if (!userZoomedRef.current) fitToView()
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [graphData])

  // Fit the whole graph into the viewport. More nodes => smaller scale (zoom out)
  // so the overview always shows everything without changing the layout itself.
  const fitToView = () => {
    const g = graphRef.current
    const canvas = canvasRef.current
    const zb = zoomRef.current
    if (!g || !canvas || !zb || g.nodes.length === 0) return
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const n of g.nodes) {
      if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x
      if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y
    }
    const { w: W, h: H } = dimRef.current
    const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY)
    const pad = 48
    let k = Math.min((W - pad * 2) / bw, (H - pad * 2) / bh)
    k = Math.max((zoomRef.current as any)?.scaleExtent?.()[0] ?? 0.2, Math.min((zoomRef.current as any)?.scaleExtent?.()[1] ?? 8, k))
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2
    const tx = W / 2 - k * cx, ty = H / 2 - k * cy
    select(canvas).call(zb.transform, zoomIdentity.translate(tx, ty).scale(k))
  }

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
      .on('zoom', (event) => { transformRef.current = event.transform; if (event.sourceEvent) userZoomedRef.current = true; dirtyRef.current = true })
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
      const onlyCluster = focusClusterRef.current

      // ── Cluster hull regions ──
      for (const [c, pts] of hullsRef.current) {
        if (visible && !visible.has(clusterAnyNode(c))) continue
        if (onlyCluster != null && c !== onlyCluster) continue
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
        if (onlyCluster != null) {
          const inFocus = a.cluster === onlyCluster && b.cluster === onlyCluster
          if (!inFocus) alpha = Math.min(alpha, 0.04)
        }
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
        let dim = (highlight && !highlight.has(n.id)) ? 0.18 : 1
        if (onlyCluster != null && n.cluster !== onlyCluster) dim = 0.07

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
        const inOtherCluster = onlyCluster != null && n.cluster !== onlyCluster
        const showLabel = (n.id === isHov || n.id === isSel) || (!inOtherCluster && (topLabelRef.current.has(n.id) || (highlight && highlight.has(n.id) && !isActive)))
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
    setSidebarArticles([]); setSidebarRelations([]); setSidebarLoading(true); setNodeDetail(null)
    api.entityArticles(found.id, 15)
      .then((r: any) => setSidebarArticles(r.articles ?? []))
      .catch(() => setSidebarArticles([]))
    api.entityRelations(found.id, 100)
      .then((r: any) => setSidebarRelations(r.relationships ?? []))
      .catch(() => setSidebarRelations([]))
      .finally(() => setSidebarLoading(false))
    api.entityNode(found.id)
      .then((r: any) => setNodeDetail(r ?? null))
      .catch(() => setNodeDetail(null))
  }, [hitTest])

  const legendEntries: { label: string; fg: Rgb; density: number; clusterIndex?: number }[] = (() => {
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
      clusterIndex: c.index,
    }))
  })()

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 40, background: '#f5f5f0' }}>
      {/* Floating control bar */}
      <div style={{ position: 'absolute', top: 92, left: 12, zIndex: 6, background: 'rgba(245,245,240,0.94)', border: '1px solid #0a0a0a', boxShadow: '3px 3px 0 #0a0a0a', padding: '8px 10px', maxWidth: 'calc(100% - 24px)' }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', flexWrap: 'wrap', marginBottom: 8 }}>
          <h2 style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.18em', margin: 0 }}>ENTITY CO-OCCURRENCE GRAPH</h2>
          <span style={{ fontSize: 9, color: '#555550', letterSpacing: '0.1em' }}>FORCE-DIRECTED · AUTO-CLUSTERED</span>
          {stats && (
            <span style={{ display: 'flex', gap: 16, fontSize: 9, letterSpacing: '0.1em' }}>
              {[{ l: 'NODES', v: stats.nodes }, { l: 'EDGES', v: stats.edges }, { l: 'TRIPLES', v: stats.triples }].map(s => (
                <span key={s.l}>
                  <span style={{ color: '#555550' }}>{s.l}: </span>
                  <span style={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{s.v?.toLocaleString()}</span>
                </span>
              ))}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
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
            <span style={{ color: '#555550', letterSpacing: '0.08em' }}>NODES</span>
            <input
              type="range"
              min={50}
              max={stats?.nodes ?? 6000}
              value={nodeLimit === 0 ? (stats?.nodes ?? 6000) : nodeLimit}
              onChange={e => {
                const max = stats?.nodes ?? 6000
                const v = Number(e.target.value)
                setNodeLimit(v >= max ? 0 : v)
              }}
              style={{ accentColor: '#0a0a0a', width: 120 }}
            />
            <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, width: 42 }}>{nodeLimit === 0 ? 'ALL' : nodeLimit}</span>
          </div>

          {selected && (
            <button onClick={() => setFocusId(focusId ? null : selected.id)}
              style={{ padding: '4px 10px', border: '1px solid #0a0a0a', background: focusId ? '#0a0a0a' : 'transparent', color: focusId ? '#f5f5f0' : '#0a0a0a', fontSize: 8, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>
              {focusId ? 'SHOW ALL' : 'ISOLATE'}
            </button>
          )}
        </div>
      </div>

      {/* Full-bleed canvas */}
      <div ref={wrapRef} style={{ position: 'absolute', top: 88, left: 0, right: 0, bottom: 0 }}>
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: '100%', display: 'block', cursor: hovered ? 'pointer' : 'grab' }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => { hoveredRef.current = null; setHovered(null); dirtyRef.current = true }}
          onClick={handleClick}
        />
      </div>

      {graphError && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <EmptyState msg="COULD NOT REACH API — CHECK BACKEND CONNECTION" />
        </div>
      )}
      {!graphData && !graphError && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, letterSpacing: '0.2em', color: '#555550' }}>
          COMPUTING LAYOUT<span className="cursor-blink">_</span>
        </div>
      )}

      {/* Legend */}
      <div style={{
        position: 'absolute', bottom: 12, left: 12, zIndex: 6,
        background: 'rgba(245,245,240,0.95)', border: '2px solid #0a0a0a',
        padding: '10px 12px', fontSize: 10, letterSpacing: '0.08em', maxHeight: 320, overflowY: 'auto',
        boxShadow: '3px 3px 0 #0a0a0a',
      }}>
        <div style={{ fontWeight: 700, marginBottom: 6, letterSpacing: '0.15em' }}>SHAPE = TYPE</div>
        <div style={{ marginBottom: 3 }}>● PERSON (PER)</div>
        <div style={{ marginBottom: 3 }}>■ ORGANISATION (ORG)</div>
        <div style={{ marginBottom: 6 }}>▲ LOCATION (LOC)</div>
        <div style={{ fontWeight: 700, marginBottom: 6, letterSpacing: '0.15em', borderTop: '1px dashed #0a0a0a', paddingTop: 6 }}>
          FILL = {COLOR_MODE_LABELS[colorMode]}
          {colorMode === 'cluster' && <span style={{ fontWeight: 400, opacity: 0.6 }}> · CLICK TO ISOLATE</span>}
        </div>
        {colorMode === 'cluster' && focusCluster != null && (
          <div
            onClick={() => setFocusCluster(null)}
            style={{ cursor: 'pointer', fontWeight: 700, marginBottom: 6, letterSpacing: '0.1em', textDecoration: 'underline' }}
          >◀ SHOW ALL CLUSTERS</div>
        )}
        {legendEntries.map((le, i) => {
          const isClusterSel = le.clusterIndex != null && le.clusterIndex === focusCluster
          const clickable = le.clusterIndex != null
          return (
            <div
              key={i}
              onClick={clickable ? () => setFocusCluster(isClusterSel ? null : le.clusterIndex!) : undefined}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3,
                cursor: clickable ? 'pointer' : 'default',
                background: isClusterSel ? '#0a0a0a' : 'transparent',
                color: isClusterSel ? '#f5f5f0' : '#0a0a0a',
                padding: clickable ? '2px 4px' : 0,
                marginLeft: clickable ? -4 : 0,
                marginRight: clickable ? -4 : 0,
              }}
            >
              <ColorSwatch fg={le.fg} density={le.density} size={18} />
              <span>{le.label}</span>
              {isClusterSel && <span style={{ marginLeft: 'auto', fontWeight: 700 }}>◀</span>}
            </div>
          )
        })}
        {colorMode === 'cluster' && clusterInfoRef.current.length > 12 && (
          <div style={{ marginTop: 4, color: '#555550', fontSize: 9 }}>+{clusterInfoRef.current.length - 12} more</div>
        )}
      </div>

      {focusCluster != null && (() => {
        const ci = clusterInfoRef.current.find(x => x.index === focusCluster)
        if (!ci) return null
        return createPortal(
          <div style={{ position: 'fixed', top: 72, left: '50%', transform: 'translateX(-50%)', zIndex: 60, background: 'rgba(245,245,240,0.96)', border: '2px solid #0a0a0a', boxShadow: '3px 3px 0 #0a0a0a', padding: '7px 12px', display: 'flex', alignItems: 'center', gap: 12, fontSize: 10, letterSpacing: '0.1em', maxWidth: 'calc(100% - 24px)', flexWrap: 'wrap', justifyContent: 'center' }}>
            <span style={{ fontWeight: 700 }}>CLUSTER {ci.index + 1}</span>
            <span style={{ height: 14, width: 1, background: '#0a0a0a' }} />
            <span style={{ fontWeight: 700 }}>{ci.repr}</span>
            <span style={{ color: '#555550' }}>{ci.count} ENTITIES · ISOLATED</span>
            <button onClick={() => setFocusCluster(null)} style={{ padding: '3px 8px', border: '1px solid #0a0a0a', background: '#0a0a0a', color: '#f5f5f0', fontSize: 8, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', fontWeight: 700, cursor: 'pointer' }}>SHOW ALL</button>
          </div>,
          document.body
        )
      })()}

      {!everClicked && !hovered && (
        <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 6, fontSize: 8, letterSpacing: '0.12em', color: '#555550', pointerEvents: 'none', background: 'rgba(245,245,240,0.8)', padding: '4px 8px', border: '1px solid #d4d4cc' }}>
          SCROLL = ZOOM · DRAG = PAN · CLICK A NODE ▶
        </div>
      )}

      {hovered && (
        <div style={{ position: 'absolute', bottom: 12, right: 12, zIndex: 6, background: '#0a0a0a', color: '#f5f5f0', fontSize: 10, padding: '5px 10px', letterSpacing: '0.08em', pointerEvents: 'none' }}>
          {hovered.text} · {hovered.label} · {hovered.weight} co-occ. · {hovered.cluster + 1 >= 0 ? `CLUSTER ${hovered.cluster + 1}` : ''}
        </div>
      )}

      {selected && createPortal(
        <div style={{ position: 'fixed', inset: 0, zIndex: 100, display: 'flex', justifyContent: 'flex-end', pointerEvents: 'all' }}
          onClick={() => { setSelected(null); setNodeDetail(null) }}>
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
                {nodeDetail?.description && (
                  <div style={{ fontSize: 10, marginTop: 6, lineHeight: 1.35, opacity: 0.85 }}>
                    {nodeDetail.description}
                  </div>
                )}
                {nodeDetail?.wikidata_url && (
                  <a
                    href={nodeDetail.wikidata_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: 9, marginTop: 6, letterSpacing: '0.08em', color: '#f5f5f0', textDecoration: 'underline' }}
                  >
                    VIEW ON WIKIDATA ↗
                  </a>
                )}
              </div>
               <button onClick={() => { setSelected(null); setNodeDetail(null) }} style={{ fontSize: 20, background: 'none', border: 'none', cursor: 'pointer', color: '#f5f5f0', padding: 2, lineHeight: 1, flexShrink: 0 }}>×</button>
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
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#0a0a0a', marginLeft: 6 }}>{isSubj ? '→' : '←'}</span>
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
        </div>,
        document.body
      )}
    </div>
  )
}

function ColorSwatch({ fg, density, size = 18 }: { fg: Rgb; density: number; size?: number }) {
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
