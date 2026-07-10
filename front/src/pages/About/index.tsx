import { Card, Descriptions } from 'antd'

export default function About() {
  return (
    <Card title="关于">
      <Descriptions column={1} bordered>
        <Descriptions.Item label="技术栈">React 19 + TypeScript + Vite</Descriptions.Item>
        <Descriptions.Item label="UI 库">Ant Design</Descriptions.Item>
        <Descriptions.Item label="路由">React Router v7</Descriptions.Item>
        <Descriptions.Item label="HTTP 客户端">Axios（含拦截器封装）</Descriptions.Item>
      </Descriptions>
    </Card>
  )
}
