import type { ThemeConfig } from 'antd'
import { theme } from 'antd'

import type { ThemeMode } from './state/uiStore'

export const marketColors = {
  bullish: '#52c41a',
  bearish: '#ff4d4f',
  neutral: '#999999',
  primary: '#1890ff',
} as const

export function getAppTheme(mode: ThemeMode): ThemeConfig {
  const isDark = mode === 'dark'
  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: marketColors.primary,
      colorInfo: marketColors.primary,
      colorSuccess: marketColors.bullish,
      colorError: marketColors.bearish,
      colorWarning: '#faad14',
      colorBgContainer: isDark ? '#141414' : '#ffffff',
      colorBgElevated: isDark ? '#1f1f1f' : '#ffffff',
      colorBgLayout: isDark ? '#0a0a0a' : '#f5f5f5',
      colorBorder: isDark ? '#303030' : '#d9d9d9',
      colorBorderSecondary: isDark ? '#303030' : '#f0f0f0',
      borderRadius: 2,
      borderRadiusLG: 2,
      borderRadiusSM: 2,
      borderRadiusXS: 2,
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    },
    components: {
      Layout: {
        headerBg: isDark ? '#141414' : '#ffffff',
        bodyBg: isDark ? '#0a0a0a' : '#f5f5f5',
        headerHeight: 64,
        headerPadding: '0 24px',
      },
      Table: {
        headerBg: isDark ? '#1d1d1d' : '#fafafa',
        rowHoverBg: isDark ? '#262626' : '#f5f5f5',
      },
      Tag: {
        defaultBg: isDark ? '#1f1f1f' : '#fafafa',
      },
    },
  }
}
