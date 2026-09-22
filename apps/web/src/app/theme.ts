import { theme, type ThemeConfig } from 'antd';

import { useUiStore, type ThemeMode } from '../store/uiStore';

export const FONT_FAMILY = 'Inter, system-ui, "Segoe UI", sans-serif';

export const TOKENS = {
  dark: {
    colorBgLayout: '#0d1117',
    colorBgContainer: '#161b22',
    colorBgElevated: '#1f2630',
    colorBorder: 'rgba(255,255,255,0.10)',
    colorText: '#ffffff',
    colorTextSecondary: '#c3c2b7',
    colorTextTertiary: '#898781',
    colorPrimary: '#3987e5',
    colorPrimaryHover: '#5598e7',
    colorSuccess: '#0ca30c',
    colorWarning: '#fab219',
    colorError: '#d03b3b',
  },
  light: {
    colorBgLayout: '#f7f8fa',
    colorBgContainer: '#ffffff',
    colorBgElevated: '#ffffff',
    colorBorder: 'rgba(11,11,11,0.10)',
    colorText: '#0b0b0b',
    colorTextSecondary: '#52514e',
    colorTextTertiary: '#898781',
    colorPrimary: '#2a78d6',
    colorPrimaryHover: '#256abf',
    colorSuccess: '#0ca30c',
    colorWarning: '#fab219',
    colorError: '#d03b3b',
  },
} as const;

/**
 * Chart-only tokens (§9.2) that have no Ant Design equivalent. Kept apart from `TOKENS` because
 * that object is spread into `theme.token`, which only accepts Ant Design's own keys.
 */
/**
 * `series` is the categorical order (blue, orange, aqua, yellow, magenta, green, violet, red), stepped
 * per surface and validated for colour-vision deficiency. Assign it by entity, never by rank, and
 * never cycle it: a ninth series is a sign the chart needs splitting.
 */
export const CHART_TOKENS = {
  dark: {
    gridline: '#2c2c2a',
    axis: '#898781',
    series: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
  },
  light: {
    gridline: '#e1e0d9',
    axis: '#898781',
    series: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'],
  },
} as const;

export function useChartTokens() {
  return CHART_TOKENS[useUiStore((s) => s.themeMode)];
}

export function themeConfig(mode: ThemeMode): ThemeConfig {
  const tokens = TOKENS[mode];
  return {
    algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      ...tokens,
      colorBorderSecondary: tokens.colorBorder,
      fontFamily: FONT_FAMILY,
      borderRadius: 8,
      borderRadiusLG: 12,
      motionDurationMid: '0.15s',
      motionDurationSlow: '0.25s',
      boxShadowTertiary: mode === 'light' ? '0 1px 2px rgba(0,0,0,.06)' : 'none',
    },
    components: {
      Layout: {
        headerBg: tokens.colorBgContainer,
        siderBg: tokens.colorBgContainer,
        bodyBg: tokens.colorBgLayout,
        headerHeight: 56,
        headerPadding: '0 16px',
      },
      Menu: { itemBg: 'transparent', itemBorderRadius: 8, subMenuItemBorderRadius: 8 },
      // §9.4: card radius 12, control radius 8, tag radius 999 (a pill).
      Card: { borderRadiusLG: 12 },
      Tag: { borderRadiusSM: 999 },
    },
  };
}
