import { Card, Col, Flex, Row, Statistic, Table, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useChartTokens } from '../../app/theme';
import type { AnalyticsScope, DowntimePareto } from '../../api/types';
import { KpiTile } from '../../components/KpiTile';
import { EmptyState } from '../../components/EmptyState';
import { PageHeader } from '../../components/PageHeader';
import { TimeRangePicker, useTimeRange } from '../../components/TimeRangePicker';
import {
  useDowntimePareto,
  useKpiDefinitions,
  useOee,
  useProductionPlan,
  useReliability,
} from '../../hooks/useAnalytics';
import { formatDuration } from '../../lib/format';
import { ScopePicker } from './ScopePicker';

type ParetoRow = DowntimePareto['rows'][number];

/** Production analytics (FR-PA-01..04, 06): OEE tiles and trend, Pareto, reliability, plan. */
export default function ProductionPage() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const chart = useChartTokens();
  const { range, setRange } = useTimeRange('24h');
  const [scope, setScope] = useState<AnalyticsScope>('asset');
  const [scopeId, setScopeId] = useState<string>();

  const window = { scope, id: scopeId, from: range.from, to: range.to };
  const { data: oee, isLoading } = useOee({ ...window, period: 'day' });
  const { data: pareto } = useDowntimePareto(window);
  const { data: reliability } = useReliability(window);
  const { data: plan } = useProductionPlan(window);
  const { data: definitions } = useKpiDefinitions();

  const formulaFor = (code: string) => definitions?.find((d) => d.code === code)?.formula;

  const trendOption = useMemo<EChartsOption>(() => {
    const trend = oee?.trend ?? [];
    const series = (['oee', 'availability', 'performance', 'quality'] as const).map((key) => ({
      name: t(`analytics.${key}`),
      type: 'line' as const,
      smooth: true,
      showSymbol: false,
      data: trend.map((point) => [point.time, point[key] ?? 0]),
    }));
    return {
      grid: { left: 48, right: 16, top: 36, bottom: 32 },
      legend: { top: 0, textStyle: { color: token.colorTextSecondary } },
      tooltip: { trigger: 'axis', valueFormatter: (v) => `${Number(v).toFixed(1)}%` },
      xAxis: { type: 'time', axisLabel: { color: token.colorTextSecondary } },
      yAxis: {
        type: 'value',
        max: 100,
        axisLabel: { formatter: '{value}%', color: token.colorTextSecondary },
        splitLine: { lineStyle: { color: chart.gridline } },
      },
      series,
    };
  }, [oee, token, chart, t]);

  const paretoOption = useMemo<EChartsOption>(() => {
    const rows = pareto?.rows ?? [];
    return {
      grid: { left: 56, right: 56, top: 24, bottom: 56 },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: rows.map((r) => r.cause_code),
        axisLabel: { rotate: 30, color: token.colorTextSecondary },
      },
      yAxis: [
        {
          type: 'value',
          name: 'hours',
          axisLabel: { color: token.colorTextSecondary },
          splitLine: { lineStyle: { color: chart.gridline } },
        },
        { type: 'value', max: 100, axisLabel: { formatter: '{value}%' }, splitLine: { show: false } },
      ],
      series: [
        {
          type: 'bar',
          name: t('analytics.downtime'),
          data: rows.map((r) => +(r.seconds / 3600).toFixed(2)),
          itemStyle: { color: token.colorError },
        },
        {
          type: 'line',
          name: t('analytics.cumulative'),
          yAxisIndex: 1,
          data: rows.map((r) => +(r.cumulative_share * 100).toFixed(1)),
          itemStyle: { color: token.colorWarning },
        },
      ],
    };
  }, [pareto, token, chart, t]);

  const paretoColumns: ColumnsType<ParetoRow> = [
    { title: t('analytics.cause'), dataIndex: 'cause_code' },
    {
      title: t('analytics.downtime'),
      dataIndex: 'seconds',
      width: 130,
      align: 'right',
      render: (v: number) => formatDuration(v),
    },
    {
      title: t('analytics.share'),
      dataIndex: 'share',
      width: 100,
      align: 'right',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
  ];

  return (
    <>
      <PageHeader
        title={t('analytics.productionTitle')}
        subtitle={t('analytics.productionSubtitle')}
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
          </>
        }
      />

      {!scopeId ? (
        <EmptyState description={t('analytics.pickScopePrompt')} />
      ) : (
        <Flex vertical gap={16}>
          <Row gutter={[12, 12]}>
            <Col xs={12} md={6}>
              <KpiTile
                title="OEE"
                value={oee?.oee}
                unit="%"
                digits={1}
                formula={formulaFor('oee')}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.availability')}
                value={oee?.availability}
                unit="%"
                digits={1}
                formula={formulaFor('availability')}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.performance')}
                value={oee?.performance}
                unit="%"
                digits={1}
                formula={formulaFor('performance')}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('analytics.quality')}
                value={oee?.quality}
                unit="%"
                digits={1}
                formula={formulaFor('quality')}
              />
            </Col>
          </Row>

          <Card size="small" title={t('analytics.oeeTrend')} loading={isLoading}>
            <ReactECharts option={trendOption} style={{ height: 300 }} notMerge />
          </Card>

          <Row gutter={[12, 12]}>
            <Col xs={24} lg={14}>
              <Card size="small" title={t('analytics.downtimePareto')}>
                {pareto && pareto.rows.length > 0 ? (
                  <>
                    <ReactECharts option={paretoOption} style={{ height: 280 }} notMerge />
                    <Table<ParetoRow>
                      rowKey="cause_code"
                      size="small"
                      pagination={false}
                      columns={paretoColumns}
                      dataSource={pareto.rows}
                      style={{ marginTop: 12 }}
                    />
                  </>
                ) : (
                  <EmptyState description={t('analytics.noDowntime')} />
                )}
              </Card>
            </Col>

            <Col xs={24} lg={10}>
              <Flex vertical gap={12}>
                <Card size="small" title={t('analytics.reliability')}>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Statistic
                        title="MTBF"
                        value={reliability?.mtbf_h ?? 0}
                        precision={1}
                        suffix="h"
                        valueStyle={{ fontSize: 22 }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title="MTTR"
                        value={reliability?.mttr_h ?? 0}
                        precision={1}
                        suffix="h"
                        valueStyle={{ fontSize: 22 }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title={t('analytics.breakdowns')}
                        value={reliability?.breakdowns ?? 0}
                        valueStyle={{ fontSize: 18 }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title={t('analytics.repairs')}
                        value={reliability?.repairs ?? 0}
                        valueStyle={{ fontSize: 18 }}
                      />
                    </Col>
                  </Row>
                </Card>

                <Card size="small" title={t('analytics.productionVsPlan')}>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Statistic
                        title={t('analytics.actual')}
                        value={plan?.actual ?? 0}
                        valueStyle={{ fontSize: 22 }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title={t('analytics.planned')}
                        value={plan?.planned ?? 0}
                        valueStyle={{ fontSize: 22 }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title={t('analytics.attainment')}
                        value={plan?.attainment ?? 0}
                        precision={1}
                        suffix="%"
                        valueStyle={{ fontSize: 18 }}
                      />
                    </Col>
                    <Col span={12}>
                      <Statistic
                        title={t('analytics.rejects')}
                        value={plan?.reject ?? 0}
                        valueStyle={{ fontSize: 18, color: token.colorError }}
                      />
                    </Col>
                  </Row>
                </Card>
              </Flex>
            </Col>
          </Row>

          {plan && plan.cycle_time_histogram.length > 0 && (
            <Card size="small" title={t('analytics.cycleTime')}>
              <ReactECharts
                option={{
                  grid: { left: 48, right: 16, top: 16, bottom: 40 },
                  tooltip: { trigger: 'axis' },
                  xAxis: {
                    type: 'category',
                    data: plan.cycle_time_histogram.map((b) => `${b.from.toFixed(1)}s`),
                    axisLabel: { color: token.colorTextSecondary },
                  },
                  yAxis: {
                    type: 'value',
                    axisLabel: { color: token.colorTextSecondary },
                    splitLine: { lineStyle: { color: chart.gridline } },
                  },
                  series: [
                    {
                      type: 'bar',
                      data: plan.cycle_time_histogram.map((b) => b.count),
                      itemStyle: { color: token.colorPrimary },
                    },
                  ],
                }}
                style={{ height: 220 }}
                notMerge
              />
              <span style={{ fontSize: 12, color: token.colorTextTertiary }}>
                {dayjs(range.from).format('DD MMM HH:mm')} – {dayjs(range.to).format('DD MMM HH:mm')}
              </span>
            </Card>
          )}
        </Flex>
      )}
    </>
  );
}
