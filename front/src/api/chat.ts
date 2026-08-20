import { http } from './request'

export interface ChatSession {
  thread_id: string
  title: string
  created_at: string
}

export type MemoryChatSseEvent = {
  type: string
  stage?: string
  status?: string
  delta?: string
  answer?: string
  items?: string[]
  data?: string
  message?: string
  ok?: boolean
  code?: string
  cancelled?: boolean
  [key: string]: unknown
}

export function createChatSession(title?: string) {
  return http.post<ChatSession>('/chat/sessions', title ? { title } : {})
}

export function listChatSessions() {
  return http.get<ChatSession[]>('/chat/sessions')
}

export function deleteChatSession(threadId: string) {
  return http.delete<null>(`/chat/sessions/${threadId}`)
}

function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || '/api'
}

/** SSE：/chat 记忆对话 */
export async function memoryChat(
  params: { thread_id: string; message: string },
  onEvent: (event: MemoryChatSseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token')
  const response = await fetch(`${getApiBaseUrl()}/chat`, {
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
      const event = JSON.parse(raw) as MemoryChatSseEvent
      if (event.type === 'done') sawDone = true
      onEvent(event)
    } catch {
      // ignore
    }
  }

  const flushPart = (part: string) => {
    for (const line of part.split('\n')) {
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
      for (const part of parts) flushPart(part)
    }
    buffer += decoder.decode()
    if (buffer.trim()) flushPart(buffer)
  } catch (error) {
    if (signal?.aborted || (error as Error)?.name === 'AbortError') {
      throw error
    }
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

  if (signal?.aborted) return

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
