import {
  indexDocs,
  searchDocs,
  uploadDoc,
  type IndexStatsData,
  type SearchHit,
  type UploadDocData,
} from '@/api/docs'
import AskChatWidget from '@/pages/Knowledge/AskChatWidget'
import {
  Button,
  Card,
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
import { useState } from 'react'

const { Paragraph, Text } = Typography

type SearchFormValues = {
  query: string
  top_k?: number
  source_path?: string
  title?: string
  updated_at?: string
}

export default function Knowledge() {
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [docPath, setDocPath] = useState('')
  const [uploading, setUploading] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [searching, setSearching] = useState(false)
  const [lastUpload, setLastUpload] = useState<UploadDocData | null>(null)
  const [indexStats, setIndexStats] = useState<IndexStatsData | null>(null)
  const [hits, setHits] = useState<SearchHit[]>([])
  const [searchForm] = Form.useForm<SearchFormValues>()

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
      message.success(`上传成功：${data.path}`)
    } catch {
      // 错误已由拦截器提示
    } finally {
      setUploading(false)
    }
  }

  const handleIndex = async () => {
    const path = docPath.trim()
    if (!path) {
      message.warning('请填写要索引的文件路径')
      return
    }

    setIndexing(true)
    try {
      const stats = await indexDocs({ path, rebuild: false })
      setIndexStats(stats)
      message.success(
        `索引完成：新增 ${stats.indexed}，跳过 ${stats.skipped}，元数据 ${stats.metadata_updated}，块 ${stats.chunks}`,
      )
    } catch {
      // 错误已由拦截器提示
    } finally {
      setIndexing(false)
    }
  }

  const handleSearch = async () => {
    const values = await searchForm.validateFields()
    setSearching(true)
    try {
      const result = await searchDocs({
        query: values.query.trim(),
        top_k: values.top_k ?? 2,
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
            <Button type="primary" loading={uploading} onClick={() => void handleUpload()}>
              上传文件
            </Button>
            <Button loading={indexing} onClick={() => void handleIndex()}>
              索引该文件
            </Button>
          </Space>

          {lastUpload && (
            <Text type="secondary">
              最近上传：{lastUpload.path}（{lastUpload.size} bytes）
            </Text>
          )}

          {indexStats && (
            <Text type="secondary">
              最近索引：indexed={indexStats.indexed}, skipped={indexStats.skipped},
              metadata_updated={indexStats.metadata_updated}, chunks={indexStats.chunks}
            </Text>
          )}
        </Space>
      </Card>

      <Card title="知识库检索">
        <Paragraph type="secondary">
          向量 + 关键字混合检索（同步接口）。智能对话请点右下角图标。
        </Paragraph>

        <Form
          form={searchForm}
          layout="inline"
          initialValues={{ top_k: 2 }}
          onFinish={() => void handleSearch()}
          style={{ rowGap: 12 }}
        >
          <Form.Item
            name="query"
            label="问题"
            rules={[{ required: true, message: '请输入检索内容' }]}
            style={{ minWidth: 280, flex: 1 }}
          >
            <Input placeholder="例如：职业迷茫和收支规划" allowClear />
          </Form.Item>
          <Form.Item name="top_k" label="返回条数" style={{ minWidth: 120 }}>
            <InputNumber min={1} max={50} />
          </Form.Item>
          <Form.Item name="source_path" label="路径" style={{ minWidth: 200 }}>
            <Input placeholder="docs/xxx.md" allowClear />
          </Form.Item>
          <Form.Item name="title" label="标题" style={{ minWidth: 160 }}>
            <Input placeholder="精确标题" allowClear />
          </Form.Item>
          <Form.Item name="updated_at" label="更新时间" style={{ minWidth: 160 }}>
            <Input placeholder="2026年6月" allowClear />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={searching}>
              检索
            </Button>
          </Form.Item>
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
                    <Text strong>
                      #{index + 1} {item.title || '未命名'}
                    </Text>
                    {item.score != null && (
                      <Text type="secondary">score={item.score.toFixed(3)}</Text>
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

      <AskChatWidget />
    </Space>
  )
}
