import { Grid, Layout, Skeleton, theme } from 'antd';
import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';

import { VoiceConsole } from '../features/voice/VoiceConsole';
import { useUiStore } from '../store/uiStore';
import { BottomNav, SideNav } from './Nav';
import { TopBar } from './TopBar';

export function AppShell() {
  const { token } = theme.useToken();
  const screens = Grid.useBreakpoint();
  const navCollapsed = useUiStore((s) => s.navCollapsed);
  const wide = screens.xl ?? true;
  const tablet = screens.md ?? true;
  const border = `1px solid ${token.colorBorder}`;

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Header style={{ position: 'sticky', top: 0, zIndex: 20, borderBottom: border }}>
        <TopBar showNavToggle={wide} compact={!tablet} />
      </Layout.Header>
      <Layout hasSider={tablet}>
        {tablet && (
          <Layout.Sider
            width={220}
            collapsedWidth={64}
            collapsed={wide ? navCollapsed : true}
            trigger={null}
            style={{ borderInlineEnd: border, position: 'sticky', top: 56, height: 'calc(100vh - 56px)' }}
          >
            <SideNav />
          </Layout.Sider>
        )}
        <Layout.Content style={{ padding: tablet ? 24 : 16, paddingBottom: tablet ? 24 : 88, minWidth: 0 }}>
          <main style={{ maxWidth: 1600, margin: '0 auto' }}>
            <Suspense fallback={<Skeleton active paragraph={{ rows: 8 }} />}>
              <Outlet />
            </Suspense>
          </main>
        </Layout.Content>
      </Layout>
      {!tablet && <BottomNav />}
      <VoiceConsole />
    </Layout>
  );
}
