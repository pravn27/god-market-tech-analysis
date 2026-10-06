import { GlobalOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import GlobalMarketPage from './features/global-market/GlobalMarketPage'
import { useUiStore } from './state/uiStore'

const { Header, Sider, Content } = Layout

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const navigationCollapsed = useUiStore((state) => state.navigationCollapsed)
  const toggleNavigation = useUiStore((state) => state.toggleNavigation)

  return (
    <Layout className="app-shell">
      <Sider collapsible collapsed={navigationCollapsed} trigger={null} width={232}>
        <div className="brand" aria-label="God Market ASTA">
          <span className="brand-mark">GM</span>
          {!navigationCollapsed && <span>God Market</span>}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={[{ key: '/global-market', icon: <GlobalOutlined />, label: 'Global Market' }]}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <button className="navigation-toggle" type="button" onClick={toggleNavigation} aria-label="Toggle navigation">
            {navigationCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
          <Typography.Text type="secondary">PS ASTA Setup · local decision support</Typography.Text>
        </Header>
        <Content className="app-content">
          <Routes>
            <Route path="/global-market" element={<GlobalMarketPage />} />
            <Route path="*" element={<Navigate to="/global-market" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
