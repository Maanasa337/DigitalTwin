import { ArrowLeftOutlined } from '@ant-design/icons';
import { Button, Col, Row, Skeleton, Space, Tabs, Tag, theme, Typography } from 'antd';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import type { TelemetryLatestValue } from '../../api/types';
import { useAssets } from '../../hooks/useAssets';
import { useTelemetryLatest } from '../../hooks/useTelemetry';
import { usePredictionsLatest } from '../../hooks/usePdm';
import { HealthGauge } from '../../components/HealthGauge';
import { RulBadge } from '../../components/RulBadge';
import { SensorTile } from '../../components/SensorTile';
import { assetStatusLevel, STATUS_PALETTE } from '../../lib/status';
import { useLiveTwinStore } from '../../store/liveTwinStore';
import type { Asset } from '../../api/types';

const { Title, Text } = Typography;

/**
 * Machine detail page — header with health/RUL/status, tabs: Live, Prediction, Timeline.
 */
export default function MachineDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { token } = theme.useToken();

  const { data: assetsPage, isLoading: assetsLoading } = useAssets({ size: 200 });
  const asset = useMemo(
    () => assetsPage?.items.find((a: Asset) => a.code === code),
    [assetsPage, code],
  );

  const { data: latest } = useTelemetryLatest(asset?.id ?? '');
  const { data: predLatest } = usePredictionsLatest(asset?.id ?? '');
  const live = useLiveTwinStore((s) => (code ? s.assets[code] : undefined));

  if (assetsLoading || !code) {
    return (
      <div style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

  if (!asset) {
    return (
      <div style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          {t('common.back', 'Back')}
        </Button>
        <div style={{ marginTop: 24, textAlign: 'center' }}>
          <Text type="secondary">Machine "{code}" not found</Text>
        </div>
      </div>
    );
  }

  const statusLevel = assetStatusLevel(asset.status);
  const statusColor = STATUS_PALETTE[statusLevel].color;
  const health = live?.health ?? predLatest?.prediction?.health_index ?? null;
  const pred = predLatest?.prediction;

  return (
    <div style={{ padding: 24 }}>
      {/* Back button */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/')}
        style={{ marginBottom: 12 }}
      >
        Fleet
      </Button>

      {/* Header */}
      <div
        style={{
          background: token.colorBgContainer,
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadiusLG,
          padding: '20px 24px',
          marginBottom: 20,
          borderLeft: `4px solid ${statusColor}`,
        }}
      >
        <Row gutter={24} align="middle">
          <Col flex="auto">
            <Space direction="vertical" size={0}>
              <Title level={4} style={{ margin: 0 }}>
                {asset.name}
              </Title>
              <Text type="secondary">
                {asset.code} · {asset.asset_type.replace(/_/g, ' ')} · Fidelity L{asset.fidelity_level}
              </Text>
            </Space>
          </Col>
          <Col>
            <Space size={20} align="center">
              <HealthGauge health={health} size={68} anomalyScore={pred?.anomaly_score} />
              <div>
                <RulBadge
                  point={pred?.rul.point ?? live?.rul_point ?? null}
                  low={pred?.rul.low ?? live?.rul_low ?? null}
                  high={pred?.rul.high ?? live?.rul_high ?? null}
                  unit={pred?.rul.unit ?? 'cycles'}
                  coverage={pred?.rul.coverage}
                />
                {pred?.confidence.label && (
                  <div style={{ marginTop: 4 }}>
                    <Tag
                      color={
                        pred.confidence.label === 'high'
                          ? 'green'
                          : pred.confidence.label === 'medium'
                            ? 'orange'
                            : 'red'
                      }
                      style={{ fontSize: 11 }}
                    >
                      {pred.confidence.label} confidence
                    </Tag>
                  </div>
                )}
              </div>
              <Tag
                color={statusColor}
                style={{ fontSize: 13, fontWeight: 600, padding: '4px 12px', borderRadius: 6 }}
              >
                {asset.status}
              </Tag>
            </Space>
          </Col>
        </Row>
      </div>

      {/* Tabs */}
      <Tabs
        defaultActiveKey="live"
        items={[
          {
            key: 'live',
            label: t('machine.tab.live', 'Live'),
            children: <LiveTab latestValues={latest?.values ?? []} />,
          },
          {
            key: 'prediction',
            label: t('machine.tab.prediction', 'Prediction'),
            children: (
              <div style={{ padding: 16, color: token.colorTextSecondary, textAlign: 'center' }}>
                Prediction charts will appear once ECharts is installed and models are trained.
              </div>
            ),
          },
          {
            key: 'timeline',
            label: t('machine.tab.timeline', 'Timeline'),
            children: (
              <div style={{ padding: 16, color: token.colorTextSecondary, textAlign: 'center' }}>
                Timeline view — state events, alarms, and predictions merged chronologically.
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

function LiveTab({
  latestValues,
}: {
  latestValues: TelemetryLatestValue[];
}) {
  if (latestValues.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Skeleton active paragraph={{ rows: 4 }} />
      </div>
    );
  }

  return (
    <Row gutter={[12, 12]} style={{ padding: '8px 0' }}>
      {latestValues.map((sensor) => (
        <Col key={sensor.sensor_id} xs={12} sm={8} md={6} lg={4}>
          <SensorTile sensor={sensor} />
        </Col>
      ))}
    </Row>
  );
}
