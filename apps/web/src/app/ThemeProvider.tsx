import { App as AntApp, ConfigProvider } from 'antd';
import enUS from 'antd/locale/en_US';
import hiIN from 'antd/locale/hi_IN';
import { useEffect, useMemo, type ReactNode } from 'react';

import { useUiStore } from '../store/uiStore';
import { themeConfig, TOKENS } from './theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const mode = useUiStore((s) => s.themeMode);
  const language = useUiStore((s) => s.language);
  const config = useMemo(() => themeConfig(mode), [mode]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = mode;
    root.style.colorScheme = mode;
    document.body.style.background = TOKENS[mode].colorBgLayout;
    document.body.style.color = TOKENS[mode].colorText;
  }, [mode]);

  return (
    <ConfigProvider theme={config} locale={language === 'hi' ? hiIN : enUS}>
      <AntApp>{children}</AntApp>
    </ConfigProvider>
  );
}
