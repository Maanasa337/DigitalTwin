import { Button, Result } from 'antd';
import { lazy, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { createBrowserRouter, useNavigate } from 'react-router-dom';

import type { Role } from '../api/types';
import { AppShell } from './AppShell';
import { useAuth } from './authContext';

const TwinPage = lazy(() => import('../features/twin/TwinPage'));
const SimulationPage = lazy(() => import('../features/simulation/SimulationPage'));
const Fleet = lazy(() => import('../features/monitoring/Fleet'));
const MachineDetail = lazy(() => import('../features/monitoring/MachineDetail'));
const Explorer = lazy(() => import('../features/alarms/Explorer'));
const AlarmsPage = lazy(() => import('../features/alarms/AlarmsPage'));
const ModelsPage = lazy(() => import('../features/pdm/ModelsPage'));
const ModelDetail = lazy(() => import('../features/pdm/ModelDetail'));
const QualityPage = lazy(() => import('../features/explain/QualityPage'));
const MaintenancePage = lazy(() => import('../features/maintenance/MaintenancePage'));
const SchedulePage = lazy(() => import('../features/maintenance/SchedulePage'));
const ProductionPage = lazy(() => import('../features/analytics/ProductionPage'));
const EnergyPage = lazy(() => import('../features/analytics/EnergyPage'));
const VoicePage = lazy(() => import('../features/voice/VoicePage'));
const ReportsPage = lazy(() => import('../features/reports/ReportsPage'));

function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { hasRole } = useAuth();
  const { t } = useTranslation();
  if (hasRole(...roles)) return children;
  return <Result status="403" title="403" subTitle={t('errors.forbidden')} />;
}

function NotFound() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <Result
      status="404"
      title="404"
      subTitle={t('errors.notFound')}
      extra={
        <Button type="primary" onClick={() => navigate('/')}>
          {t('errors.goHome')}
        </Button>
      }
    />
  );
}

export const router = createBrowserRouter(
  [
    {
      element: <AppShell />,
      children: [
        { index: true, element: <Fleet /> },
        { path: 'machines/:code', element: <MachineDetail /> },
        { path: 'twin', element: <TwinPage /> },
        { path: 'explorer', element: <Explorer /> },
        { path: 'alarms', element: <AlarmsPage /> },
        { path: 'maintenance', element: <MaintenancePage /> },
        { path: 'maintenance/schedule', element: <SchedulePage /> },
        { path: 'analytics/production', element: <ProductionPage /> },
        { path: 'analytics/energy', element: <EnergyPage /> },
        { path: 'voice', element: <VoicePage /> },
        { path: 'reports', element: <ReportsPage /> },
        {
          path: 'explain/quality',
          element: (
            <RequireRole roles={['engineer', 'admin']}>
              <QualityPage />
            </RequireRole>
          ),
        },
        {
          path: 'models',
          element: (
            <RequireRole roles={['engineer', 'admin']}>
              <ModelsPage />
            </RequireRole>
          ),
        },
        {
          path: 'models/:id',
          element: (
            <RequireRole roles={['engineer', 'admin']}>
              <ModelDetail />
            </RequireRole>
          ),
        },
        {
          path: 'simulation',
          element: (
            <RequireRole roles={['engineer', 'admin']}>
              <SimulationPage />
            </RequireRole>
          ),
        },
        { path: '*', element: <NotFound /> },
      ],
    },
  ],
  {
    future: {
      v7_fetcherPersist: true,
      v7_normalizeFormMethod: true,
      v7_partialHydration: true,
      v7_relativeSplatPath: true,
      v7_skipActionErrorRevalidation: true,
    },
  },
);
