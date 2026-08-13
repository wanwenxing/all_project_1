import { askDocs, type AskSseEvent, type SearchHit } from '@/api/docs'
import {
  Button,
  Collapse,
  Form,
  Input,
  InputNumber,
  List,
  Space,
  Typography,
  message,
} from 'antd'
import { CloseOutlined, CommentOutlined, ClearOutlined } from '@ant-design/icons'
import { useEffect, useRef, useState } from 'react'

const { Text } = Typography

type AskFormValues = {
  top_k?: number
  source_path?: string
  title?: string
  updated_at?: string
}

type ChatRole = 'user' | 'assistant' | 'system'

type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  streaming?: boolean
  hits?: SearchHit[]
  retrieveStep?: string
}

const RETRIEVE_STEP_LABELS: Record<string, string> = {
  vector: '向量检索',
  keyword: '关键字检索',
  rrf: 'RRF 融合',
  rerank: 'Rerank 精排',
}

function uid(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export default function AskChatWidget() {
  const [open, setOpen] = useState(false)
  const [asking, setAsking] = useState(false)
  const [composer, setComposer] = useState('')
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [askForm] = Form.useForm<AskFormValues>()
  const askAbortRef = useRef<AbortController | null>(null)
  const answerMsgIdRef = useRef<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, asking, open])

  const pushMessage = (msg: ChatMessage) => {
    setChatMessages((prev) => [...prev, msg])
  }

  const updateMessage = (id: string, patch: Partial<ChatMessage>) => {
    setChatMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)))
  }

  const appendToMessage = (id: string, delta: string) => {
    setChatMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + delta } : m)),
    )
  }

  const handleAskEvent = (event: AskSseEvent) => {
    switch (event.type) {
      case 'stage':
        if (event.status === 'start' && event.stage) {
          const label =
            event.stage === 'rewrite'
              ? '正在优化问题…'
              : event.stage === 'retrieve'
                ? '正在检索知识库…'
                : '正在整理回答…'
          pushMessage({ id: uid('sys'), role: 'system', content: label })
          if (event.stage === 'answer' && !answerMsgIdRef.current) {
            const id = uid('assistant')
            answerMsgIdRef.current = id
            pushMessage({ id, role: 'assistant', content: '', streaming: true })
          }
        }
        break
      case 'rewrite_done':
        pushMessage({
          id: uid('sys'),
          role: 'system',
          content: event.fallback
            ? '优化失败，沿用原问题'
            : `已优化为：${event.optimized_query || ''}`,
        })
        break
      case 'retrieve_step': {
        const step = event.step || ''
        const label = RETRIEVE_STEP_LABELS[step] || step || '检索步骤'
        if (event.status === 'start') {
          pushMessage({
            id: uid('sys'),
            role: 'system',
            content: `开始${label}…`,
          })
          break
        }
        if (event.status === 'done') {
          const list = event.hits || []
          pushMessage({
            id: uid('sys'),
            role: 'system',
            content: `${label}完成，命中 ${event.total ?? list.length} 条`,
          })
          if (list.length > 0) {
            pushMessage({
              id: uid(`hits-${step}`),
              role: 'assistant',
              content: `${label}结果`,
              hits: list,
              retrieveStep: step,
            })
          }
        }
        break
      }
      case 'retrieve_done': {
        const list = event.hits || []
        pushMessage({
          id: uid('sys'),
          role: 'system',
          content: `检索收尾：将 ${event.total ?? list.length} 条精排结果送给 LLM`,
        })
        break
      }
      case 'answer_delta':
        if (event.delta && answerMsgIdRef.current) {
          appendToMessage(answerMsgIdRef.current, event.delta)
        }
        break
      case 'answer_done':
        if (answerMsgIdRef.current) {
          updateMessage(answerMsgIdRef.current, {
            content: event.answer || '',
            streaming: false,
          })
        }
        break
      case 'error':
        // fallback 的改写失败默认不打扰；超时 / 断连仍提示用户
        if (
          !event.fallback ||
          event.code === 'llm_timeout' ||
          event.code === 'stream_interrupted'
        ) {
          pushMessage({
            id: uid('sys'),
            role: 'system',
            content: `出错了${event.stage ? `（${event.stage}）` : ''}：${event.message || '未知错误'}`,
          })
        }
        break
      case 'done':
        if (answerMsgIdRef.current) {
          updateMessage(answerMsgIdRef.current, { streaming: false })
        }
        if (event.ok === false) {
          if (event.code === 'llm_timeout' || event.code === 'stream_interrupted') {
            // error 帧已提示，这里只收尾
            break
          }
          pushMessage({ id: uid('sys'), role: 'system', content: '本轮未完成' })
        }
        break
      default:
        break
    }
  }

  const sendAsk = async () => {
    const query = composer.trim()
    if (!query) {
      message.warning('请输入问题')
      return
    }
    if (asking) return

    const values = askForm.getFieldsValue()
    askAbortRef.current?.abort()
    const controller = new AbortController()
    askAbortRef.current = controller
    answerMsgIdRef.current = null

    setAsking(true)
    setComposer('')
    pushMessage({ id: uid('user'), role: 'user', content: query })

    try {
      await askDocs(
        {
          query,
          top_k: values.top_k ?? 2,
          source_path: values.source_path?.trim() || undefined,
          title: values.title?.trim() || undefined,
          updated_at: values.updated_at?.trim() || undefined,
        },
        handleAskEvent,
        controller.signal,
      )
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        pushMessage({ id: uid('sys'), role: 'system', content: '已取消' })
      } else {
        const msg = error instanceof Error ? error.message : '智能检索失败'
        pushMessage({ id: uid('sys'), role: 'system', content: msg })
        message.error(msg)
      }
    } finally {
      setAsking(false)
      askAbortRef.current = null
      answerMsgIdRef.current = null
    }
  }

  const handleCancelAsk = () => {
    askAbortRef.current?.abort()
  }

  const handleClear = () => {
    if (asking) {
      message.warning('请先取消当前请求')
      return
    }
    setChatMessages([])
  }

  return (
    <>
      {open && (
        <div
          className="fixed bottom-24 right-6 z-50 flex w-[min(420px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-blue-100 bg-[#f0f5ff] shadow-2xl"
          style={{ height: 'min(640px, calc(100vh - 7rem))' }}
        >
          <div className="flex items-center justify-between bg-[#1677ff] px-4 py-3 text-white">
            <div>
              <div className="text-sm font-semibold">智能检索</div>
              <div className="text-xs text-white/85">优化问题 · 混合检索 · 回答</div>
            </div>
            <Space size={4}>
              <Button
                type="text"
                size="small"
                icon={<ClearOutlined />}
                onClick={handleClear}
                style={{ color: '#fff' }}
                title="清空会话"
              />
              <Button
                type="text"
                size="small"
                icon={<CloseOutlined />}
                onClick={() => setOpen(false)}
                style={{ color: '#fff' }}
                title="关闭"
              />
            </Space>
          </div>

          <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
            {chatMessages.length === 0 && (
              <div className="mt-10 text-center text-sm text-neutral-400">
                像聊天一样提问，我会先优化问题、检索知识库，再回复你
              </div>
            )}

            {chatMessages.map((msg) => {
              if (msg.role === 'system') {
                return (
                  <div
                    key={msg.id}
                    className="my-2.5 text-center text-xs text-neutral-500"
                  >
                    <span className="inline-block max-w-[85%] rounded bg-black/5 px-2.5 py-1">
                      {msg.content}
                    </span>
                  </div>
                )
              }

              const isUser = msg.role === 'user'
              return (
                <div
                  key={msg.id}
                  className={`mb-3.5 flex items-start gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {!isUser && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-[#1677ff] text-xs text-white">
                      AI
                    </div>
                  )}

                  <div className="max-w-[78%]">
                    <div
                      className={`relative rounded-md px-3 py-2.5 text-[13px] leading-relaxed shadow-sm ${
                        isUser
                          ? 'bg-[#bae0ff] text-neutral-900'
                          : 'bg-white text-neutral-900'
                      }`}
                      style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                    >
                      {msg.content || (msg.streaming ? '…' : '')}
                      {msg.streaming && <span className="ml-0.5 opacity-45">▍</span>}
                    </div>

                    {msg.hits && msg.hits.length > 0 && (
                      <Collapse
                        size="small"
                        className="mt-2 bg-white"
                        items={[
                          {
                            key: 'hits',
                            label: `${msg.retrieveStep ? `${RETRIEVE_STEP_LABELS[msg.retrieveStep] || msg.retrieveStep} · ` : ''}查看 ${msg.hits.length} 条片段`,
                            children: (
                              <List
                                size="small"
                                dataSource={msg.hits}
                                renderItem={(item, index) => (
                                  <List.Item style={{ padding: '8px 0' }}>
                                    <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                      <Text>
                                        #{index + 1} {item.title || '未命名'}
                                        {item.score != null
                                          ? ` · ${item.score.toFixed(3)}`
                                          : ''}
                                      </Text>
                                      <Text type="secondary" style={{ fontSize: 12 }}>
                                        {item.source_path || '-'}
                                      </Text>
                                      <Text style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>
                                        {item.content}
                                      </Text>
                                    </Space>
                                  </List.Item>
                                )}
                              />
                            ),
                          },
                        ]}
                      />
                    )}
                  </div>

                  {isUser && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-[#0958d9] text-xs text-white">
                      我
                    </div>
                  )}
                </div>
              )
            })}
            <div ref={chatEndRef} />
          </div>

          <div className="border-t border-blue-100 bg-white p-3">
            <Collapse
              ghost
              size="small"
              items={[
                {
                  key: 'filters',
                  label: '可选过滤条件',
                  children: (
                    <Form form={askForm} layout="vertical" initialValues={{ top_k: 2 }}>
                      <Form.Item name="source_path" label="路径" className="!mb-2">
                        <Input placeholder="docs/xxx.md" allowClear />
                      </Form.Item>
                      <Form.Item name="title" label="标题" className="!mb-2">
                        <Input placeholder="标题" allowClear />
                      </Form.Item>
                      <Form.Item name="updated_at" label="时间" className="!mb-2">
                        <Input placeholder="2026年6月" allowClear />
                      </Form.Item>
                      <Form.Item name="top_k" label="条数" className="!mb-0">
                        <InputNumber min={1} max={50} className="w-full" />
                      </Form.Item>
                    </Form>
                  ),
                },
              ]}
            />

            <div className="mt-2 flex items-end gap-2">
              <Input.TextArea
                value={composer}
                onChange={(e) => setComposer(e.target.value)}
                placeholder="输入问题，Enter 发送"
                autoSize={{ minRows: 2, maxRows: 4 }}
                className="flex-1"
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault()
                    void sendAsk()
                  }
                }}
              />
              <Space direction="vertical" size={4}>
                <Button type="primary" loading={asking} onClick={() => void sendAsk()}>
                  发送
                </Button>
                <Button disabled={!asking} onClick={handleCancelAsk}>
                  取消
                </Button>
              </Space>
            </div>
          </div>
        </div>
      )}

      <button
        type="button"
        aria-label={open ? '关闭智能检索' : '打开智能检索'}
        onClick={() => setOpen((prev) => !prev)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[#1677ff] text-white shadow-lg transition hover:scale-105 hover:bg-[#0958d9] active:scale-95"
      >
        {open ? <CloseOutlined className="text-xl" /> : <CommentOutlined className="text-xl" />}
      </button>
    </>
  )
}
