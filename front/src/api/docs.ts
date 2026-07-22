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

export function uploadDoc(file: File) {
  const form = new FormData()
  form.append('file', file)
  return http.post<UploadDocData>('/docs/upload', form, {
    timeout: 60_000,
  })
}

export function indexDocs(rebuild = false) {
  return http.post<IndexStatsData>(
    '/docs/index',
    undefined,
    {
      params: { rebuild },
      timeout: 300_000,
    },
  )
}
