import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'
import { Section, Card, EmptyState, LoadingDots } from '../components/Layout'
import { EntityDrawer } from './Entities'

const LABEL_GLYPHS: Record<string, string> = { PER: '●', ORG: '■', LOC: '◆' }

export function Watchlist() {
  const [items, setItems] = useState<any[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<any>(null)
  const [nodeId, setNodeId] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [formErr, setFormErr] = useState('')

  const load = useCallback(() => {
    setItems(null)
    setError('')
    api.watchlist()
      .then((r: any) => setItems(r.items ?? []))
      .catch((e: any) => setError(String(e.message || e)))
  }, [])

  useEffect(load, [load])

  const remove = async (id: number) => {
    await api.removeWatchlist(id).catch(() => {})
    load()
  }

  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormErr('')
    const id = Number(nodeId)
    if (!id) { setFormErr('ENTITY NODE ID REQUIRED'); return }
    setBusy(true)
    try {
      await api.addWatchlist(id, note.trim() || undefined)
      setNodeId(''); setNote(''); load()
    } catch (e: any) {
      setFormErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <Section title="WATCHLIST" sub={items ? `${items.length} TRACKED` : ''}>
        <Card style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.14em', marginBottom: 10 }}>ADD ENTITY BY NODE ID</div>
          <form onSubmit={add} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <label style={{ fontSize: 8, letterSpacing: '0.12em', color: '#555550' }}>
              NODE ID
              <input value={nodeId} onChange={e => setNodeId(e.target.value)} placeholder="e.g. 42"
                style={{ width: '100%', marginTop: 3, padding: '5px 8px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 10, fontFamily: 'Space Mono, monospace', outline: 'none' }} />
            </label>
            <label style={{ flex: '1 1 160px', fontSize: 8, letterSpacing: '0.12em', color: '#555550' }}>
              NOTE (optional)
              <input value={note} onChange={e => setNote(e.target.value)} placeholder="why tracking?"
                style={{ width: '100%', marginTop: 3, padding: '5px 8px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 10, fontFamily: 'Space Mono, monospace', outline: 'none' }} />
            </label>
            <button type="submit" disabled={busy}
              style={{ padding: '5px 16px', border: '1px solid #0a0a0a', background: '#0a0a0a', color: '#f5f5f0', fontSize: 9, letterSpacing: '0.12em', fontFamily: 'Space Mono, monospace', cursor: 'pointer', fontWeight: 700 }}>
              {busy ? 'ADDING…' : 'ADD'}
            </button>
          </form>
          {formErr && <div style={{ marginTop: 8, fontSize: 9, color: '#a00', letterSpacing: '0.08em' }}>⚠ {formErr}</div>}
          <div style={{ marginTop: 8, fontSize: 8, color: '#555550', letterSpacing: '0.06em' }}>
            TIP: open any entity in the ENTITIES tab and use “ADD TO WATCHLIST”.
          </div>
        </Card>

        {error && <EmptyState msg={error} />}
        {!items ? <LoadingDots /> : items.length === 0 ? <EmptyState msg="NO ENTITIES WATCHED YET" /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {items.map((it: any) => (
              <Card key={it.node_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', cursor: 'pointer' }}
                onClick={() => setSelected({ id: it.node_id, text: it.entity?.text, label: it.entity?.label, mention_count: it.entity?.mention_count, aliases: it.entity?.aliases })}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>
                    {LABEL_GLYPHS[it.entity?.label] ?? '○'} {it.entity?.text ?? `#${it.node_id}`}
                  </div>
                  <div style={{ fontSize: 8, color: '#555550', letterSpacing: '0.06em', marginTop: 2 }}>
                    {it.mentions ?? 0} MENTIONS
                    {it.last_mentioned ? ` · LAST ${it.last_mentioned.slice(0, 10)}` : ''}
                    {it.note ? ` · “${it.note}”` : ''}
                  </div>
                </div>
                {it.entity?.wikidata_url && (
                  <a href={it.entity.wikidata_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                    style={{ fontSize: 8, color: '#0a0a0a', textDecoration: 'underline' }}>WIKIDATA</a>
                )}
                <button onClick={(e) => { e.stopPropagation(); remove(it.node_id) }}
                  style={{ padding: '3px 10px', border: '1px solid #0a0a0a', background: '#f5f5f0', fontSize: 9, letterSpacing: '0.1em', fontFamily: 'Space Mono, monospace', cursor: 'pointer' }}>
                  REMOVE
                </button>
              </Card>
            ))}
          </div>
        )}
      </Section>

      {selected && <EntityDrawer entity={selected} onClose={() => setSelected(null)} onSelectNode={(id) => setSelected({ id })} />}
    </div>
  )
}
