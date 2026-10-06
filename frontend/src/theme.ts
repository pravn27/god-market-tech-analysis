import type { ThemeConfig } from 'antd'
import { theme } from 'antd'

export const psAstaTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#34d399',
    colorInfo: '#60a5fa',
    colorSuccess: '#34d399',
    colorWarning: '#fbbf24',
    colorError: '#fb7185',
    colorBgBase: '#06090f',
    colorBgContainer: '#0d1420',
    colorBgElevated: '#121c2a',
    colorBorder: '#26384e',
    colorText: '#e5edf7',
    borderRadius: 8,
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
  components: {
    Layout: {
      headerBg: '#06090f',
      siderBg: '#0a1019',
      bodyBg: '#06090f',
    },
    Menu: {
      darkItemBg: '#0a1019',
      darkItemSelectedBg: '#173b3b',
      darkItemSelectedColor: '#a7f3d0',
    },
  },
}
