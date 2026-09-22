import {
  ArrowLeftOutlined,
  BlockOutlined,
  CloudServerOutlined,
  FundOutlined,
  LineChartOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import { Button, Card, Col, Flex, Grid, Row, Skeleton, Tabs, Tag, Tooltip, Typography, theme } from 'antd';
import { lazy, Suspense, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';

import type { Asset, PredictionConfidence, TelemetryLatestValue } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { HealthGauge } from '../../components/HealthGauge';
import { RulBadge } from '../../components/RulBadge';
import { SensorTile } from '../../components/SensorTile';
import { StatusTag } from '../../components/StatusTag';
import { useAssets } from '../../hooks/useAssets';
import { useLiveAssetFeed } from '../../hooks/useLiveFeed';
import { usePredictionsLatest } from '../../hooks/usePdm';
import { useActiveAlarmCounts, useTelemetryLatest } from '../../hooks/useTelemetry';
import { useExplanationForPrediction } from '../../hooks/useXai';
import { assetStatusLevel, STATUS_PALETTE, statusTextColor, withAlpha, type StatusLevel } from '../../lib/status';
import { useLiveTwinStore } from '../../store/liveTwinStore';
import { useUiStore } from '../../store/uiStore';
import { ExplanationCard } from '../explain/ExplanationCard';
import { FidelityBadge } from '../twin/FidelityBadge';
import { PredictionTimeline } from './PredictionTimeline';

// three.js is heavy; it is fetched only when the 3D rail is actually shown.
const Machine3D = lazy(() => import('../twin/Machine3D'));

const CONFIDENCE_LEVEL: Record<NonNullable<PredictionConfidence['label']>, StatusLevel> = {
  high: 'good',
  medium: 'warning',
  low: 'critical',
};

function ConfidenceTag({ confidence }: { confidence: PredictionConfidence }) {
  const { t } = useTranslation();
  const mode = useUiStore((s) => s.themeMode);
  if (!confidence.label) return null;
  const level = CONFIDENCE_LEVEL[confidence.label];
  const { color, Icon } = STATUS_PALETTE[level];
  return (
    <Tooltip title={confidence.reasons.join(' · ') || undefined}>
      <Tag
        bordered={false}
        icon={<Icon aria-hidden />}
        style={{ background: withAlpha(color, 0.16), color: statusTextColor(level, mode), marginInlineEnd: 0 }}
      >
        {t(`machine.confidence.${confidence.label}`)}
      </Tag>
    </Tooltip>
  );
}

/**
 * Machine detail page (§9.7 `/machines/:code`): header with status, health, RUL and confidence;
 * tabs Live / Prediction / Timeline; a collapsible 3D rail on tablet and wider.
 */
export default function MachineDetail() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const screens = Grid.useBreakpoint();
  const [railOpen, setRailOpen] = useState(true);

  const assets = useAssets({ size: 200 });
  const asset = useMemo(() => assets.data?.items.find((a: Asset) => a.code === code), [assets.data, code]);

  const { data: latest, isPending: latestPending } = useTelemetryLatest(asset?.id ?? '');
  const { data: predLatest } = usePredictionsLatest(asset?.id ?? '');
  const pred = predLatest?.prediction ?? null;
  const explanation = useExplanationForPrediction(pred?.id);
  const live = useLiveTwinStore((s) => s.assets[code]);
  const alarmCounts = useActiveAlarmCounts();
  useLiveAssetFeed(useMemo(() => (asset ? [{ id: asset.id, code: asset.code }] : []), [asset]));

  const back = (
    <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
      {t('machine.backToFleet')}
    </Button>
  );

  if (assets.isPending) return <Skeleton active paragraph={{ rows: 8 }} />;
  if (!asset) {
    return <EmptyState description={t('machine.notFound', { code })} action={back} />;
  }

  const status = live?.status ?? asset.status;
  const statusColor = STATUS_PALETTE[assetStatusLevel(status)].color;
  const health = live?.health ?? pred?.health_index ?? null;
  const alarmCount = Math.max(live?.alarm_count ?? 0, alarmCounts[asset.id] ?? 0);
  const showRail = screens.md ?? true;

  const tabs = (
    <Tabs
      defaultActiveKey="live"
      items={[
        {
          key: 'live',
          label: t('machine.tab.live'),
          children: <LiveTab latestValues={latest?.values ?? []} pending={latestPending} />,
        },
        {
          key: 'prediction',
          label: t('machine.tab.prediction'),
          children: pred ? (
            <ExplanationCard explanationId={explanation.data?.id} assetId={asset.id} />
          ) : (
            <EmptyState description={t('machine.noPrediction')} />
          ),
        },
        {
          key: 'timeline',
          label: t('machine.tab.timeline'),
          children: <PredictionTimeline assetId={asset.id} />,
        },
      ]}
    />
  );

  return (
    <>
      <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/')} style={{ marginBottom: 8 }}>
        {t('nav.fleet')}
      </Button>

      <Card
        size="small"
        style={{ marginBottom: 16, borderInlineStart: `4px solid ${statusColor}` }}
        styles={{ body: { padding: '16px 20px' } }}
      >
        <Flex wrap gap={16} justify="space-between" align="center">
          <Flex vertical gap={4} style={{ minWidth: 0 }}>
            <Flex wrap gap={8} align="center">
              <Typography.Title level={1} style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
                {asset.name}
              </Typography.Title>
              <StatusTag status={status} />
              {pred?.source === 'edge' && (
                <Tooltip
                  title={
                    pred.latency_ms != null
                      ? t('machine.edgeHintLatency', { ms: Math.round(pred.latency_ms) })
                      : t('machine.edgeHint')
                  }
                >
                  <Tag icon={<CloudServerOutlined aria-hidden />} color="processing" style={{ marginInlineEnd: 0 }}>
                    {t('machine.edge')}
                  </Tag>
                </Tooltip>
              )}
            </Flex>
            <Flex wrap gap={8} align="center">
              <Typography.Text type="secondary">
                {asset.code} · {t(`assetType.${asset.asset_type}`, { defaultValue: asset.asset_type })}
              </Typography.Text>
              <FidelityBadge level={asset.fidelity_level} />
            </Flex>
          </Flex>
          <Flex wrap gap={20} align="center">
            <HealthGauge health={health} size={68} anomalyScore={pred?.anomaly_score} />
            <Flex vertical gap={4}>
              <RulBadge
                point={pred?.rul.point ?? live?.rul_point ?? null}
                low={pred?.rul.low ?? live?.rul_low ?? null}
                high={pred?.rul.high ?? live?.rul_high ?? null}
                unit={pred?.rul.unit ?? 'cycles'}
                coverage={pred?.rul.coverage}
              />
              {pred && <ConfidenceTag confidence={pred.confidence} />}
            </Flex>
            <Link to={`/explorer?asset=${encodeURIComponent(asset.code)}`}>
              <Button icon={<LineChartOutlined />}>{t('machine.openExplorer')}</Button>
            </Link>
            <Link to={`/machines/${asset.code}/grafana`}>
              <Button icon={<FundOutlined />}>{t('machine.openDashboard')}</Button>
            </Link>
            {showRail && (
              <Tooltip title={t(railOpen ? 'machine.hide3d' : 'machine.show3d')}>
                <Button
                  icon={railOpen ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                  aria-label={t(railOpen ? 'machine.hide3d' : 'machine.show3d')}
                  aria-expanded={railOpen}
                  onClick={() => setRailOpen((open) => !open)}
                />
              </Tooltip>
            )}
          </Flex>
        </Flex>
      </Card>

      <Row gutter={[16, 16]} wrap={false}>
        <Col flex="auto" style={{ minWidth: 0 }}>
          {tabs}
        </Col>
        {showRail && railOpen && (
          <Col flex="0 0 min(420px, 40%)">
            <Card
              size="small"
              title={
                <Flex gap={8} align="center">
                  <BlockOutlined aria-hidden />
                  {t('machine.model3d')}
                </Flex>
              }
              style={{ position: 'sticky', top: 72 }}
              styles={{ body: { background: token.colorBgContainer } }}
            >
              <Suspense fallback={<Skeleton.Node active style={{ width: '100%', height: 360 }} />}>
                <Machine3D code={asset.code} assetType={asset.asset_type} prediction={pred} alarmCount={alarmCount} />
              </Suspense>
            </Card>
          </Col>
        )}
      </Row>
    </>
  );
}

function LiveTab({ latestValues, pending }: { latestValues: TelemetryLatestValue[]; pending: boolean }) {
  const { t } = useTranslation();
  if (pending) return <Skeleton active paragraph={{ rows: 4 }} />;
  if (latestValues.length === 0) return <EmptyState description={t('machine.noTelemetry')} />;

  return (
    <Row gutter={[12, 12]}>
      {latestValues.map((sensor) => (
        <Col key={sensor.sensor_id} xs={12} sm={8} lg={6} xxl={4}>
          <SensorTile sensor={sensor} />
        </Col>
      ))}
    </Row>
  );
}
