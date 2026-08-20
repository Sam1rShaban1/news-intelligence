import { EmptyState } from './Layout'

export interface BarSeries {
  key: string
  color: string
  label: string
}

/** Dependency-free stacked column chart. Robust against empty / malformed data. */
export function MiniStackedBars({
  data,
  series,
  xKey,
  height = 150,
}: {
  data: any[] | null | undefined
  series: BarSeries[]
  xKey?: string
  height?: number
}) {
  if (!data || data.length === 0) return <EmptyState msg="NO DATA" />
  const nums = data.flatMap((d) => series.map((s) => Number(d?.[s.key]) || 0))
  const max = Math.max(1, ...nums)
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height, paddingTop: 4 }}>
        {data.map((d, i) => (
          <div
            key={i}
            title={series.map((s) => `${s.label}: ${Number(d?.[s.key]) || 0}`).join('  ·  ')}
            style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%', gap: 1 }}
          >
            {series.map((s) => {
              const v = Number(d?.[s.key]) || 0
              const pct = (v / max) * 100
              return (
                <div
                  key={s.key}
                  style={{ height: `${pct}%`, background: s.color, minHeight: v > 0 ? 2 : 0 }}
                />
              )
            })}
          </div>
        ))}
      </div>
      {xKey && (
        <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
          {data.map((d, i) => (
            <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 7, color: '#555550', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
              {String(d?.[xKey] ?? '')}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Dependency-free donut chart for a share distribution. */
export function MiniDonut({
  data,
  size = 170,
  stroke = 24,
}: {
  data: { name: string; value: number; color: string }[]
  size?: number
  stroke?: number
}) {
  if (!data || data.length === 0) return <EmptyState msg="NO DATA" />
  const total = data.reduce((s, d) => s + (Number(d.value) || 0), 0)
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ maxWidth: '100%' }}>
      <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#d4d4cc" strokeWidth={stroke} />
        {total > 0 &&
          data.map((d, i) => {
            const frac = (Number(d.value) || 0) / total
            const dash = frac * circ
            const seg = (
              <circle
                key={i}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={d.color}
                strokeWidth={stroke}
                strokeDasharray={`${dash} ${circ - dash}`}
                strokeDashoffset={-offset}
              />
            )
            offset += dash
            return seg
          })}
      </g>
      <text x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="central" style={{ fontSize: 13, fontWeight: 700, fill: '#0a0a0a' }}>
        {total.toLocaleString()}
      </text>
    </svg>
  )
}
