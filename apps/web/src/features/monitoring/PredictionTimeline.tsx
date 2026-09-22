import { FieldTimeOutlined } from '@ant-design/icons';
import { Card, Col, Flex, List, Row, Skeleton, Tag, Typography, theme } from 'antd';
import dayjs from 'dayjs';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { Alarm } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { type ChartMarker, SeriesChart } from '../../components/SeriesChart';
import { TimeRangePicker, useTimeRange } from '../../components/TimeRangePicker';
import { useNow } from '../../hooks/useNow';
import { usePredictions } from '../../hooks/usePdm';
import { useAlarms } from '../../hooks/useTelemetry';
import { formatDateTime } from '../../lib/format';
import { STATUS_PALETTE } from '../../lib/status';

const GROUP = 'machine-timeline';

function severityLevel(severity: Alarm['severity']) {
  return severity === 'info' ? 'neutral' : severity;
}

/**
 * Machine timeline tab: the model's health index and remaining life (with its conformal interval)
 * over the chosen window, alarm raises marked on both, and the alarms themselves listed below.
 */
export function PredictionTimeline({ assetId }: { assetId: string }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { range, setRange } = useTimeRange('24h');
  const now = useNow(60_000);
  const window = useMemo(() => {
    if (range.preset === 'custom') return { from: range.from, to: range.to };
    const span = dayjs(range.to).diff(range.from);
    return { from: dayjs(now).subtract(span, 'ms').toISOString(), to: dayjs(now).toISOString() };
  }, [range, now]);

  const predictions = usePredictions(assetId, window.from, window.to);
  const alarms = useAlarms({ asset_id: assetId, size: 200 });

  const inRange = useMemo(
    () => (alarms.data?.items ?? []).filter((a) => dayjs(a.raised_at).isAfter(window.from)),
    [alarms.data, window.from],
  );
  const markers = useMemo<ChartMarker[]>(
    () =>
      inRange.map((a) => ({
        axis: 'x',
        value: a.raised_at,
        label: `${a.severity}: ${a.title}`,
        color: STATUS_PALETTE[severityLevel(a.severity)].color,
      })),
    [inRange],
  );

  const rows = useMemo(() => predictions.data ?? [], [predictions.data]);
  const unit = rows.find((p) => p.rul.unit)?.rul.unit ?? '';
  const sources = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of rows) counts[p.source] = (counts[p.source] ?? 0) + 1;
    return counts;
  }, [rows]);

  const health = useMemo(
    () => [
      {
        name: t('machine.timeline.health'),
        color: token.colorPrimary,
        step: true,
        data: rows.map((p): [string, number | null] => [p.time, p.health_index]),
      },
    ],
    [rows, token, t],
  );
  const rul = useMemo(
    () => [
      {
        name: t('machine.timeline.rul'),
        color: token.colorPrimary,
        data: rows.map((p): [string, number | null] => [p.time, p.rul.point]),
        band: rows.map((p): [string, number | null, number | null] => [p.time, p.rul.low, p.rul.high]),
      },
    ],
    [rows, token, t],
  );

  return (
    <Flex vertical gap={16}>
      <Flex wrap gap={8} justify="space-between" align="center">
        <Flex wrap gap={8} align="center">
          {Object.entries(sources).map(([source, count]) => (
            <Tag key={source} color={source === 'edge' ? 'processing' : 'default'} style={{ marginInlineEnd: 0 }}>
              {t(`machine.timeline.source.${source}`, { count, defaultValue: `${source}: ${count}` })}
            </Tag>
          ))}
        </Flex>
        <TimeRangePicker value={range} onChange={setRange} />
      </Flex>

      {predictions.isPending ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<FieldTimeOutlined />} description={t('machine.timeline.empty')} />
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={12}>
            <Card size="small" title={t('machine.timeline.health')}>
              <SeriesChart
                unit="%"
                series={health}
                markers={markers}
                from={window.from}
                to={window.to}
                group={GROUP}
                yMin={0}
                yMax={100}
                digits={1}
              />
            </Card>
          </Col>
          <Col xs={24} xl={12}>
            <Card size="small" title={t('machine.timeline.rulTitle', { unit })}>
              <SeriesChart unit={unit} series={rul} markers={markers} from={window.from} to={window.to} group={GROUP} digits={1} />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('machine.timeline.band')}
              </Typography.Text>
            </Card>
          </Col>
        </Row>
      )}

      <Card size="small" title={t('machine.timeline.alarms', { count: inRange.length })}>
        <List
          size="small"
          loading={alarms.isPending}
          dataSource={inRange}
          locale={{ emptyText: t('machine.timeline.noAlarms') }}
          pagination={inRange.length > 8 ? { pageSize: 8, size: 'small' } : false}
          renderItem={(a) => {
            const { color, Icon } = STATUS_PALETTE[severityLevel(a.severity)];
            return (
              <List.Item>
                <Flex gap={12} align="center" style={{ width: '100%', minWidth: 0 }}>
                  <Icon aria-hidden style={{ color }} />
                  <Typography.Text className="tabular" type="secondary" style={{ flexShrink: 0 }}>
                    {formatDateTime(a.raised_at)}
                  </Typography.Text>
                  <Tag style={{ marginInlineEnd: 0 }}>{t(`alarms.severity.${a.severity}`, { defaultValue: a.severity })}</Tag>
                  <Typography.Text ellipsis>{a.title}</Typography.Text>
                  <Typography.Text type="secondary" style={{ marginInlineStart: 'auto', flexShrink: 0 }}>
                    {t(`alarms.status.${a.status}`, { defaultValue: a.status })}
                  </Typography.Text>
                </Flex>
              </List.Item>
            );
          }}
        />
      </Card>
    </Flex>
  );
}
