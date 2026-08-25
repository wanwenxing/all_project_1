import { runAgent, type AgentToolStep } from '@/api/agent'
import { Button, Card, Input, Space, Tag, Typography } from 'antd'
import { useState } from 'react'

const { Paragraph, Text, Title } = Typography
const { TextArea } = Input

export default function AgentPage() {
  const [message, setMessage] = useState('我想知道 3*5+1 的答案')
  const [loading, setLoading] = useState(false)
  const [answer, setAnswer] = useState('')
  const [toolSteps, setToolSteps] = useState<AgentToolStep[]>([])

  const handleRun = async () => {
    const text = message.trim()
    if (!text) return
    setLoading(true)
    setAnswer('')
    setToolSteps([])
    try {
      const data = await runAgent(text)
      setAnswer(data.answer)
      setToolSteps(data.tool_steps || [])
    } catch {
      // axios 拦截器已提示
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="Agent 工具编排">
      <Paragraph type="secondary">
        调用后端图级 ReAct（agent ↔ call_tools）。有依赖的计算会多轮调用工具，例如先乘后加。
      </Paragraph>

      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <TextArea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={4}
          maxLength={4000}
          showCount
          placeholder="输入问题，例如：3*5+1 等于多少？"
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              void handleRun()
            }
          }}
        />
        <Button type="primary" loading={loading} onClick={() => void handleRun()}>
          运行 Agent
        </Button>

        {toolSteps.length > 0 && (
          <Card size="small" title="工具调用轨迹" type="inner">
            <Space direction="vertical" style={{ width: '100%' }}>
              {toolSteps.map((step, index) => (
                <div key={`${step.name}-${index}`}>
                  <Tag color="blue">{step.name}</Tag>
                  <Text code>{step.content}</Text>
                </div>
              ))}
            </Space>
          </Card>
        )}

        {answer && (
          <Card size="small" title="最终回答" type="inner">
            <Title level={5} style={{ margin: 0 }}>
              {answer}
            </Title>
          </Card>
        )}
      </Space>
    </Card>
  )
}
