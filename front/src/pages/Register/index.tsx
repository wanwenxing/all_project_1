import { register } from '@/api/auth'
import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Card, Form, Input, Typography, message } from 'antd'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

interface RegisterFormValues {
  username: string
  email: string
  password: string
  confirmPassword: string
}

const { Title, Text } = Typography

export default function Register() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)

  const handleSubmit = async ({ username, email, password }: RegisterFormValues) => {
    setLoading(true)
    try {
      const data = await register({ username, email, password })
      localStorage.setItem('token', data.token.access_token)
      message.success('注册成功')
      navigate('/')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card className="shadow-md">
      <div className="mb-6 text-center">
        <Title level={3} className="!mb-2">
          注册
        </Title>
        <Text type="secondary">创建新账号以使用系统</Text>
      </div>

      <Form<RegisterFormValues>
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
          label="邮箱"
          name="email"
          rules={[
            { required: true, message: '请输入邮箱' },
            { type: 'email', message: '请输入有效的邮箱地址' },
          ]}
        >
          <Input prefix={<MailOutlined />} placeholder="请输入邮箱" />
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

        <Form.Item
          label="确认密码"
          name="confirmPassword"
          dependencies={['password']}
          rules={[
            { required: true, message: '请再次输入密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('password') === value) {
                  return Promise.resolve()
                }
                return Promise.reject(new Error('两次输入的密码不一致'))
              },
            }),
          ]}
        >
          <Input.Password prefix={<LockOutlined />} placeholder="请再次输入密码" />
        </Form.Item>

        <Form.Item className="!mb-4">
          <Button type="primary" htmlType="submit" block loading={loading}>
            注册
          </Button>
        </Form.Item>
      </Form>

      <div className="text-center">
        <Text type="secondary">已有账号？</Text>{' '}
        <Link to="/login" className="text-blue-500 hover:text-blue-600">
          立即登录
        </Link>
      </div>
    </Card>
  )
}
