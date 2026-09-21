import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';

import { queryClient } from '../lib/queryClient';
import { AuthProvider } from './AuthProvider';
import { router } from './router';
import { ThemeProvider } from './ThemeProvider';
import { WsProvider } from './WsProvider';

export function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <QueryClientProvider client={queryClient}>
          <WsProvider>
            <RouterProvider router={router} future={{ v7_startTransition: true }} />
          </WsProvider>
        </QueryClientProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
