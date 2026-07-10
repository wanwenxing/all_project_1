import { login } from '@/api/auth'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, Typography, message } from 'antd'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

interface LoginFormValues {
  username: string
  password: string
}

const { Title, Text } = Typography

export default function Login() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (values: LoginFormValues) => {
    setLoading(true)
    try {
      const data = await login(values)
      localStorage.setItem('token', data.token.access_token)
      message.success('登录成功')
      navigate('/')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="shadow-md">
      <div className="mb-6 text-center">
        <Title level={3} className="!mb-2">
          登录
        </Title>
        <Text type="secondary">使用账户名和密码登录系统</Text>
      </div>

      <Form<LoginFormValues>
        layout="vertical"
        size="large"
        onFinish={handleSubmit}
        autoComplete="off"
      >
        <Form.Item
          label="账户名"
          name="username"
          rules={[
            { required: true, message: '请输入账户名' },
            { min: 3, message: '账户名至少 3 个字符' },
            { max: 50, message: '账户名最多 50 个字符' },
          ]}
        >
          <Input prefix={<UserOutlined />} placeholder="请输入账户名" />
        </Form.Item>

        <Form.Item
          label="密码"
          name="password"
          rules={[
            { required: true, message: '请输入密码' },
            { min: 6, message: '密码至少 6 个字符' },
            { max: 128, message: '密码最多 128 个字符' },
          ]}
        >
          <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" />
        </Form.Item>

        <Form.Item className="!mb-4">
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form.Item>
      </Form>

      <div className="text-center">
        <Text type="secondary">还没有账号？</Text>{' '}
        <Link to="/register" className="text-blue-500 hover:text-blue-600">
          立即注册
        </Link>
      </div>
    </Card>
  )
}
