import { http } from './request'

export interface UploadDocData {
  filename: string
  path: string
  size: number
}

export interface IndexStatsData {
  indexed: number
  skipped: number
  metadata_updated: number
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

export type AskSseEvent = {
  type: string
  stage?: string
  status?: string
  step?: string
  delta?: string
  original_query?: string
  optimized_query?: string
  fallback?: boolean
  query?: string
  total?: number
  hits?: SearchHit[]
  answer?: string
  message?: string
  ok?: boolean
  code?: string
  cancelled?: boolean
  [key: string]: unknown
}

function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || '/api'
}

/**
 * 调用 /docs/ask（SSE）。axios 不适合 SSE，这里用 fetch 读流。
 * 若传输层意外断开且后端未能发出业务 done，会合成 stream_interrupted 兜底事件。
 */
export async function askDocs(
  params: SearchParams,
  onEvent: (event: AskSseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token')
  const response = await fetch(`${getApiBaseUrl()}/docs/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(params),
    signal,
  })

  const accessToken = response.headers.get('x-access-token')
  if (accessToken) {
    localStorage.setItem('token', accessToken)
  }

  if (response.status === 401) {
    localStorage.removeItem('token')
    if (!['/login', '/register'].includes(window.location.pathname)) {
      window.location.replace('/login')
    }
    throw new Error('未登录或登录已过期')
  }

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const body = (await response.json()) as { message?: string }
      if (body?.message) message = body.message
    } catch {
      // ignore
    }
    throw new Error(message)
  }

  if (!response.body) {
    throw new Error('浏览器不支持流式读取')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let sawDone = false

  const dispatchRaw = (raw: string) => {
    try {
      const event = JSON.parse(raw) as AskSseEvent
      if (event.type === 'done') sawDone = true
      onEvent(event)
    } catch {
      // 忽略单条解析失败
    }
  }

  const flushPart = (part: string) => {
    const lines = part.split('\n')
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data:')) continue
      const raw = trimmed.slice(5).trim()
      if (!raw) continue
      dispatchRaw(raw)
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        flushPart(part)
      }
    }

    // 读到流结束时再扫一遍尾部缓冲
    buffer += decoder.decode()
    if (buffer.trim()) {
      flushPart(buffer)
    }
  } catch (error) {
    if (signal?.aborted || (error as Error)?.name === 'AbortError') {
      throw error
    }
    // 读流异常且尚未收到 done：合成断连兜底
    if (!sawDone) {
      onEvent({
        type: 'error',
        stage: 'connection',
        code: 'stream_interrupted',
        message: '连接已断开，请重试',
      })
      onEvent({ type: 'done', ok: false, code: 'stream_interrupted' })
      return
    }
    throw error
  }

  // 用户主动取消：不合成错误提示
  if (signal?.aborted) {
    return
  }

  // 传输正常结束，但始终没有业务 done → 后端可能硬崩/被代理掐断
  if (!sawDone) {
    onEvent({
      type: 'error',
      stage: 'connection',
      code: 'stream_interrupted',
      message: '连接已断开，请重试',
    })
    onEvent({ type: 'done', ok: false, code: 'stream_interrupted' })
  }
}
