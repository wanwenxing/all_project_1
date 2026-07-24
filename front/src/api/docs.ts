import { http } from './request'

export interface UploadDocData {
  filename: string
  path: string
  size: number
}

export interface IndexStatsData {
  indexed: number
  skipped: number
  removed: number
  chunks: number
}

export interface SearchHit {
  chroma_id: string
  content: string
  distance: number | null
  score: number | null
  document_id: string | null
  chunk_id: string | null
  chunk_index: number | null
  source_path: string | null
  title: string | null
  updated_at: string | null
}

export interface SearchResult {
  query: string
  total: number
  hits: SearchHit[]
}

export interface SearchParams {
  query: string
  top_k?: number
  source_path?: string
  title?: string
  updated_at?: string
}

export function uploadDoc(file: File) {
  const form = new FormData()
  form.append('file', file)
  return http.post<UploadDocData>('/docs/upload', form, {
    timeout: 60_000,
  })
}

export function indexDocs(options?: { path?: string; rebuild?: boolean }) {
  const { path, rebuild = false } = options || {}
  return http.post<IndexStatsData>('/docs/index', undefined, {
    params: {
      rebuild,
      ...(path ? { path } : {}),
    },
    timeout: 300_000,
  })
}

export function searchDocs(params: SearchParams) {
  return http.post<SearchResult>('/docs/search', params, {
    timeout: 60_000,
  })
}
