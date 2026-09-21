import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { App as AntApp } from 'antd';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import type { Role } from '../api/types';
import { AuthContext, makeAuthValue } from '../app/authContext';

export function renderWithProviders(ui: ReactNode, { roles = ['engineer'], route = '/' }: { roles?: Role[]; route?: string } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const auth = makeAuthValue({ sub: 'u1', name: 'Test User', email: null, roles }, async () => undefined, () => undefined);
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>
        <AntApp>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </AntApp>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}
