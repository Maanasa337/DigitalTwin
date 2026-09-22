import {
  AlertOutlined,
  ApartmentOutlined,
  AudioOutlined,
  BarChartOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FilePdfOutlined,
  FundOutlined,
  LineChartOutlined,
  RobotOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { Flex, Menu, theme, type MenuProps } from 'antd';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

import type { Role } from '../api/types';
import { useAuth } from './authContext';

export interface NavLeaf {
  path: string;
  labelKey: string;
  icon?: ReactNode;
  roles?: Role[];
  /** Extra route prefixes that belong to this item, e.g. a machine page belongs to Fleet. */
  also?: string[];
}

export interface NavGroup {
  key: string;
  labelKey: string;
  icon: ReactNode;
  roles?: Role[];
  children: NavLeaf[];
}

export type NavItem = NavLeaf | NavGroup;

export function isGroup(item: NavItem): item is NavGroup {
  return 'children' in item;
}

const ENGINEERING: Role[] = ['engineer', 'admin'];

/** §9.5 layout shell, with the Twin, Models, Maintenance and Analytics sections as submenus. */
export const NAV_ITEMS: NavItem[] = [
  { path: '/', labelKey: 'nav.fleet', icon: <DashboardOutlined />, also: ['/machines'] },
  { path: '/explorer', labelKey: 'nav.explorer', icon: <LineChartOutlined /> },
  { path: '/alarms', labelKey: 'nav.alarms', icon: <AlertOutlined /> },
  {
    key: 'group:twin',
    labelKey: 'nav.twin',
    icon: <ApartmentOutlined />,
    children: [
      { path: '/twin', labelKey: 'nav.twinRegistry' },
      { path: '/twin/3d', labelKey: 'nav.twin3d' },
    ],
  },
  {
    key: 'group:models',
    labelKey: 'nav.models',
    icon: <RobotOutlined />,
    roles: ENGINEERING,
    children: [
      { path: '/models', labelKey: 'nav.modelRegistry' },
      { path: '/models/benchmarks', labelKey: 'nav.benchmarks' },
      { path: '/explain/quality', labelKey: 'nav.explainQuality' },
    ],
  },
  {
    key: 'group:maintenance',
    labelKey: 'nav.maintenance',
    icon: <ToolOutlined />,
    children: [
      { path: '/maintenance', labelKey: 'nav.orders' },
      { path: '/maintenance/schedule', labelKey: 'nav.schedule' },
    ],
  },
  {
    key: 'group:analytics',
    labelKey: 'nav.analytics',
    icon: <BarChartOutlined />,
    children: [
      { path: '/analytics/production', labelKey: 'nav.production' },
      { path: '/analytics/energy', labelKey: 'nav.energy' },
    ],
  },
  { path: '/dashboards', labelKey: 'nav.dashboards', icon: <FundOutlined />, roles: ENGINEERING },
  { path: '/voice', labelKey: 'nav.voice', icon: <AudioOutlined /> },
  { path: '/reports', labelKey: 'nav.reports', icon: <FilePdfOutlined /> },
  { path: '/simulation', labelKey: 'nav.simulation', icon: <ExperimentOutlined />, roles: ENGINEERING },
];

/** The four destinations of the phone tab bar (§9.5, < 768 px). */
export const BOTTOM_NAV_PATHS = ['/', '/alarms', '/voice', '/maintenance'];

type HasRole = (...roles: Role[]) => boolean;

const allowed = (hasRole: HasRole, roles?: Role[]) => !roles || hasRole(...roles);

/** Role-filtered tree: a group is dropped when it is gated or when none of its children remain. */
export function visibleNavItems(hasRole: HasRole): NavItem[] {
  return NAV_ITEMS.flatMap((item): NavItem[] => {
    if (!allowed(hasRole, item.roles)) return [];
    if (!isGroup(item)) return [item];
    const children = item.children.filter((child) => allowed(hasRole, child.roles));
    return children.length ? [{ ...item, children }] : [];
  });
}

export function navLeaves(items: NavItem[]): NavLeaf[] {
  return items.flatMap((item) => (isGroup(item) ? item.children : [item]));
}

function matchLength(leaf: NavLeaf, pathname: string): number {
  return [leaf.path, ...(leaf.also ?? [])].reduce((best, prefix) => {
    const hit =
      prefix === '/' ? pathname === '/' : pathname === prefix || pathname.startsWith(`${prefix}/`);
    return hit ? Math.max(best, prefix.length) : best;
  }, 0);
}

/**
 * The selected leaf is the longest matching prefix, so `/models/benchmarks` selects Benchmarks and
 * not the Registry, while `/models/<id>` still selects the Registry.
 */
export function activeNav(items: NavItem[], pathname: string): { path?: string; group?: string } {
  let path: string | undefined;
  let group: string | undefined;
  let best = 0;
  for (const item of items) {
    for (const leaf of isGroup(item) ? item.children : [item]) {
      const length = matchLength(leaf, pathname);
      if (length > best) {
        best = length;
        path = leaf.path;
        group = isGroup(item) ? item.key : undefined;
      }
    }
  }
  return { path, group };
}

function useNav() {
  const { hasRole } = useAuth();
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const items = visibleNavItems(hasRole);
  return { items, active: activeNav(items, pathname), t };
}

/** `collapsed` is the icon-only rail: submenus become flyouts there, so their open state is left to antd. */
export function SideNav({ collapsed = false }: { collapsed?: boolean }) {
  const { items, active, t } = useNav();
  const navigate = useNavigate();
  const [openKeys, setOpenKeys] = useState<string[]>(active.group ? [active.group] : []);
  const [openedFor, setOpenedFor] = useState(active.group);

  // Navigating into a section (by link, voice or back button) opens its submenu; the user can still
  // close it afterwards. Adjusted during render rather than in an effect, per the React docs.
  if (active.group !== openedFor) {
    setOpenedFor(active.group);
    if (active.group && !openKeys.includes(active.group)) setOpenKeys([...openKeys, active.group]);
  }

  const leaf = (item: NavLeaf) => ({
    key: item.path,
    icon: item.icon,
    label: <NavLink to={item.path}>{t(item.labelKey)}</NavLink>,
  });

  const menuItems: MenuProps['items'] = items.map((item) =>
    isGroup(item)
      ? { key: item.key, icon: item.icon, label: t(item.labelKey), children: item.children.map(leaf) }
      : leaf(item),
  );

  return (
    <nav aria-label={t('nav.label')}>
      <Menu
        mode="inline"
        selectedKeys={active.path ? [active.path] : []}
        {...(collapsed ? {} : { openKeys, onOpenChange: setOpenKeys })}
        onClick={({ key }) => navigate(key)}
        items={menuItems}
        style={{ borderInlineEnd: 'none', paddingTop: 8 }}
      />
    </nav>
  );
}

export function BottomNav() {
  const { items, active, t } = useNav();
  const { token } = theme.useToken();
  const leaves = navLeaves(items);
  const tabs = BOTTOM_NAV_PATHS.flatMap((path) => leaves.filter((leaf) => leaf.path === path));
  // The Maintenance leaf has no icon of its own (it lives in a submenu), so borrow the group's.
  const iconFor = (leaf: NavLeaf) =>
    leaf.icon ?? items.find((item) => isGroup(item) && item.children.includes(leaf))?.icon;
  const labelFor = (leaf: NavLeaf) => (leaf.path === '/maintenance' ? 'nav.maintenance' : leaf.labelKey);

  return (
    <nav
      aria-label={t('nav.label')}
      className="bottom-nav"
      style={{ background: token.colorBgContainer, borderTop: `1px solid ${token.colorBorder}` }}
    >
      {tabs.map((item) => {
        const selected =
          item.path === '/'
            ? active.path === '/'
            : active.path === item.path || Boolean(active.path?.startsWith(`${item.path}/`));
        return (
          <NavLink
            key={item.path}
            to={item.path}
            className="bottom-nav__item"
            aria-current={selected ? 'page' : false}
            style={{ color: selected ? token.colorPrimary : token.colorTextSecondary }}
          >
            <Flex vertical align="center" gap={2}>
              <span aria-hidden style={{ fontSize: 20 }}>
                {iconFor(item)}
              </span>
              <span style={{ fontSize: 12 }}>{t(labelFor(item))}</span>
            </Flex>
          </NavLink>
        );
      })}
    </nav>
  );
}
