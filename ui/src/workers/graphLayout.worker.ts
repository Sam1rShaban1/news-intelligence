// graphLayout.worker.ts — off-main-thread layout for the knowledge graph.
// Delegates the actual work to layoutCore so the same code can also run on the
// main thread as a fallback. Streams node positions back via transferables.

import { runLayout, reheat } from './layoutCore'

const ctx: any = self

ctx.onmessage = (ev: MessageEvent) => {
  const msg = ev.data
  if (msg.type === 'start') {
    runLayout(
      msg.nodes,
      msg.edges,
      msg.width,
      msg.height,
      {
        onInit: (clusters, count) => ctx.postMessage({ type: 'init', clusters, count }),
        onTick: (buf) => ctx.postMessage({ type: 'tick', buf }, [buf.buffer]),
        onDone: (buf) => ctx.postMessage({ type: 'done', buf }, [buf.buffer]),
      },
    )
  } else if (msg.type === 'resize') {
    reheat(msg.width, msg.height)
  }
}
