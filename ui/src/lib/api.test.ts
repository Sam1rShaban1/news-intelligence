import { describe, it, expect } from 'vitest'
import { api } from './api'

describe('api URL builders (no network)', () => {
  it('builds a per-article PDF export URL', () => {
    expect(api.articlePdfUrl('42')).toBe('/api/export/articles/42/pdf')
  })

  it('builds a per-story PDF export URL', () => {
    expect(api.storyPdfUrl('7')).toBe('/api/export/stories/7/pdf')
  })

  it('builds a story tabular export URL with format', () => {
    expect(api.exportStoryUrl('7', 'json')).toBe('/api/export/stories/7?format=json')
  })

  it('exposes the expected surface of endpoints', () => {
    const fns = [
      'overview', 'search', 'articles', 'sentimentDist', 'entities', 'graphStats',
      'stories', 'sources', 'createSource', 'alertRules', 'semanticSearch',
      'watchlist', 'entityDossier', 'storyTimeline',
    ]
    for (const f of fns) expect(typeof (api as any)[f]).toBe('function')
  })
})
