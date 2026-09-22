import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { Role } from '../api/types';
import en from '../i18n/en.json';
import hi from '../i18n/hi.json';
import { AuthContext, makeAuthValue } from './authContext';
import { activeNav, BottomNav, isGroup, NAV_ITEMS, navLeaves, SideNav, visibleNavItems } from './Nav';

function renderNav(roles: Role[], route = '/twin', ui = <SideNav />) {
  const auth = makeAuthValue({ sub: 'u1', name: 'Test', email: null, roles }, async () => undefined, () => undefined);
  return render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </AuthContext.Provider>,
  );
}

const lookup = (dict: unknown, key: string) =>
  key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], dict);

const rolesMatcher = (roles: Role[]) => (...required: Role[]) => required.some((r) => roles.includes(r));

describe('navigation labels', () => {
  const labelKeys = NAV_ITEMS.flatMap((item) => [item.labelKey, ...(isGroup(item) ? item.children.map((c) => c.labelKey) : [])]);

  it.each(labelKeys)('%s is translated in en and hi', (key) => {
    expect(typeof lookup(en, key)).toBe('string');
    expect(typeof lookup(hi, key)).toBe('string');
  });

  it('renders translated text, never a raw key', () => {
    renderNav(['admin']);
    const nav = screen.getByRole('navigation');
    expect(nav.textContent).not.toMatch(/\bnav\.[a-z]/i);
    for (const label of ['Fleet', 'Explorer', 'Alarms', 'Twin', 'Models', 'Maintenance', 'Analytics', 'Dashboards']) {
      expect(within(nav).getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it('opens the submenu of the current section', () => {
    renderNav(['technician'], '/twin/3d');
    expect(screen.getByRole('link', { name: '3D layout' })).toHaveAttribute('href', '/twin/3d');
    expect(screen.getByRole('link', { name: 'Registry' })).toHaveAttribute('href', '/twin');
  });
});

describe('navigation role filtering', () => {
  it('hides Simulation, Models and Dashboards for technicians', () => {
    renderNav(['technician']);
    expect(screen.getByText('Twin')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Simulation' })).not.toBeInTheDocument();
    expect(screen.queryByText('Models')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Dashboards' })).not.toBeInTheDocument();
  });

  it('hides Simulation for managers', () => {
    renderNav(['manager']);
    expect(screen.queryByRole('link', { name: 'Simulation' })).not.toBeInTheDocument();
  });

  it.each<Role>(['engineer', 'admin'])('shows the engineering items for %s', (role) => {
    renderNav([role]);
    expect(screen.getByRole('link', { name: 'Simulation' })).toHaveAttribute('href', '/simulation');
    expect(screen.getByRole('link', { name: 'Dashboards' })).toHaveAttribute('href', '/dashboards');
    expect(screen.getByText('Models')).toBeInTheDocument();
  });

  // Asserted as behaviour rather than a frozen list: every module adds nav items, and a hard-coded
  // array turns each one into an unrelated test failure.
  it('filters the item tree by role', () => {
    const paths = (roles: Role[]) => navLeaves(visibleNavItems(rolesMatcher(roles))).map((i) => i.path);
    const gated = NAV_ITEMS.filter((i) => i.roles);
    const restricted = navLeaves(gated).map((i) => i.path);

    const technician = paths(['technician']);
    expect(technician).not.toEqual(expect.arrayContaining(restricted));
    expect(technician.some((p) => restricted.includes(p))).toBe(false);
    // An admin holds every gated role, so they see the whole tree in its declared order.
    expect(paths(['admin'])).toEqual(navLeaves(NAV_ITEMS).map((i) => i.path));
  });
});

describe('active item', () => {
  const items = visibleNavItems(rolesMatcher(['admin']));

  it.each([
    ['/', '/', undefined],
    ['/machines/cnc-01', '/', undefined],
    ['/machines/cnc-01/grafana', '/', undefined],
    ['/twin', '/twin', 'group:twin'],
    ['/twin/3d', '/twin/3d', 'group:twin'],
    ['/models/benchmarks', '/models/benchmarks', 'group:models'],
    ['/models/3f2a', '/models', 'group:models'],
    ['/explain/quality', '/explain/quality', 'group:models'],
    ['/maintenance/schedule', '/maintenance/schedule', 'group:maintenance'],
    ['/analytics/energy', '/analytics/energy', 'group:analytics'],
  ])('%s selects %s', (pathname, path, group) => {
    expect(activeNav(items, pathname)).toEqual({ path, group });
  });
});

describe('bottom navigation', () => {
  it('shows only Fleet, Alarms, Voice and Maintenance', () => {
    renderNav(['admin'], '/maintenance/schedule', <BottomNav />);
    const links = screen.getAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/', '/alarms', '/voice', '/maintenance']);
    expect(screen.getByRole('link', { name: 'Maintenance' })).toHaveAttribute('aria-current', 'page');
  });
});
