import {
  indexDocs,
  searchDocs,
  uploadDoc,
  type IndexStatsData,
  type SearchHit,
  type UploadDocData,
} from '@/api/docs'
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

export default function Knowledge() {
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [docPath, setDocPath] = useState('')
  const [uploading, setUploading] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [searching, setSearching] = useState(false)
  const [lastUpload, setLastUpload] = useState<UploadDocData | null>(null)
  const [indexStats, setIndexStats] = useState<IndexStatsData | null>(null)
  const [hits, setHits] = useState<SearchHit[]>([])
  const [searchForm] = Form.useForm()

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

  const handleSearch = async (values: {
    query: string
    top_k?: number
    source_path?: string
    title?: string
    updated_at?: string
  }) => {
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
    </Space>
  )
}
