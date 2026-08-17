import { Layout, Menu, theme } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

const { Header, Content, Footer } = Layout

const menuItems = [
  { key: '/', label: '首页' },
  { key: '/knowledge', label: '知识库' },
  { key: '/evals/cases', label: '评测题库' },
  { key: '/evals/runs', label: '测评任务' },
  { key: '/about', label: '关于' },
]

export default function BasicLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', padding: '0 24px' }}>
        <div
          style={{
            color: '#fff',
            fontSize: 18,
            fontWeight: 600,
            marginRight: 48,
          }}
        >
          Front
        </div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ flex: 1, minWidth: 0 }}
        />
      </Header>
      <Content style={{ padding: 24, background: token.colorBgLayout }}>
        <div
          style={{
            padding: 24,
            minHeight: 360,
            background: token.colorBgContainer,
            borderRadius: token.borderRadiusLG,
          }}
        >
          <Outlet />
        </div>
      </Content>
      <Footer style={{ textAlign: 'center' }}>Front ©2026</Footer>
    </Layout>
  )
}
