// layoutCore.ts — shared knowledge-graph layout (Louvain + d3-force).
// Used by the Web Worker AND by a main-thread fallback so the graph always
// renders even if the worker cannot be constructed.

import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide, forceX, forceY } from 'd3-force'
import louvain from 'louvain'

export interface LNode { id: string; weight: number; x: number; y: number; vx: number; vy: number; cluster: number }
export interface LEdge { source: string; target: string; weight: number }

let currentSim: any = null
let currentK = 1
let currentAnchors = new Map<number, { x: number; y: number }>()

// Cluster anchors laid out on a circle around the centre (as in the original
// design) so the layout behaves exactly as it did before the spread tweaks.
function buildAnchors(K: number, W: number, H: number) {
  const R = Math.min(W, H) * 0.32
  const m = new Map<number, { x: number; y: number }>()
  for (let k = 0; k < K; k++) {
    const ang = (k / Math.max(1, K)) * Math.PI * 2 - Math.PI / 2
    m.set(k, { x: W / 2 + R * Math.cos(ang), y: H / 2 + R * Math.sin(ang) })
  }
  currentAnchors = m
}

function pack(nodes: LNode[]): Float32Array {
  const buf = new Float32Array(nodes.length * 2)
  for (let i = 0; i < nodes.length; i++) { buf[2 * i] = nodes[i].x; buf[2 * i + 1] = nodes[i].y }
  return buf
}

export function runLayout(
  nodes: LNode[],
  edges: LEdge[],
  W: number,
  H: number,
  cb: {
    onInit: (clusters: Record<string, number>, count: number) => void
    onTick: (positions: Float32Array) => void
    onDone: (positions: Float32Array) => void
  },
): () => void {
  const maxW = edges.reduce((m, e) => Math.max(m, e.weight), 0) || 1
  const maxNodeW = nodes.reduce((m, n) => Math.max(m, n.weight), 0) || 1

  // ── Community detection (Louvain) ──
  let clusterOf: Record<string, number> = {}
  try {
    const raw = (louvain as any).jLouvain().nodes(nodes.map(n => n.id)).edges(edges)() as Record<string, number>
    clusterOf = raw
  } catch {
    nodes.forEach((n, i) => { clusterOf[n.id] = 0 })
  }
  const rawUnique = [...new Set(Object.values(clusterOf))]
  const rawIdx = new Map(rawUnique.map((c, i) => [c, i]))
  nodes.forEach(n => { n.cluster = rawIdx.get(clusterOf[n.id]) ?? 0 })

  // Renumber clusters contiguously from 0 (keep every Louvain community).
  const unique = [...new Set(nodes.map(n => n.cluster))]
  const idx = new Map(unique.map((c, i) => [c, i]))
  nodes.forEach(n => { n.cluster = idx.get(n.cluster) ?? 0 })
  currentK = unique.length
  buildAnchors(currentK, W, H)

  // Seed positions near each cluster's anchor (matches original behaviour).
  for (const n of nodes) {
    const a = currentAnchors.get(n.cluster)!
    n.x = a.x + (Math.random() - 0.5) * 80
    n.y = a.y + (Math.random() - 0.5) * 80
  }

  const clustersOut: Record<string, number> = {}
  nodes.forEach(n => { clustersOut[n.id] = n.cluster })
  cb.onInit(clustersOut, currentK)

  // Original force-directed layout (restored): all edges drive the simulation,
  // communities gather around centre-circle anchors. Auto-fit zoom frames it.
  const nr = (d: any) => 5 + (d.weight / (maxNodeW || 1)) * 14 + 3
  currentSim = forceSimulation(nodes as any)
    .force('link', forceLink(edges as any).id((d: any) => d.id)
      .distance((d: any) => 28 + (1 - d.weight / maxW) * 64)
      .strength((d: any) => 0.05 + (d.weight / maxW) * 0.5))
    .force('charge', forceManyBody().strength(-160).distanceMax(320).theta(0.9))
    .force('collide', forceCollide().radius((d: any) => nr(d)).strength(0.85))
    .force('center', forceCenter(W / 2, H / 2))
    .force('x', forceX((d: any) => currentAnchors.get((d as any).cluster)!.x).strength(0.06))
    .force('y', forceY((d: any) => currentAnchors.get((d as any).cluster)!.y).strength(0.06))
  currentSim.velocityDecay(0.42).alpha(1).alphaDecay(0.08).alphaMin(0.01)
  currentSim.stop()
  // Stream the simulation live so the UI stays responsive (even at 100k+ edges).
  currentSim.on('tick', () => cb.onTick(pack(nodes)))
  currentSim.on('end', () => cb.onDone(pack(nodes)))
  currentSim.restart()

  return () => { currentSim?.stop() }
}

export function reheat(W: number, H: number) {
  if (!currentSim) return
  buildAnchors(currentK, W, H)
  currentSim.force('center', forceCenter(W / 2, H / 2))
  currentSim.force('x', forceX((d: any) => currentAnchors.get((d as any).cluster)!.x).strength(0.06))
  currentSim.force('y', forceY((d: any) => currentAnchors.get((d as any).cluster)!.y).strength(0.06))
  currentSim.alpha(0.12).alphaDecay(0.08).alphaMin(0.005).restart()
}
