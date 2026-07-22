import { indexDocs, uploadDoc, type IndexStatsData, type UploadDocData } from '@/api/docs'
import { Button, Card, Space, Typography, Upload, message } from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { useState } from 'react'

const { Paragraph, Text } = Typography

export default function Knowledge() {
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [indexing, setIndexing] = useState(false)
  const [lastUpload, setLastUpload] = useState<UploadDocData | null>(null)
  const [indexStats, setIndexStats] = useState<IndexStatsData | null>(null)

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
      message.success(`已保存到 ${data.path}`)
      setFileList([])
    } catch {
      // 错误提示由 request 拦截器处理
    } finally {
      setUploading(false)
    }
  }

  const handleIndex = async () => {
    setIndexing(true)
    try {
      const stats = await indexDocs(false)
      setIndexStats(stats)
      message.success('知识库更新完成')
    } catch {
      // 错误提示由 request 拦截器处理
    } finally {
      setIndexing(false)
    }
  }

  return (
    <Card title="知识库">
      <Paragraph>
        上传 <Text code>.md</Text> / <Text code>.txt</Text> 文件到后端{' '}
        <Text code>docs/</Text>，再点击「存储知识库」执行增量索引。
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
  )
}
