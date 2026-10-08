import { BulbFilled, BulbOutlined, GlobalOutlined, LineChartOutlined } from '@ant-design/icons'
import { Button, Layout, Tooltip, Typography } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import GlobalMarketPage from './features/global-market/GlobalMarketPage'
import { useUiStore } from './state/uiStore'

const { Header, Content, Footer } = Layout

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const themeMode = useUiStore((state) => state.themeMode)
  const toggleTheme = useUiStore((state) => state.toggleTheme)
  const isDark = themeMode === 'dark'
  const themeLabel = isDark ? 'Switch to light theme' : 'Switch to dark theme'

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <button className="brand" type="button" onClick={() => navigate('/global-market')} aria-label="God Market home">
          <LineChartOutlined className="brand-icon" aria-hidden="true" />
          <Typography.Text strong className="brand-text">
            God Market <span className="brand-accent">TA</span>
          </Typography.Text>
        </button>
        <nav className="app-nav" aria-label="Primary">
          <Button
            type={location.pathname === '/global-market' ? 'primary' : 'text'}
            icon={<GlobalOutlined />}
            onClick={() => navigate('/global-market')}
          >
            Global Market
          </Button>
        </nav>
        <Tooltip title={themeLabel}>
          <Button
            type="text"
            aria-label={themeLabel}
            icon={isDark ? <BulbFilled className="theme-toggle-on" /> : <BulbOutlined />}
            onClick={toggleTheme}
          />
        </Tooltip>
      </Header>
      <Content className="app-content">
        <Routes>
          <Route path="/global-market" element={<GlobalMarketPage />} />
          <Route path="*" element={<Navigate to="/global-market" replace />} />
        </Routes>
      </Content>
      <Footer className="app-footer">PS ASTA Setup · local decision support</Footer>
    </Layout>
  )
}
