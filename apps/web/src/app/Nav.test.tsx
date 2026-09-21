import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { Role } from '../api/types';
import { AuthContext, makeAuthValue } from './authContext';
import { NAV_ITEMS, SideNav, visibleNavItems } from './Nav';

function renderNav(roles: Role[]) {
  const auth = makeAuthValue({ sub: 'u1', name: 'Test', email: null, roles }, async () => undefined, () => undefined);
  render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={['/twin']}>
        <SideNav />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('navigation role filtering', () => {
  it('hides Simulation for technicians', () => {
    renderNav(['technician']);
    expect(screen.getByRole('link', { name: 'Twin' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Simulation' })).not.toBeInTheDocument();
  });

  it('hides Simulation for managers', () => {
    renderNav(['manager']);
    expect(screen.queryByRole('link', { name: 'Simulation' })).not.toBeInTheDocument();
  });

  it.each<Role>(['engineer', 'admin'])('shows Simulation for %s', (role) => {
    renderNav([role]);
    expect(screen.getByRole('link', { name: 'Twin' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Simulation' })).toHaveAttribute('href', '/simulation');
  });

  // Asserted as behaviour rather than a frozen list: every module adds nav items, and a hard-coded
  // array turns each one into an unrelated test failure.
  it('filters the item list by role', () => {
    const paths = (roles: Role[]) =>
      visibleNavItems((...required) => required.some((r) => roles.includes(r))).map((i) => i.path);

    const technician = paths(['technician']);
    const admin = paths(['admin']);
    const restricted = NAV_ITEMS.filter((i) => i.roles).map((i) => i.path);
    const unrestricted = NAV_ITEMS.filter((i) => !i.roles).map((i) => i.path);

    expect(technician).toEqual(unrestricted);
    expect(technician).not.toEqual(expect.arrayContaining(restricted));
    // An admin holds every gated role, so they see the whole list in its declared order.
    expect(admin).toEqual(NAV_ITEMS.map((i) => i.path));
    expect(admin).toEqual(expect.arrayContaining(restricted));
  });
});
