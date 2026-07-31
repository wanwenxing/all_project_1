import {
  askDocs,
  indexDocs,
  searchDocs,
  uploadDoc,
  type AskSseEvent,
  type IndexStatsData,
  type SearchHit,
  type UploadDocData,
} from '@/api/docs'
import {
  Button,
  Card,
  Collapse,
  Divider,
  Form,
  Input,
  InputNumber,
  List,
  Space,
  Typography,
  Upload,
  message,
} from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { useEffect, useRef, useState } from 'react'

const { Paragraph, Text } = Typography

type AskFormValues = {
  query: string
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
}

function uid(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export default function Knowledge() {
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [docPath, setDocPath] = useState('')
  const [uploading, setUploading] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [searching, setSearching] = useState(false)
  const [asking, setAsking] = useState(false)
  const [lastUpload, setLastUpload] = useState<UploadDocData | null>(null)
  const [indexStats, setIndexStats] = useState<IndexStatsData | null>(null)
  const [hits, setHits] = useState<SearchHit[]>([])
  const [searchForm] = Form.useForm()
  const [askForm] = Form.useForm()

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [composer, setComposer] = useState('')
  const askAbortRef = useRef<AbortController | null>(null)
  const answerMsgIdRef = useRef<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, asking])

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

  const handleUpload = async () => {
    const raw = fileList[0]?.originFileObj
    if (!raw) {
      message.warning('请先选择要上传的文件')
      return
    }

    setUploading(true)
    try {
      const data = await uploadDoc(raw)
      setLastUpload(data)
      setDocPath(data.path)
      message.success(`已保存到 ${data.path}`)
      setFileList([])
    } catch {
      // 错误提示由 request 拦截器处理
    } finally {
      setUploading(false)
    }
  }

  const handleIndex = async () => {
    const path = docPath.trim()
    if (!path) {
      message.warning('请先上传文件，或填写要索引的文件路径（如 docs/笔记.md）')
      return
    }

    setIndexing(true)
    try {
      const stats = await indexDocs({ path })
      setIndexStats(stats)
      message.success(`已索引 ${path}`)
    } catch {
      // 错误提示由 request 拦截器处理
    } finally {
      setIndexing(false)
    }
  }

  const handleSearch = async (values: AskFormValues) => {
    setSearching(true)
    try {
      const result = await searchDocs({
        query: values.query.trim(),
        top_k: values.top_k ?? 5,
        source_path: values.source_path?.trim() || undefined,
        title: values.title?.trim() || undefined,
        updated_at: values.updated_at?.trim() || undefined,
      })
      setHits(result.hits)
      message.success(`检索完成，共 ${result.total} 条`)
    } catch {
      setHits([])
    } finally {
      setSearching(false)
    }
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
            ? `优化失败，沿用原问题`
            : `已优化为：${event.optimized_query || ''}`,
        })
        break
      case 'retrieve_done': {
        const list = event.hits || []
        pushMessage({
          id: uid('sys'),
          role: 'system',
          content: `检索完成，命中 ${event.total ?? list.length} 条`,
        })
        if (list.length > 0) {
          pushMessage({
            id: uid('hits'),
            role: 'assistant',
            content: '相关知识片段',
            hits: list,
          })
        }
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
        if (!event.fallback) {
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

    const values = askForm.getFieldsValue() as AskFormValues
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
          top_k: values.top_k ?? 5,
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

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="知识库入库">
        <Paragraph>
          上传 <Text code>.md</Text> / <Text code>.txt</Text> 到后端{' '}
          <Text code>docs/</Text>，再对<strong>指定单个文件</strong>执行索引。
        </Paragraph>

        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Upload.Dragger
            accept=".md,.txt,text/markdown,text/plain"
            maxCount={1}
            beforeUpload={() => false}
            fileList={fileList}
            onChange={({ fileList: next }) => setFileList(next)}
          >
            <p className="ant-upload-text">点击或拖拽文件到此处</p>
            <p className="ant-upload-hint">仅支持 Markdown / 纯文本，需先登录</p>
          </Upload.Dragger>

          <Input
            addonBefore="文件路径"
            placeholder="docs/笔记.md"
            value={docPath}
            onChange={(e) => setDocPath(e.target.value)}
            allowClear
          />

          <Space wrap>
            <Button type="default" loading={uploading} onClick={handleUpload}>
              上传文件
            </Button>
            <Button type="primary" loading={indexing} onClick={handleIndex}>
              存储知识库
            </Button>
          </Space>

          {lastUpload && (
            <pre
              style={{
                margin: 0,
                padding: 12,
                background: '#f5f5f5',
                borderRadius: 8,
              }}
            >
              {JSON.stringify(lastUpload, null, 2)}
            </pre>
          )}

          {indexStats && (
            <pre
              style={{
                margin: 0,
                padding: 12,
                background: '#f5f5f5',
                borderRadius: 8,
              }}
            >
              {JSON.stringify(indexStats, null, 2)}
            </pre>
          )}
        </Space>
      </Card>

      <Card title="知识库检索">
        <Paragraph>
          输入关键字做向量检索；可选按 <Text code>source_path</Text> /{' '}
          <Text code>title</Text> / <Text code>updated_at</Text> 精确过滤。
        </Paragraph>

        <Form
          form={searchForm}
          layout="vertical"
          initialValues={{ top_k: 5 }}
          onFinish={handleSearch}
        >
          <Form.Item
            label="关键字"
            name="query"
            rules={[{ required: true, message: '请输入检索关键字' }]}
          >
            <Input.TextArea rows={2} placeholder="例如：友情、团建、职业迷茫" allowClear />
          </Form.Item>

          <Space wrap size="middle" style={{ width: '100%' }} align="start">
            <Form.Item label="文件路径" name="source_path" style={{ minWidth: 240 }}>
              <Input placeholder="docs/好的友情不亚于爱情.md" allowClear />
            </Form.Item>
            <Form.Item label="标题" name="title" style={{ minWidth: 180 }}>
              <Input placeholder="好的友情不亚于爱情" allowClear />
            </Form.Item>
            <Form.Item label="更新时间" name="updated_at" style={{ minWidth: 160 }}>
              <Input placeholder="2026年6月" allowClear />
            </Form.Item>
            <Form.Item label="返回条数" name="top_k" style={{ minWidth: 120 }}>
              <InputNumber min={1} max={50} style={{ width: '100%' }} />
            </Form.Item>
          </Space>

          <Button type="primary" htmlType="submit" loading={searching}>
            检索
          </Button>
        </Form>

        <Divider />

        <List
          locale={{ emptyText: '暂无检索结果' }}
          dataSource={hits}
          renderItem={(item, index) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Text strong>#{index + 1}</Text>
                    <Text>{item.title || '未命名'}</Text>
                    {item.score != null && (
                      <Text type="secondary">score={item.score.toFixed(4)}</Text>
                    )}
                    {item.distance != null && (
                      <Text type="secondary">distance={item.distance.toFixed(4)}</Text>
                    )}
                  </Space>
                }
                description={
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Text type="secondary">
                      {item.source_path || '-'}
                      {item.updated_at ? ` · ${item.updated_at}` : ''}
                      {item.chroma_id ? ` · ${item.chroma_id}` : ''}
                    </Text>
                    <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                      {item.content}
                    </Paragraph>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>

      <Card title="LLM 智能检索" styles={{ body: { padding: 0 } }}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: 560,
            background: '#ededed',
          }}
        >
          <div style={{ flex: 1, overflow: 'auto', padding: '16px 12px' }}>
            {chatMessages.length === 0 && (
              <div style={{ textAlign: 'center', color: '#999', marginTop: 48 }}>
                像聊天一样提问，我会先优化问题、检索知识库，再回复你
              </div>
            )}

            {chatMessages.map((msg) => {
              if (msg.role === 'system') {
                return (
                  <div
                    key={msg.id}
                    style={{
                      textAlign: 'center',
                      margin: '10px 0',
                      fontSize: 12,
                      color: '#888',
                    }}
                  >
                    <span
                      style={{
                        display: 'inline-block',
                        background: 'rgba(0,0,0,0.06)',
                        padding: '4px 10px',
                        borderRadius: 4,
                        maxWidth: '85%',
                      }}
                    >
                      {msg.content}
                    </span>
                  </div>
                )
              }

              const isUser = msg.role === 'user'
              return (
                <div
                  key={msg.id}
                  style={{
                    display: 'flex',
                    justifyContent: isUser ? 'flex-end' : 'flex-start',
                    alignItems: 'flex-start',
                    gap: 8,
                    marginBottom: 14,
                  }}
                >
                  {!isUser && (
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 4,
                        background: '#07c160',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        fontSize: 12,
                      }}
                    >
                      AI
                    </div>
                  )}

                  <div style={{ maxWidth: '72%' }}>
                    <div
                      style={{
                        background: isUser ? '#95ec69' : '#fff',
                        color: '#111',
                        padding: '10px 12px',
                        borderRadius: 6,
                        boxShadow: '0 1px 1px rgba(0,0,0,0.06)',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        lineHeight: 1.55,
                        position: 'relative',
                      }}
                    >
                      {msg.content || (msg.streaming ? '…' : '')}
                      {msg.streaming && (
                        <span style={{ opacity: 0.45, marginLeft: 2 }}>▍</span>
                      )}
                    </div>

                    {msg.hits && msg.hits.length > 0 && (
                      <Collapse
                        size="small"
                        style={{ marginTop: 8, background: '#fff' }}
                        items={[
                          {
                            key: 'hits',
                            label: `查看 ${msg.hits.length} 条检索片段`,
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
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 4,
                        background: '#4a90d9',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        fontSize: 12,
                      }}
                    >
                      我
                    </div>
                  )}
                </div>
              )
            })}
            <div ref={chatEndRef} />
          </div>

          <div
            style={{
              borderTop: '1px solid #d9d9d9',
              background: '#f7f7f7',
              padding: 12,
            }}
          >
            <Collapse
              ghost
              size="small"
              items={[
                {
                  key: 'filters',
                  label: '可选过滤条件',
                  children: (
                    <Form form={askForm} layout="inline" initialValues={{ top_k: 5 }}>
                      <Form.Item name="source_path" label="路径">
                        <Input placeholder="docs/xxx.md" allowClear style={{ width: 180 }} />
                      </Form.Item>
                      <Form.Item name="title" label="标题">
                        <Input placeholder="标题" allowClear style={{ width: 140 }} />
                      </Form.Item>
                      <Form.Item name="updated_at" label="时间">
                        <Input placeholder="2026年6月" allowClear style={{ width: 120 }} />
                      </Form.Item>
                      <Form.Item name="top_k" label="条数">
                        <InputNumber min={1} max={50} />
                      </Form.Item>
                    </Form>
                  ),
                },
              ]}
            />

            <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'flex-end' }}>
              <Input.TextArea
                value={composer}
                onChange={(e) => setComposer(e.target.value)}
                placeholder="输入问题，Enter 发送，Shift+Enter 换行"
                autoSize={{ minRows: 2, maxRows: 4 }}
                style={{ flex: 1 }}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault()
                    void sendAsk()
                  }
                }}
              />
              <Space direction="vertical">
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
      </Card>
    </Space>
  )
}
