import { ArrowLeftOutlined, ExportOutlined, FundOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Skeleton, Tooltip, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { grafanaDashboardUrl } from '../../api/grafana';
import { EmptyState } from '../../components/EmptyState';
import { PageHeader } from '../../components/PageHeader';
import { useGrafanaHealth } from '../../hooks/useGrafana';
import { useUiStore } from '../../store/uiStore';

/** Dashboards provisioned from infra/grafana/provisioning/dashboards/json (uids are fixed there). */
const DASHBOARDS = {
  asset: { uid: 'tv-asset', slug: 'asset-overview' },
  fleet: { uid: 'tv-fleet', slug: 'fleet-overview' },
} as const;

/**
 * FR-MM-05: a provisioned Grafana dashboard in kiosk mode, themed like the app. `asset` is used by
 * `/machines/:code/grafana`, `fleet` by `/dashboards`. Grafana is optional in compose, so its health
 * is checked first: a stopped instance shows a retryable notice instead of a proxy error page, and the
 * external link is disabled rather than opening that error page in a new tab.
 */
export default function GrafanaPage({ kind }: { kind: 'asset' | 'fleet' }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { code } = useParams<{ code: string }>();
  const mode = useUiStore((s) => s.themeMode);
  const health = useGrafanaHealth();

  const { uid, slug } = DASHBOARDS[kind];
  const src = grafanaDashboardUrl(uid, slug, mode, kind === 'asset' && code ? { asset: code } : {});
  const title = kind === 'asset' ? t('grafana.assetTitle', { code }) : t('grafana.fleetTitle');

  return (
    <>
      <PageHeader
        title={title}
        subtitle={t('grafana.subtitle')}
        actions={
          <>
            {kind === 'asset' && code && (
              <Link to={`/machines/${code}`}>
                <Button icon={<ArrowLeftOutlined />}>{t('grafana.backToMachine')}</Button>
              </Link>
            )}
            <Tooltip title={health.isError ? t('grafana.unavailableShort') : undefined}>
              <Button
                icon={<ExportOutlined />}
                href={src.replace('&kiosk', '')}
                target="_blank"
                rel="noreferrer"
                disabled={health.isError}
              >
                {t('grafana.openInGrafana')}
              </Button>
            </Tooltip>
          </>
        }
      />
      {health.isPending ? (
        <Skeleton active paragraph={{ rows: 10 }} />
      ) : health.isError ? (
        <EmptyState
          icon={<FundOutlined />}
          description={t('grafana.unavailable')}
          action={
            <Button icon={<ReloadOutlined />} onClick={() => void health.refetch()}>
              {t('common.retry')}
            </Button>
          }
        />
      ) : (
        <iframe
          key={src}
          title={title}
          src={src}
          style={{
            display: 'block',
            width: '100%',
            height: 'calc(100vh - 200px)',
            minHeight: 480,
            border: `1px solid ${token.colorBorder}`,
            borderRadius: 12,
            background: token.colorBgContainer,
          }}
        />
      )}
    </>
  );
}
