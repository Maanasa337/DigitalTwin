import {
  AlertOutlined,
  ApartmentOutlined,
  AudioOutlined,
  BarChartOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FilePdfOutlined,
  LineChartOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Flex, Menu, theme } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

import type { Role } from '../api/types';
import { useAuth } from './authContext';

export interface NavItem {
  path: string;
  labelKey: string;
  icon: ReactNode;
  roles?: Role[];
}

export const NAV_ITEMS: NavItem[] = [
  { path: '/', labelKey: 'nav.fleet', icon: <DashboardOutlined /> },
  { path: '/twin', labelKey: 'nav.twin', icon: <ApartmentOutlined /> },
  { path: '/explorer', labelKey: 'nav.explorer', icon: <LineChartOutlined /> },
  { path: '/alarms', labelKey: 'nav.alarms', icon: <AlertOutlined /> },
  { path: '/maintenance', labelKey: 'nav.maintenance', icon: <ToolOutlined /> },
  { path: '/analytics/production', labelKey: 'nav.production', icon: <BarChartOutlined /> },
  { path: '/analytics/energy', labelKey: 'nav.energy', icon: <ThunderboltOutlined /> },
  { path: '/reports', labelKey: 'nav.reports', icon: <FilePdfOutlined /> },
  { path: '/voice', labelKey: 'nav.voice', icon: <AudioOutlined /> },
  { path: '/models', labelKey: 'nav.models', icon: <RobotOutlined />, roles: ['engineer', 'admin'] },
  { path: '/simulation', labelKey: 'nav.simulation', icon: <ExperimentOutlined />, roles: ['engineer', 'admin'] },
];

export function visibleNavItems(hasRole: (...roles: Role[]) => boolean): NavItem[] {
  return NAV_ITEMS.filter((item) => !item.roles || hasRole(...item.roles));
}

function useNav() {
  const { hasRole } = useAuth();
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const items = visibleNavItems(hasRole);
  const active = items.find((item) =>
    item.path === '/' ? pathname === '/' : pathname.startsWith(item.path),
  )?.path;
  return { items, active, t };
}

export function SideNav() {
  const { items, active, t } = useNav();
  const navigate = useNavigate();
  return (
    <nav aria-label={t('nav.label')}>
      <Menu
        mode="inline"
        selectedKeys={active ? [active] : []}
        onClick={({ key }) => navigate(key)}
        items={items.map((item) => ({
          key: item.path,
          icon: item.icon,
          label: <NavLink to={item.path}>{t(item.labelKey)}</NavLink>,
        }))}
        style={{ borderInlineEnd: 'none', paddingTop: 8 }}
      />
    </nav>
  );
}

export function BottomNav() {
  const { items, active, t } = useNav();
  const { token } = theme.useToken();
  return (
    <nav
      aria-label={t('nav.label')}
      className="bottom-nav"
      style={{ background: token.colorBgContainer, borderTop: `1px solid ${token.colorBorder}` }}
    >
      {items.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          className="bottom-nav__item"
          style={{ color: item.path === active ? token.colorPrimary : token.colorTextSecondary }}
        >
          <Flex vertical align="center" gap={2}>
            <span aria-hidden style={{ fontSize: 20 }}>
              {item.icon}
            </span>
            <span style={{ fontSize: 12 }}>{t(item.labelKey)}</span>
          </Flex>
        </NavLink>
      ))}
    </nav>
  );
}
