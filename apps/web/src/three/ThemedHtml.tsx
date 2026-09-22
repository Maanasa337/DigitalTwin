import { Html } from '@react-three/drei';
import { ConfigProvider } from 'antd';
import { useMemo, type ComponentProps } from 'react';

import { themeConfig } from '../app/theme';
import { useUiStore } from '../store/uiStore';

/**
 * drei's `<Html>` renders into a separate React root, so Ant Design's theme context does not reach
 * it. This re-provides the theme; i18n and Zustand are module-level and need nothing.
 */
export function ThemedHtml({ children, ...props }: ComponentProps<typeof Html>) {
  const mode = useUiStore((s) => s.themeMode);
  const config = useMemo(() => themeConfig(mode), [mode]);
  return (
    <Html {...props}>
      <ConfigProvider theme={config}>{children}</ConfigProvider>
    </Html>
  );
}
