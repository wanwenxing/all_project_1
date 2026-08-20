import {
  createChatSession,
  deleteChatSession,
  listChatSessions,
  memoryChat,
  type ChatSession,
  type MemoryChatSseEvent,
} from '@/api/chat'
import {
  Button,
  Card,
  Empty,
  Input,
  Space,
  Tag,
  Typography,
  message,
} from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'

const { Paragraph, Text, Title } = Typography
const { TextArea } = Input

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
}

type WindowState = {
  thread_id: string
  title: string
  messages: ChatMessage[]
  input: string
  sending: boolean
  status: string
}

function uid() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export default function MemoryChatPage() {
  const [windows, setWindows] = useState<WindowState[]>([])
  const [loading, setLoading] = useState(false)
  const abortMap = useRef<Map<string, AbortController>>(new Map())

  const refreshSessions = useCallback(async () => {
    setLoading(true)
    try {
      const sessions = await listChatSessions()
      setWindows((prev) => {
        const byId = new Map(prev.map((w) => [w.thread_id, w]))
        return sessions.map((s: ChatSession) => {
          const existing = byId.get(s.thread_id)
          return (
            existing || {
              thread_id: s.thread_id,
              title: s.title,
              messages: [],
              input: '',
              sending: false,
              status: '',
            }
          )
        })
      })
    } catch {
      // axios 拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshSessions()
    return () => {
      abortMap.current.forEach((c) => c.abort())
      abortMap.current.clear()
    }
  }, [refreshSessions])

  const addWindow = async () => {
    try {
      const session = await createChatSession()
      setWindows((prev) => [
        ...prev,
        {
          thread_id: session.thread_id,
          title: session.title,
          messages: [
            {
              id: uid(),
              role: 'system',
              content:
                '同一账号下，可在本窗口说「记住…」写入长期记忆；换到其它窗口提问，仍可召回。',
            },
          ],
          input: '',
          sending: false,
          status: '',
        },
      ])
    } catch {
      // handled
    }
  }

  const removeWindow = async (threadId: string) => {
    abortMap.current.get(threadId)?.abort()
    abortMap.current.delete(threadId)
    try {
      await deleteChatSession(threadId)
    } catch {
      // ignore
    }
    setWindows((prev) => prev.filter((w) => w.thread_id !== threadId))
  }

  const patchWindow = (threadId: string, patch: Partial<WindowState>) => {
    setWindows((prev) =>
      prev.map((w) => (w.thread_id === threadId ? { ...w, ...patch } : w)),
    )
  }

  const send = async (threadId: string) => {
    const win = windows.find((w) => w.thread_id === threadId)
    if (!win) return
    const text = win.input.trim()
    if (!text || win.sending) return

    const userMsg: ChatMessage = { id: uid(), role: 'user', content: text }
    const assistantId = uid()
    patchWindow(threadId, {
      input: '',
      sending: true,
      status: '思考中…',
      messages: [
        ...win.messages,
        userMsg,
        { id: assistantId, role: 'assistant', content: '' },
      ],
    })

    const controller = new AbortController()
    abortMap.current.get(threadId)?.abort()
    abortMap.current.set(threadId, controller)

    const applyAssistant = (content: string | ((prev: string) => string)) => {
      setWindows((prev) =>
        prev.map((w) => {
          if (w.thread_id !== threadId) return w
          return {
            ...w,
            messages: w.messages.map((m) => {
              if (m.id !== assistantId) return m
              const next =
                typeof content === 'function' ? content(m.content) : content
              return { ...m, content: next }
            }),
          }
        }),
      )
    }

    try {
      await memoryChat(
        { thread_id: threadId, message: text },
        (event: MemoryChatSseEvent) => {
          if (event.type === 'memory_hits' && Array.isArray(event.items)) {
            const tip = `【长期记忆召回】\n${event.items.map((i) => `· ${i}`).join('\n')}`
            setWindows((prev) =>
              prev.map((w) => {
                if (w.thread_id !== threadId) return w
                const withoutEmptyAssistant = w.messages.filter(
                  (m) => !(m.id === assistantId && !m.content),
                )
                const assistant =
                  w.messages.find((m) => m.id === assistantId) || {
                    id: assistantId,
                    role: 'assistant' as const,
                    content: '',
                  }
                return {
                  ...w,
                  status: `召回记忆 ${event.items!.length} 条`,
                  messages: [
                    ...withoutEmptyAssistant.filter((m) => m.id !== assistantId),
                    { id: uid(), role: 'system', content: tip },
                    assistant,
                  ],
                }
              }),
            )
          } else if (event.type === 'memory_saved' && event.data) {
            message.success(`已写入长期记忆：${event.data}`)
            patchWindow(threadId, { status: '已写入长期记忆' })
          } else if (event.type === 'answer_delta' && event.delta) {
            applyAssistant((prev) => prev + event.delta)
            patchWindow(threadId, { status: '生成中…' })
          } else if (event.type === 'answer_done' && typeof event.answer === 'string') {
            applyAssistant(event.answer)
          } else if (event.type === 'error' && event.message && !event.cancelled) {
            applyAssistant((prev) => prev || `出错：${event.message}`)
            message.error(String(event.message))
          } else if (event.type === 'done') {
            patchWindow(threadId, { sending: false, status: '' })
          }
        },
        controller.signal,
      )
    } catch (error) {
      if ((error as Error)?.name !== 'AbortError') {
        applyAssistant((prev) => prev || '请求失败，请重试')
      }
    } finally {
      patchWindow(threadId, { sending: false, status: '' })
      abortMap.current.delete(threadId)
    }
  }

  return (
    <div>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <div>
          <Title level={4} style={{ marginBottom: 8 }}>
            记忆对话（多窗口）
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>
            每个窗口是独立短期会话（thread）；同一登录用户共享长期记忆（Store + 本地
            BGE）。在窗口 A 说「记住我喜欢 5G 套餐」，再到窗口 B 问「我喜欢什么？」验证跨窗口记忆。
          </Paragraph>
          <Space>
            <Button type="primary" onClick={() => void addWindow()} loading={loading}>
              新建窗口
            </Button>
            <Button onClick={() => void refreshSessions()}>刷新列表</Button>
            <Tag color="blue">DeepSeek + 本地 BGE</Tag>
          </Space>
        </div>

        {windows.length === 0 ? (
          <Empty description="还没有窗口，点击「新建窗口」开始" />
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: 16,
            }}
          >
            {windows.map((win) => (
              <Card
                key={win.thread_id}
                size="small"
                title={win.title}
                extra={
                  <Button
                    type="link"
                    danger
                    size="small"
                    onClick={() => void removeWindow(win.thread_id)}
                  >
                    关闭
                  </Button>
                }
                styles={{ body: { padding: 12 } }}
              >
                <div
                  style={{
                    height: 320,
                    overflowY: 'auto',
                    marginBottom: 12,
                    padding: 8,
                    background: '#fafafa',
                    borderRadius: 8,
                  }}
                >
                  {win.messages.map((m) => (
                    <div
                      key={m.id}
                      style={{
                        marginBottom: 8,
                        textAlign:
                          m.role === 'user'
                            ? 'right'
                            : m.role === 'system'
                              ? 'center'
                              : 'left',
                      }}
                    >
                      <div
                        style={{
                          display: 'inline-block',
                          maxWidth: '92%',
                          padding: '6px 10px',
                          borderRadius: 8,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontSize: 13,
                          background:
                            m.role === 'user'
                              ? '#1677ff'
                              : m.role === 'system'
                                ? '#fff7e6'
                                : '#fff',
                          color: m.role === 'user' ? '#fff' : 'rgba(0,0,0,0.88)',
                          border:
                            m.role === 'assistant' ? '1px solid #eee' : undefined,
                        }}
                      >
                        {m.content || (win.sending ? '…' : '')}
                      </div>
                    </div>
                  ))}
                </div>
                {win.status ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {win.status}
                  </Text>
                ) : null}
                <Space.Compact style={{ width: '100%', marginTop: 8 }}>
                  <TextArea
                    value={win.input}
                    autoSize={{ minRows: 1, maxRows: 4 }}
                    placeholder="输入消息，含「记住」可写入长期记忆"
                    disabled={win.sending}
                    onChange={(e) =>
                      patchWindow(win.thread_id, { input: e.target.value })
                    }
                    onPressEnter={(e) => {
                      if (!e.shiftKey) {
                        e.preventDefault()
                        void send(win.thread_id)
                      }
                    }}
                  />
                  <Button
                    type="primary"
                    loading={win.sending}
                    onClick={() => void send(win.thread_id)}
                  >
                    发送
                  </Button>
                </Space.Compact>
              </Card>
            ))}
          </div>
        )}
      </Space>
    </div>
  )
}
