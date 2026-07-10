import { getHello } from '@/api/demo'
import { Button, Card, Space, Typography } from 'antd'
import { useState } from 'react'

const { Paragraph, Text } = Typography

export default function Home() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string>('')

  const handleFetch = async () => {
    setLoading(true)
    try {
      const data = await getHello()
      setResult(JSON.stringify(data, null, 2))
    } catch {
      setResult('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="首页">
      <Paragraph>
        这是一个基于 <Text strong>React + Vite + Ant Design</Text> 的前端项目，
        已集成路由与 axios 请求封装。
      </Paragraph>
      <Space direction="vertical" size="middle">
        <Button type="primary" loading={loading} onClick={handleFetch}>
          测试接口请求
        </Button>
        {result && (
          <pre
            style={{
              margin: 0,
              padding: 12,
              background: '#f5f5f5',
              borderRadius: 8,
            }}
          >
            {result}
          </pre>
        )}
      </Space>
    </Card>
  )
}
