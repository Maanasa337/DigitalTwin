import { LineChartOutlined } from '@ant-design/icons';
import { App, Button, Card, Col, Empty, Flex, Row, Table, Tag, Tooltip, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AnalyticsScope, EnergyAnomaly } from '../../api/types';
import { KpiTile } from '../../components/KpiTile';
import { PageHeader } from '../../components/PageHeader';
import { TimeRangePicker, useTimeRange } from '../../components/TimeRangePicker';
import {
  useCreateEnergyBaseline,
  useEnergyAnomalies,
  useEnergySummary,
} from '../../hooks/useAnalytics';
import { useApiError } from '../../hooks/useApiError';
import { formatDateTime, formatNumber } from '../../lib/format';
import { ScopePicker } from './ScopePicker';

/** Energy analytics (FR-EN-01..03): cost, CO2, intensity against baseline, and anomalies. */
export default function EnergyPage() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { message } = App.useApp();
  const onError = useApiError();
  const { range, setRange } = useTimeRange('24h');
  const [scope, setScope] = useState<AnalyticsScope>('asset');
  const [scopeId, setScopeId] = useState<string>();

  const window = { scope, id: scopeId, from: range.from, to: range.to };
  const { data: summary, isLoading } = useEnergySummary(window);
  const { data: anomalies } = useEnergyAnomalies(window);
  const createBaseline = useCreateEnergyBaseline();

  const hasBaseline = (summary?.intensity_trend ?? []).some((p) => p.expected_kwh != null);

  const refitBaseline = () => {
    if (!scopeId) return;
    createBaseline.mutate(
      {
        scope,
        scope_id: scopeId,
        period_start: dayjs().subtract(30, 'day').toISOString(),
        period_end: dayjs().toISOString(),
      },
      {
        onSuccess: (baseline) =>
          void message.success(
            t('analytics.baselineFitted', 'Baseline refitted (R² {{r2}})', {
              r2: baseline.r2?.toFixed(3) ?? 'n/a',
            }),
          ),
        onError,
      },
    );
  };

  const intensityOption = useMemo<EChartsOption>(() => {
    const trend = summary?.intensity_trend ?? [];
    return {
      grid: { left: 56, right: 16, top: 36, bottom: 40 },
      legend: { top: 0, textStyle: { color: token.colorTextSecondary } },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'time', axisLabel: { color: token.colorTextSecondary } },
      yAxis: {
        type: 'value',
        name: 'kWh',
        axisLabel: { color: token.colorTextSecondary },
        splitLine: { lineStyle: { color: token.colorBorderSecondary } },
      },
      series: [
        {
          name: t('analytics.actualEnergy', 'Actual'),
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: trend.map((p) => [p.time, p.energy_kwh]),
          itemStyle: { color: token.colorPrimary },
        },
        {
          name: t('analytics.expectedEnergy', 'Baseline expectation'),
          type: 'line',
          smooth: true,
          showSymbol: false,
          lineStyle: { type: 'dashed' },
          data: trend.map((p) => [p.time, p.expected_kwh]),
          itemStyle: { color: token.colorTextTertiary },
        },
      ],
    };
  }, [summary, token, t]);

  const topConsumersOption = useMemo<EChartsOption>(() => {
    const rows = [...(summary?.breakdown ?? [])].reverse();
    return {
      grid: { left: 110, right: 24, top: 16, bottom: 32 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'value',
        axisLabel: { color: token.colorTextSecondary },
        splitLine: { lineStyle: { color: token.colorBorderSecondary } },
      },
      yAxis: {
        type: 'category',
        data: rows.map((r) => r.asset_code),
        axisLabel: { color: token.colorTextSecondary },
      },
      series: [
        {
          type: 'bar',
          data: rows.map((r) => +r.energy_kwh.toFixed(2)),
          itemStyle: { color: token.colorPrimary },
        },
      ],
    };
  }, [summary, token]);

  const anomalyColumns: ColumnsType<EnergyAnomaly> = [
    { title: t('common.time', 'Time'), dataIndex: 'time', width: 180, render: (v: string) => formatDateTime(v) },
    {
      title: t('analytics.actualEnergy', 'Actual'),
      dataIndex: 'energy_kwh',
      width: 110,
      align: 'right',
      render: (v: number) => `${formatNumber(v, 2)} kWh`,
    },
    {
      title: t('analytics.expectedEnergy', 'Expected'),
      dataIndex: 'expected_kwh',
      width: 110,
      align: 'right',
      render: (v: number) => `${formatNumber(v, 2)} kWh`,
    },
    {
      title: t('analytics.units', 'Units'),
      dataIndex: 'units',
      width: 90,
      align: 'right',
      render: (v: number) => formatNumber(v, 0),
    },
    {
      title: t('analytics.deviation', 'Deviation'),
      dataIndex: 'sigma',
      width: 110,
      align: 'right',
      render: (v: number) => (
        <Tag color={v >= 5 ? 'red' : 'orange'} style={{ marginInlineEnd: 0 }}>
          {v.toFixed(1)}σ
        </Tag>
      ),
    },
    {
      title: t('analytics.health', 'Health'),
      dataIndex: 'health_index',
      width: 100,
      align: 'right',
      render: (v: number | null) =>
        v == null ? (
          '—'
        ) : (
          <Tooltip title={t('analytics.healthHint', 'Asset health at the time of the anomaly')}>
            <span>{v.toFixed(0)}</span>
          </Tooltip>
        ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title={t('analytics.energyTitle', 'Energy analytics')}
        subtitle={t(
          'analytics.energySubtitle',
          'Consumption measured against what this output should have cost, not against last week.',
        )}
        actions={
          <>
            <ScopePicker
              scope={scope}
              scopeId={scopeId}
              onChange={(nextScope, nextId) => {
                setScope(nextScope);
                setScopeId(nextId);
              }}
            />
            <TimeRangePicker value={range} onChange={setRange} />
            <Button
              icon={<LineChartOutlined />}
              loading={createBaseline.isPending}
              disabled={!scopeId}
              onClick={refitBaseline}
            >
              {t('analytics.refitBaseline', 'Refit baseline')}
            </Button>
          </>
        }
      />

      {!scopeId ? (
        <Empty description={t('analytics.pickScopePrompt', 'Select a plant, line or asset.')} />
      ) : (
        <Flex vertical gap={16}>
          <Row gutter={[12, 12]}>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.energy', 'Energy')}
                value={summary?.energy_kwh}
                unit="kWh"
                digits={1}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.cost', 'Cost')}
                value={summary?.cost}
                unit={summary?.currency}
                digits={0}
                formula="Sum of energy x the tariff rate in force at each reading"
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title="CO2"
                value={summary?.co2_kg}
                unit="kg"
                digits={1}
                formula="Energy x the plant's grid emission factor"
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.peakDemand', 'Peak demand')}
                value={summary?.peak_demand_kw}
                unit="kW"
                digits={1}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.energyPerUnit', 'Energy per unit')}
                value={summary?.energy_per_unit}
                unit="kWh/unit"
                digits={3}
                formula="Total energy / good count"
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.idleShare', 'Idle energy share')}
                value={summary?.idle_energy_share}
                unit="%"
                digits={1}
                formula="Energy drawn while IDLE or DOWN / total energy"
              />
            </Col>
          </Row>

          <Card
            size="small"
            title={t('analytics.intensity', 'Consumption vs baseline')}
            loading={isLoading}
            extra={
              !hasBaseline ? (
                <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                  {t('analytics.noBaseline', 'No baseline fitted')}
                </Tag>
              ) : null
            }
          >
            {(summary?.intensity_trend ?? []).length > 0 ? (
              <ReactECharts option={intensityOption} style={{ height: 300 }} notMerge />
            ) : (
              <Empty description={t('analytics.noEnergy', 'No energy readings in this window.')} />
            )}
          </Card>

          <Row gutter={[12, 12]}>
            <Col xs={24} lg={10}>
              <Card size="small" title={t('analytics.topConsumers', 'Top consumers')}>
                {(summary?.breakdown ?? []).length > 0 ? (
                  <ReactECharts option={topConsumersOption} style={{ height: 240 }} notMerge />
                ) : (
                  <Empty description={t('analytics.noEnergy', 'No energy readings in this window.')} />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={14}>
              <Card
                size="small"
                title={
                  <Flex gap={8} align="center">
                    <span>{t('analytics.anomalies', 'Energy anomalies')}</span>
                    {(anomalies?.length ?? 0) > 0 && (
                      <Tag color="error" style={{ marginInlineEnd: 0 }}>
                        {anomalies!.length}
                      </Tag>
                    )}
                  </Flex>
                }
              >
                <Table<EnergyAnomaly>
                  rowKey={(r) => r.time}
                  size="small"
                  columns={anomalyColumns}
                  dataSource={anomalies ?? []}
                  pagination={{ pageSize: 8, showSizeChanger: false }}
                  locale={{
                    emptyText: hasBaseline
                      ? t('analytics.noAnomalies', 'Consumption is within 3σ of the baseline.')
                      : t(
                          'analytics.baselineNeeded',
                          'Fit a baseline first — anomalies are measured against expected consumption.',
                        ),
                  }}
                />
              </Card>
            </Col>
          </Row>
        </Flex>
      )}
    </div>
  );
}
