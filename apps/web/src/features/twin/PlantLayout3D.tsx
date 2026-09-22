import { BlockOutlined } from '@ant-design/icons';
import { OrbitControls } from '@react-three/drei';
import { Canvas, type ThreeEvent } from '@react-three/fiber';
import { Flex, Tag, Typography, theme } from 'antd';
import { useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { Group } from 'three';

import type { AssetStatus, TreeAsset } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { PageHeader } from '../../components/PageHeader';
import { useLiveAssetFeed } from '../../hooks/useLiveFeed';
import { useActiveAlarmCounts } from '../../hooks/useTelemetry';
import { useTwinTree } from '../../hooks/useTwin';
import { STATUS_PALETTE, statusTextColor, withAlpha, type StatusLevel } from '../../lib/status';
import { useLiveTwinStore } from '../../store/liveTwinStore';
import { useUiStore } from '../../store/uiStore';
import { CanvasBoundary } from '../../three/CanvasBoundary';
import { assetLevel } from '../../three/healthMaterial';
import { layoutAssets, layoutBounds, plantAssets, type Placement } from '../../three/layout';
import { HOUSING_COLOR, MachineContext } from '../../three/machineContext';
import { MACHINE_HEIGHT, MachineModel } from '../../three/MachineModel';
import { SceneLights } from '../../three/SceneLights';
import { ThemedHtml } from '../../three/ThemedHtml';
import { useAlarmPulse } from '../../three/useAlarmPulse';
import { QueryView } from './QueryView';

const LEGEND: StatusLevel[] = ['good', 'warning', 'serious', 'critical', 'neutral'];

interface NodeProps {
  asset: TreeAsset;
  placement: Placement;
  status: AssetStatus;
  health: number | null;
  alarms: number;
  onOpen: (code: string) => void;
}

function AssetNode({ asset, placement, status, health, alarms, onOpen }: NodeProps) {
  const { t } = useTranslation();
  const ref = useRef<Group>(null);
  const mode = useUiStore((s) => s.themeMode);
  const level = assetLevel(status, health);
  const { color, Icon } = STATUS_PALETTE[level];
  useAlarmPulse(ref, alarms > 0);

  const context = useMemo(
    () => ({
      health: Object.fromEntries(asset.components.map((c) => [c.code, c.health])),
      housing: HOUSING_COLOR[mode],
    }),
    [asset.components, mode],
  );
  const open = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation();
    onOpen(asset.code);
  };
  const label = `${asset.name} · ${t(`status.asset.${status}`)}${health === null ? '' : ` · ${Math.round(health)}`}`;

  return (
    <group position={[placement.x, placement.y, placement.z]} rotation={[0, placement.rot, 0]}>
      {/* Floor pad in the asset's status colour: readable from far away even when parts are small */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]}>
        <circleGeometry args={[2.3, 40]} />
        <meshStandardMaterial color={color} transparent opacity={0.28} />
      </mesh>
      <group
        ref={ref}
        onClick={open}
        onPointerOver={(e) => {
          e.stopPropagation();
          document.body.style.cursor = 'pointer';
        }}
        onPointerOut={() => {
          document.body.style.cursor = '';
        }}
      >
        <MachineContext.Provider value={context}>
          <MachineModel assetType={asset.asset_type} />
        </MachineContext.Provider>
      </group>
      <ThemedHtml position={[0, MACHINE_HEIGHT[asset.asset_type] + 0.5, 0]} center zIndexRange={[10, 0]}>
        {/* A real button, so the plant is navigable by keyboard and screen reader as well as by mouse. */}
        <button
          type="button"
          onClick={() => onOpen(asset.code)}
          aria-label={label}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '2px 10px',
            whiteSpace: 'nowrap',
            border: 'none',
            borderRadius: 999,
            cursor: 'pointer',
            font: '500 12px/20px Inter, system-ui, sans-serif',
            background: withAlpha(color, 0.22),
            color: statusTextColor(level, mode),
            backdropFilter: 'blur(4px)',
          }}
        >
          <Icon aria-hidden />
          {asset.code}
          {alarms > 0 && <span className="tabular">· {alarms}</span>}
        </button>
      </ThemedHtml>
    </group>
  );
}

/**
 * `/twin/3d` (FR-DT-07): every asset on the plant floor, coloured by the worse of its run state and
 * health (live from `/ws/live` when available, else the twin tree), pulsing while it has open alarms.
 * Click a machine or its label to open it.
 */
export default function PlantLayout3D() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const mode = useUiStore((s) => s.themeMode);
  const navigate = useNavigate();
  const tree = useTwinTree();
  const live = useLiveTwinStore((s) => s.assets);
  const alarmCounts = useActiveAlarmCounts();

  const assets = useMemo(() => {
    const byCode = new Map<string, TreeAsset>();
    for (const plant of tree.data?.plants ?? [])
      for (const line of plant.lines) for (const asset of line.assets) byCode.set(asset.code, asset);
    return byCode;
  }, [tree.data]);
  const placements = useMemo(() => (tree.data ? layoutAssets(plantAssets(tree.data)) : []), [tree.data]);
  const bounds = useMemo(() => layoutBounds(placements), [placements]);
  useLiveAssetFeed(useMemo(() => [...assets.values()].map(({ id, code }) => ({ id, code })), [assets]));

  const open = (code: string) => navigate(`/machines/${code}`);
  const legend = (
    <Flex wrap gap={6} role="list" aria-label={t('twin3d.legend')}>
      {LEGEND.map((level) => {
        const { color, Icon } = STATUS_PALETTE[level];
        return (
          <Tag
            key={level}
            role="listitem"
            bordered={false}
            icon={<Icon aria-hidden />}
            style={{ background: withAlpha(color, 0.16), color: statusTextColor(level, mode), marginInlineEnd: 0 }}
          >
            {t(`status.level.${level}`)}
          </Tag>
        );
      })}
    </Flex>
  );

  return (
    <>
      <PageHeader title={t('twin3d.title')} subtitle={t('twin3d.subtitle')} actions={legend} />
      <QueryView query={tree} rows={10}>
        {() =>
          placements.length === 0 ? (
            <EmptyState icon={<BlockOutlined />} description={t('twin.empty.noAssets')} />
          ) : (
            <CanvasBoundary fallback={<EmptyState icon={<BlockOutlined />} description={t('twin3d.unavailable')} />}>
              <div
                style={{
                  height: 'calc(100vh - 220px)',
                  minHeight: 420,
                  borderRadius: 12,
                  overflow: 'hidden',
                  border: `1px solid ${token.colorBorder}`,
                  background: token.colorBgLayout,
                }}
              >
                <Canvas
                  frameloop="demand"
                  dpr={[1, 2]}
                  camera={{
                    position: [bounds.cx + bounds.radius * 0.6, bounds.radius * 0.9, bounds.cz + bounds.radius * 1.1],
                    fov: 45,
                  }}
                  role="img"
                  aria-label={t('twin3d.plantAria', { count: placements.length })}
                >
                  <SceneLights />
                  <mesh rotation={[-Math.PI / 2, 0, 0]} position={[bounds.cx, 0, bounds.cz]}>
                    <planeGeometry args={[bounds.width, bounds.depth]} />
                    <meshStandardMaterial color={token.colorBgContainer} />
                  </mesh>
                  {placements.map((placement) => {
                    const asset = assets.get(placement.code);
                    if (!asset) return null;
                    const state = live[asset.code];
                    return (
                      <AssetNode
                        key={asset.code}
                        asset={asset}
                        placement={placement}
                        status={state?.status ?? asset.status}
                        health={state?.health ?? asset.health}
                        alarms={Math.max(state?.alarm_count ?? 0, alarmCounts[asset.id] ?? 0)}
                        onOpen={open}
                      />
                    );
                  })}
                  <OrbitControls
                    makeDefault
                    target={[bounds.cx, 0, bounds.cz]}
                    maxPolarAngle={Math.PI / 2.1}
                    minDistance={4}
                    maxDistance={bounds.radius * 3}
                  />
                </Canvas>
              </div>
            </CanvasBoundary>
          )
        }
      </QueryView>
      <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0, fontSize: 12 }}>
        {t('twin3d.hint')}
      </Typography.Paragraph>
    </>
  );
}
