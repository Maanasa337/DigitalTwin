import { ArrowDownOutlined, ArrowUpOutlined, BlockOutlined } from '@ant-design/icons';
import { OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { Button, Flex, Result, Skeleton, Typography, theme } from 'antd';
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Group } from 'three';

import type { AssetType, Attribution, Prediction, Rul } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { HealthDot } from '../../components/HealthDot';
import { RulBadge } from '../../components/RulBadge';
import { StatusTag } from '../../components/StatusTag';
import { useTwin, useTwinTree } from '../../hooks/useTwin';
import { useExplanationForPrediction } from '../../hooks/useXai';
import { useUiStore } from '../../store/uiStore';
import { CanvasBoundary } from '../../three/CanvasBoundary';
import { HOUSING_COLOR, MachineContext, type Vec3 } from '../../three/machineContext';
import { MACHINE_HEIGHT, MachineModel } from '../../three/MachineModel';
import { SceneLights } from '../../three/SceneLights';
import { ThemedHtml } from '../../three/ThemedHtml';
import { useAlarmPulse } from '../../three/useAlarmPulse';
import { findAsset } from './treeData';

export interface Machine3DProps {
  code: string;
  assetType: AssetType;
  prediction?: Prediction | null;
  alarmCount: number;
  height?: number;
}

interface ComponentInfo {
  code: string;
  name: string;
  health: number | null;
  rul: Rul | null;
}

/**
 * The strongest driver for one component: an attribution whose feature is namespaced by the
 * component code (`spindle.vib_rms_mean`), else the top-ranked one for the whole prediction.
 */
function driverFor(attributions: Attribution[], code: string): Attribution | undefined {
  const ranked = [...attributions].sort((a, b) => a.rank - b.rank);
  return ranked.find((a) => a.feature.startsWith(`${code}.`) || a.feature.startsWith(`${code}_`)) ?? ranked[0];
}

function Tooltip3D({ info, driver }: { info: ComponentInfo; driver?: Attribution }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  return (
    <Flex
      vertical
      gap={6}
      style={{
        minWidth: 200,
        padding: '10px 12px',
        background: token.colorBgElevated,
        border: `1px solid ${token.colorBorder}`,
        borderRadius: 8,
        color: token.colorText,
        pointerEvents: 'none',
        transform: 'translate(12px, -50%)',
      }}
    >
      <Flex justify="space-between" align="center" gap={8}>
        <Typography.Text strong>{info.name}</Typography.Text>
        <StatusTag health={info.health} compact />
      </Flex>
      <RulBadge point={info.rul?.point} low={info.rul?.low} high={info.rul?.high} unit={info.rul?.unit} />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t('twin3d.topDriver')}
      </Typography.Text>
      {driver ? (
        <Flex gap={6} align="center" style={{ fontSize: 12 }}>
          {driver.direction === 'lowering' ? <ArrowDownOutlined aria-hidden /> : <ArrowUpOutlined aria-hidden />}
          <span>{driver.label}</span>
          <span className="tabular" style={{ color: token.colorTextSecondary }}>
            {Math.round(driver.share * 100)} %
          </span>
        </Flex>
      ) : (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('twin3d.noDriver')}
        </Typography.Text>
      )}
    </Flex>
  );
}

interface SceneProps {
  assetType: AssetType;
  components: ComponentInfo[];
  hovered: { code: string; point: Vec3 } | null;
  onHover: (code: string | null, point?: Vec3) => void;
  pulsing: boolean;
  attributions: Attribution[];
}

function MachineScene({ assetType, components, hovered, onHover, pulsing, attributions }: SceneProps) {
  const ref = useRef<Group>(null);
  const mode = useUiStore((s) => s.themeMode);
  const { token } = theme.useToken();
  useAlarmPulse(ref, pulsing);

  const context = useMemo(
    () => ({
      health: Object.fromEntries(components.map((c) => [c.code, c.health])),
      housing: HOUSING_COLOR[mode],
      hovered: hovered?.code ?? null,
      onHover,
    }),
    [components, mode, hovered, onHover],
  );
  const info = hovered && components.find((c) => c.code === hovered.code);

  return (
    <MachineContext.Provider value={context}>
      <group ref={ref}>
        <MachineModel assetType={assetType} />
      </group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.001, 0]}>
        <circleGeometry args={[3.2, 48]} />
        <meshStandardMaterial color={token.colorBgContainer} />
      </mesh>
      {info && hovered && (
        <ThemedHtml position={hovered.point} zIndexRange={[10, 0]}>
          <Tooltip3D info={info} driver={driverFor(attributions, info.code)} />
        </ThemedHtml>
      )}
    </MachineContext.Provider>
  );
}

/**
 * FR-DT-06: the asset's procedural model with each component coloured by its health band. Hover (or
 * focus a component in the list below, for keyboard users) shows name, RUL and the top driver from
 * the latest explanation; clicking a component in the list pins that highlight until it is clicked
 * again, and hovering elsewhere only previews over it. Open alarms make the model pulse.
 */
export default function Machine3D({ code, assetType, prediction, alarmCount, height = 360 }: Machine3DProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const twin = useTwin(code);
  const tree = useTwinTree();
  const explanation = useExplanationForPrediction(prediction?.id);
  const [hovered, setHovered] = useState<{ code: string; point: Vec3 } | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);

  const components = useMemo<ComponentInfo[]>(() => {
    const live = twin.data?.features.components?.properties ?? {};
    const registered = (tree.data && findAsset(tree.data, code)?.components) || [];
    const codes = [...new Set([...registered.map((c) => c.code), ...Object.keys(live)])];
    return codes.map((c) => {
      const known = registered.find((r) => r.code === c);
      return {
        code: c,
        name: known?.name ?? c,
        health: live[c]?.health ?? known?.health ?? null,
        rul: live[c]?.rul ?? known?.rul ?? null,
      };
    });
  }, [twin.data, tree.data, code]);

  const onHover = useMemo(
    () => (c: string | null, point?: Vec3) => setHovered(c ? { code: c, point: point ?? [0, MACHINE_HEIGHT[assetType], 0] } : null),
    [assetType],
  );

  // A hover previews over the pin; with nothing hovered the pinned component stays lit.
  const highlighted = useMemo(
    () => hovered ?? (pinned ? { code: pinned, point: [0, MACHINE_HEIGHT[assetType], 0] as Vec3 } : null),
    [hovered, pinned, assetType],
  );

  if (twin.isPending && tree.isPending) return <Skeleton.Node active style={{ width: '100%', height }} />;
  if (twin.isError && tree.isError) {
    return (
      <Result
        status="error"
        title={t('errors.loadFailed')}
        extra={
          <Button onClick={() => void Promise.all([twin.refetch(), tree.refetch()])}>{t('common.retry')}</Button>
        }
      />
    );
  }

  return (
    <Flex vertical gap={12}>
      <CanvasBoundary fallback={<EmptyState icon={<BlockOutlined />} description={t('twin3d.unavailable')} />}>
        <div style={{ height, borderRadius: 8, overflow: 'hidden', background: token.colorBgLayout }}>
          <Canvas
            frameloop="demand"
            dpr={[1, 2]}
            camera={{ position: [4.5, 3.6, 5.5], fov: 40 }}
            role="img"
            aria-label={t('twin3d.machineAria', { code })}
            onPointerMissed={() => setHovered(null)}
          >
            <SceneLights />
            <MachineScene
              assetType={assetType}
              components={components}
              hovered={highlighted}
              onHover={onHover}
              pulsing={alarmCount > 0}
              attributions={explanation.data?.attributions ?? []}
            />
            <OrbitControls
              makeDefault
              enablePan={false}
              minDistance={3}
              maxDistance={14}
              maxPolarAngle={Math.PI / 2.05}
              target={[0, 1.1, 0]}
            />
          </Canvas>
        </div>
      </CanvasBoundary>
      {components.length === 0 ? (
        <Typography.Text type="secondary">{t('twin3d.noComponents')}</Typography.Text>
      ) : (
        <Flex wrap gap={4} role="list" aria-label={t('twin3d.components')}>
          {components.map((c) => (
            <div key={c.code} role="listitem">
              <Button
                size="small"
                type={pinned === c.code || hovered?.code === c.code ? 'primary' : 'text'}
                ghost={pinned !== c.code && hovered?.code === c.code}
                aria-pressed={pinned === c.code}
                onClick={() => setPinned((current) => (current === c.code ? null : c.code))}
                onMouseEnter={() => onHover(c.code)}
                onFocus={() => onHover(c.code)}
                onMouseLeave={() => onHover(null)}
                onBlur={() => onHover(null)}
              >
                <Flex gap={6} align="center">
                  <HealthDot health={c.health} />
                  {c.name}
                </Flex>
              </Button>
            </div>
          ))}
        </Flex>
      )}
    </Flex>
  );
}
