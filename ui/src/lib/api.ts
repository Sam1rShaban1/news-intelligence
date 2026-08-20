const BASE = '/api'

async function get<T>(
  path: string,
  params?: Record<string, string | number | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString(), signal ? { signal } : undefined)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function mutate<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(new URL(BASE + path, window.location.origin), {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof data === 'object' && data && 'detail' in data ? String(data.detail) : `HTTP ${res.status}`
    throw new Error(detail)
  }
  return data as T
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
  graphCooccurrence: (
    opts?: { node_limit?: number; limit?: number; min_weight?: number; label?: string },
    signal?: AbortSignal,
  ) => get<any>('/graph/cooccurrence', opts as any, signal),
  graphStats: (signal?: AbortSignal) => get<any>('/graph/stats', undefined, signal),
  stories: (opts?: Record<string, string | number | undefined>) =>
    get<any>('/stories', opts),
  story: (id: string) => get<any>(`/stories/${id}`),
  article: (id: string) => get<any>(`/articles/${id}`),
  health: () => get<any>('/health'),
  sources: (opts?: { enabled?: boolean; include_deleted?: boolean }) =>
    get<any>('/sources', opts as any),
  createSource: (body: { name: string; url: string; rss_url?: string; enabled?: boolean }) =>
    mutate<any>('/sources', 'POST', body),
  updateSource: (id: string, body: Partial<{ name: string; url: string; rss_url?: string; enabled?: boolean }>) =>
    mutate<any>(`/sources/${id}`, 'PATCH', body),
  deleteSource: (id: string) =>
    mutate<any>(`/sources/${id}`, 'DELETE'),
  testSource: (id: string) =>
    mutate<any>(`/sources/${id}/test`, 'POST'),

  // Alerts (Phase 4)
  alertRules: () => get<any>('/alerts/rules'),
  createAlertRule: (body: { name: string; query?: string; entity_node_id?: number; languages?: string[]; min_sentiment?: number }) =>
    mutate<any>('/alerts/rules', 'POST', body),
  deleteAlertRule: (id: number) =>
    mutate<any>(`/alerts/rules/${id}`, 'DELETE'),
  alerts: (opts?: { limit?: number; read?: boolean }) =>
    get<any>('/alerts', opts as any),
  markAlertRead: (id: number) =>
    mutate<any>(`/alerts/${id}/read`, 'POST'),
  markAllAlertsRead: () =>
    mutate<any>('/alerts/read-all', 'POST'),

  // Semantic search + PDF export (Phase 4)
  semanticSearch: (body: { text: string; limit?: number; language?: string }) =>
    mutate<any>('/search/semantic', 'POST', body),
  articlePdfUrl: (id: string) => `${BASE}/export/articles/${id}/pdf`,
  storyPdfUrl: (id: string) => `${BASE}/export/stories/${id}/pdf`,
}
