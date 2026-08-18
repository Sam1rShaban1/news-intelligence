const BASE = '/api'

async function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString())
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export const api = {
  overview: (opts?: { days?: number; interval?: string; language?: string }) =>
    get<any>('/analytics/overview', opts as any),
  search: (opts?: Record<string, string | number | undefined>) =>
    get<any>('/search', opts),
  articles: (opts?: Record<string, string | number | undefined>) =>
    get<any>('/articles', opts),
  sentimentDist: () => get<any>('/sentiment/distribution'),
  sentimentRecent: (limit = 20) => get<any>('/sentiment/recent', { limit }),
  entities: (opts?: Record<string, string | number | undefined>) =>
    get<any>('/entities/nodes', opts),
  entityArticles: (id: string, limit = 10) => get<any>(`/entities/${id}/articles`, { limit }),
  entityRelations: (id: string, limit = 20) => get<any>(`/entities/${id}/relationships`, { limit }),
  entityNode: (id: string) => get<any>(`/entities/nodes/${id}`),
  graphCooccurrence: (opts?: { node_limit?: number; limit?: number; min_weight?: number; label?: string }) =>
    get<any>('/graph/cooccurrence', opts as any),
  graphStats: () => get<any>('/graph/stats'),
  stories: (opts?: Record<string, string | number | undefined>) =>
    get<any>('/stories', opts),
  story: (id: string) => get<any>(`/stories/${id}`),
  article: (id: string) => get<any>(`/articles/${id}`),
  health: () => get<any>('/health'),
}
