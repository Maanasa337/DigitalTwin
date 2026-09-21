import {
  AlertOutlined,
  AppstoreOutlined,
  SearchOutlined,
  TableOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Button, Card, Col, Empty, Input, Row, Select, Skeleton, Space, Tag, Tooltip, theme } from 'antd';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useAssets } from '../../hooks/useAssets';
import type { Asset, AssetStatus, LiveAsset } from '../../api/types';
import { HealthGauge } from '../../components/HealthGauge';
import { RulBadge } from '../../components/RulBadge';
import { STATUS_PALETTE, assetStatusLevel } from '../../lib/status';
import { useLiveTwinStore } from '../../store/liveTwinStore';

const STATUS_OPTIONS: AssetStatus[] = ['RUNNING', 'IDLE', 'MAINTENANCE', 'DOWN', 'UNKNOWN'];

/**
 * Fleet overview — responsive card grid showing all machines with live health, RUL, status.
 */
export default function Fleet() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const { data, isLoading } = useAssets({ size: 200 });
  const liveAssets = useLiveTwinStore((s) => s.assets);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<AssetStatus | 'ALL'>('ALL');
  const [viewMode, setViewMode] = useState<'card' | 'table'>('card');

  const assets = useMemo(() => {
    let items = data?.items ?? [];
    if (search) {
      const q = search.toLowerCase();
      items = items.filter(
        (a: Asset) => a.name.toLowerCase().includes(q) || a.code.toLowerCase().includes(q),
      );
    }
    if (statusFilter !== 'ALL') {
      items = items.filter((a: Asset) => a.status === statusFilter);
    }
    return items;
  }, [data?.items, search, statusFilter]);

  if (isLoading) {
    return (
      <div style={{ padding: 24 }}>
        <Row gutter={[16, 16]}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Col key={i} xs={24} sm={12} lg={8} xl={6}>
              <Card style={{ borderRadius: token.borderRadiusLG }}>
                <Skeleton active paragraph={{ rows: 3 }} />
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    );
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Toolbar */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder={t('fleet.search', 'Search machines...')}
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
          style={{ width: 220 }}
        />
        <Select
          value={statusFilter}
          onChange={setStatusFilter}
          style={{ width: 140 }}
          options={[
            { label: 'All Status', value: 'ALL' },
            ...STATUS_OPTIONS.map((s) => ({ label: s, value: s })),
          ]}
        />
        <Button.Group>
          <Button
            icon={<AppstoreOutlined />}
            type={viewMode === 'card' ? 'primary' : 'default'}
            onClick={() => setViewMode('card')}
          />
          <Button
            icon={<TableOutlined />}
            type={viewMode === 'table' ? 'primary' : 'default'}
            onClick={() => setViewMode('table')}
          />
        </Button.Group>
      </Space>

      {assets.length === 0 ? (
        <Empty description={t('fleet.empty', 'No machines found')} />
      ) : (
        <Row gutter={[16, 16]}>
          {assets.map((asset: Asset) => (
            <Col key={asset.id} xs={24} sm={12} lg={8} xl={6}>
              <FleetCard
                asset={asset}
                live={liveAssets[asset.code]}
                onClick={() => navigate(`/machines/${asset.code}`)}
              />
            </Col>
          ))}
        </Row>
      )}
    </div>
  );
}

function FleetCard({ asset, live, onClick }: { asset: Asset; live?: LiveAsset; onClick: () => void }) {
  const { token } = theme.useToken();
  const statusLevel = assetStatusLevel(asset.status);
  const statusColor = STATUS_PALETTE[statusLevel].color;

  const health = live?.health ?? null;
  const alarmCount = live?.alarm_count ?? 0;

  return (
    <Card
      hoverable
      onClick={onClick}
      style={{
        borderRadius: token.borderRadiusLG,
        borderLeft: `3px solid ${statusColor}`,
        cursor: 'pointer',
        transition: 'box-shadow 0.2s ease, transform 0.2s ease',
      }}
      styles={{ body: { padding: '16px 18px' } }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 15, color: token.colorText }}>{asset.name}</div>
          <div style={{ fontSize: 12, color: token.colorTextSecondary }}>
            {asset.code} · {asset.asset_type.replace(/_/g, ' ')}
          </div>
        </div>
        <Tag
          color={statusColor}
          style={{ fontSize: 11, fontWeight: 600, border: 'none', borderRadius: 4, margin: 0 }}
        >
          {asset.status}
        </Tag>
      </div>

      {/* Health + RUL row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 8 }}>
        <HealthGauge health={health} size={56} />
        <div style={{ flex: 1 }}>
          <RulBadge
            point={live?.rul_point ?? null}
            low={live?.rul_low ?? null}
            high={live?.rul_high ?? null}
          />
        </div>
      </div>

      {/* Footer: alarm count + power */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12, color: token.colorTextSecondary }}>
        <Tooltip title="Active alarms">
          <Space size={4}>
            <AlertOutlined style={{ color: alarmCount > 0 ? '#d03b3b' : token.colorTextQuaternary }} />
            <span>{alarmCount}</span>
          </Space>
        </Tooltip>
        {live?.metrics?.power_kw && (
          <Tooltip title="Current power">
            <Space size={4}>
              <ThunderboltOutlined />
              <span>{live.metrics.power_kw.v.toFixed(1)} kW</span>
            </Space>
          </Tooltip>
        )}
      </div>
    </Card>
  );
}
