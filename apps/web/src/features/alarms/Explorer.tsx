import { LineChartOutlined } from '@ant-design/icons';
import { Card, Checkbox, Col, Empty, Flex, Row, Select, Skeleton, Switch, Tag, Typography, theme } from 'antd';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { useChartTokens } from '../../app/theme';
import type { Alarm, Sensor, TelemetryAggPoint, TelemetryPoint, TelemetrySeries } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { PageHeader } from '../../components/PageHeader';
import { type ChartMarker, SeriesChart } from '../../components/SeriesChart';
import { TimeRangePicker, useTimeRange } from '../../components/TimeRangePicker';
import { useAssets, useSensors } from '../../hooks/useAssets';
import { useNow } from '../../hooks/useNow';
import { usePredictions } from '../../hooks/usePdm';
import { useAlarms, useTelemetry } from '../../hooks/useTelemetry';
import { STATUS_PALETTE } from '../../lib/status';

/** The categorical palette has eight validated hues; a ninth series would need a generated one. */
const MAX_SENSORS = 8;
const DEFAULT_SENSORS = 3;
const GROUP = 'explorer';

function pointValue(point: TelemetryPoint | TelemetryAggPoint): [string, number | null] {
  return 'bucket' in point ? [point.bucket, point.avg] : [point.time, point.value];
}

/**
 * A preset range ("last hour") keeps rolling while the page is open; a custom range stays put.
 * Recomputed every 30 s, which is also when the query keys change and the series refetch.
 */
function useRollingRange(range: { from: string; to: string; preset: string }) {
  const now = useNow(30_000);
  return useMemo(() => {
    if (range.preset === 'custom') return { from: range.from, to: range.to };
    const span = dayjs(range.to).diff(range.from);
    return { from: dayjs(now).subtract(span, 'ms').toISOString(), to: dayjs(now).toISOString() };
  }, [range, now]);
}

/**
 * Telemetry explorer (§9.7 `/explorer`): pick a machine and up to eight sensors and compare them over
 * time. Sensors are grouped by unit into stacked charts sharing one crosshair, with alarm raises and
 * the model's health index alongside. `?asset=` and `?sensors=` make any view linkable.
 */
export default function Explorer() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const chart = useChartTokens();
  const [params, setParams] = useSearchParams();
  const { range, setRange } = useTimeRange('1h');
  const window = useRollingRange(range);
  const [showHealth, setShowHealth] = useState(true);

  const assets = useAssets({ size: 200 });
  const assetCode = params.get('asset') ?? assets.data?.items[0]?.code ?? '';
  const asset = assets.data?.items.find((a) => a.code === assetCode);
  const sensorsQuery = useSensors(asset?.id);
  const sensors = useMemo(() => sensorsQuery.data ?? [], [sensorsQuery.data]);

  const picked = params.get('sensors');
  const selected = useMemo(
    () => (picked != null ? picked.split(',').filter(Boolean) : sensors.slice(0, DEFAULT_SENSORS).map((s) => s.code)),
    [picked, sensors],
  );

  const telemetry = useTelemetry(asset?.id ?? '', window.from, window.to, selected.join(',') || undefined);
  const predictions = usePredictions(showHealth ? (asset?.id ?? '') : '', window.from, window.to);
  const alarms = useAlarms({ asset_id: asset?.id, size: 200 });

  const update = (next: { asset?: string; sensors?: string[] }) => {
    const merged = new URLSearchParams(params);
    if (next.asset !== undefined) {
      merged.set('asset', next.asset);
      merged.delete('sensors');
    }
    if (next.sensors !== undefined) merged.set('sensors', next.sensors.join(','));
    setParams(merged, { replace: true });
  };

  // Colour follows the sensor's position on the machine, so deselecting one never repaints the rest.
  const colorOf = useMemo(() => {
    const index = new Map(sensors.map((s, i) => [s.id, i]));
    return (sensorId: string) => chart.series[(index.get(sensorId) ?? 0) % chart.series.length];
  }, [sensors, chart]);

  const alarmMarkers = useMemo<ChartMarker[]>(() => {
    const start = dayjs(window.from);
    return (alarms.data?.items ?? [])
      .filter((a: Alarm) => dayjs(a.raised_at).isAfter(start))
      .map((a) => ({
        axis: 'x' as const,
        value: a.raised_at,
        label: `${a.severity}: ${a.title}`,
        color: STATUS_PALETTE[a.severity === 'info' ? 'neutral' : a.severity].color,
      }));
  }, [alarms.data, window.from]);

  const panels = useMemo(() => {
    const bySensor = new Map(sensors.map((s) => [s.id, s]));
    const groups = new Map<string, { series: TelemetrySeries; sensor?: Sensor }[]>();
    for (const series of telemetry.data ?? []) {
      const list = groups.get(series.unit) ?? [];
      list.push({ series, sensor: bySensor.get(series.sensor_id) });
      groups.set(series.unit, list);
    }
    return [...groups.entries()].map(([unit, members]) => {
      const thresholds: ChartMarker[] = [];
      // Limits are drawn only when a chart holds one sensor: two sensors' limits on one axis mislead.
      const only = members.length === 1 ? members[0].sensor : undefined;
      if (only) {
        const limit = (value: number | null, key: string, level: 'warning' | 'critical') =>
          value != null &&
          thresholds.push({ axis: 'y', value, label: t(key), color: STATUS_PALETTE[level].color });
        limit(only.warn_high, 'explorer.warnHigh', 'warning');
        limit(only.alarm_high, 'explorer.alarmHigh', 'critical');
        limit(only.warn_low, 'explorer.warnLow', 'warning');
        limit(only.alarm_low, 'explorer.alarmLow', 'critical');
      }
      return {
        unit,
        markers: [...thresholds, ...alarmMarkers],
        series: members.map(({ series, sensor }) => ({
          name: sensor?.name ?? series.metric_name,
          color: colorOf(series.sensor_id),
          data: series.points.map(pointValue),
        })),
      };
    });
  }, [telemetry.data, sensors, alarmMarkers, colorOf, t]);

  const healthSeries = useMemo(
    () => [
      {
        name: t('explorer.health'),
        color: token.colorPrimary,
        step: true,
        data: (predictions.data ?? []).map((p): [string, number | null] => [p.time, p.health_index]),
      },
    ],
    [predictions.data, token, t],
  );

  const toggle = (code: string, on: boolean) =>
    update({ sensors: on ? [...selected, code] : selected.filter((c) => c !== code) });

  return (
    <>
      <PageHeader
        title={t('explorer.title')}
        subtitle={t('explorer.subtitle')}
        actions={<TimeRangePicker value={range} onChange={setRange} />}
      />
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={7} xxl={5}>
          <Card size="small" title={t('explorer.machine')}>
            <Flex vertical gap={12}>
              <Select
                showSearch
                optionFilterProp="label"
                loading={assets.isPending}
                value={asset?.code}
                onChange={(code: string) => update({ asset: code })}
                options={(assets.data?.items ?? []).map((a) => ({ value: a.code, label: `${a.code} — ${a.name}` }))}
                aria-label={t('explorer.machine')}
              />
              {asset && (
                <Link to={`/machines/${asset.code}`}>
                  <Typography.Text type="secondary">{t('explorer.openMachine')}</Typography.Text>
                </Link>
              )}
              <Flex justify="space-between" align="center">
                <Typography.Text strong>{t('explorer.sensors')}</Typography.Text>
                <Typography.Text type="secondary" className="tabular">
                  {selected.length}/{MAX_SENSORS}
                </Typography.Text>
              </Flex>
              {sensorsQuery.isPending && asset ? (
                <Skeleton active paragraph={{ rows: 5 }} title={false} />
              ) : (
                <Flex vertical gap={6}>
                  {sensors.map((s) => {
                    const on = selected.includes(s.code);
                    return (
                      <Checkbox
                        key={s.id}
                        checked={on}
                        disabled={!on && selected.length >= MAX_SENSORS}
                        onChange={(e) => toggle(s.code, e.target.checked)}
                      >
                        <Flex gap={8} align="center">
                          <span
                            aria-hidden
                            style={{ width: 10, height: 10, borderRadius: 2, background: colorOf(s.id), flexShrink: 0 }}
                          />
                          <span>{s.name}</span>
                          <Typography.Text type="secondary">{s.unit}</Typography.Text>
                        </Flex>
                      </Checkbox>
                    );
                  })}
                </Flex>
              )}
              <Flex justify="space-between" align="center" style={{ paddingTop: 8, borderTop: `1px solid ${token.colorBorder}` }}>
                <label htmlFor="explorer-health">{t('explorer.showHealth')}</label>
                <Switch id="explorer-health" size="small" checked={showHealth} onChange={setShowHealth} />
              </Flex>
            </Flex>
          </Card>
        </Col>
        <Col xs={24} lg={17} xxl={19}>
          <Card
            size="small"
            title={asset ? `${asset.name} · ${asset.code}` : t('explorer.title')}
            extra={alarmMarkers.length > 0 && <Tag color="warning">{t('explorer.alarmsInRange', { count: alarmMarkers.length })}</Tag>}
          >
            {!asset ? (
              <EmptyState icon={<LineChartOutlined />} description={t('explorer.pickMachine')} />
            ) : selected.length === 0 ? (
              <EmptyState icon={<LineChartOutlined />} description={t('explorer.pickSensors')} />
            ) : telemetry.isPending ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : panels.every((p) => p.series.every((s) => s.data.length === 0)) ? (
              <EmptyState icon={<LineChartOutlined />} description={t('explorer.noData')} />
            ) : (
              <Flex vertical gap={8}>
                {panels.map((panel) => (
                  <SeriesChart
                    key={panel.unit}
                    unit={panel.unit}
                    series={panel.series}
                    markers={panel.markers}
                    from={window.from}
                    to={window.to}
                    group={GROUP}
                  />
                ))}
                {showHealth &&
                  (healthSeries[0].data.length ? (
                    <SeriesChart
                      unit="%"
                      series={healthSeries}
                      from={window.from}
                      to={window.to}
                      group={GROUP}
                      height={160}
                      yMin={0}
                      yMax={100}
                      digits={1}
                    />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('explorer.noPredictions')} />
                  ))}
              </Flex>
            )}
          </Card>
        </Col>
      </Row>
    </>
  );
}
