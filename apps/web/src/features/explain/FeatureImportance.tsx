import { BarChartOutlined } from '@ant-design/icons';
import { Col, Flex, Progress, Row, Typography, theme } from 'antd';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { useChartTokens } from '../../app/theme';
import { EmptyState } from '../../components/EmptyState';
import { useGlobalImportance } from '../../hooks/useXai';
import { formatNumber } from '../../lib/format';

const TOP_FEATURES = 10;

/** Mean |SHAP| per feature over the model's background sample, top ten (FR-XAI-02). */
export function FeatureImportance({ modelId }: { modelId: string }) {
  const { t } = useTranslation();
  const importance = useGlobalImportance(modelId);
  if (importance.isPending) return <Typography.Text type="secondary">{t('common.loading')}</Typography.Text>;
  const features = [...(importance.data?.features ?? [])].sort((a, b) => b.importance - a.importance).slice(0, TOP_FEATURES);
  if (importance.isError || features.length === 0)
    return <EmptyState icon={<BarChartOutlined />} description={t('models.noImportance')} />;
  const max = features[0].importance || 1;
  return (
    <Flex vertical gap={6}>
      {features.map((f) => (
        <Flex key={f.feature} align="center" gap={8}>
          <Typography.Text ellipsis style={{ width: '45%' }} title={f.feature}>
            {f.feature}
          </Typography.Text>
          <Progress
            percent={(f.importance / max) * 100}
            showInfo={false}
            size="small"
            style={{ flex: 1, margin: 0 }}
            aria-label={`${f.feature}: ${f.importance.toFixed(4)}`}
          />
          <Typography.Text className="tabular" type="secondary" style={{ width: 64, textAlign: 'right' }}>
            {f.importance.toFixed(3)}
          </Typography.Text>
        </Flex>
      ))}
    </Flex>
  );
}

/**
 * Partial dependence of the top features: the model's average output as one feature sweeps its
 * observed range with the others held at their sampled values. One small chart per feature, since
 * each has its own scale.
 */
export function PartialDependence({ modelId, outputLabel }: { modelId: string; outputLabel: string }) {
  const { t } = useTranslation();
  const importance = useGlobalImportance(modelId);
  const curves = Object.entries(importance.data?.partial_dependence ?? {});
  if (!curves.length) return <EmptyState icon={<BarChartOutlined />} description={t('explainQuality.noPdp')} />;
  return (
    <Row gutter={[16, 16]}>
      {curves.map(([feature, points]) => (
        <Col key={feature} xs={24} md={8}>
          <Typography.Text strong ellipsis title={feature}>
            {feature}
          </Typography.Text>
          <PdpChart points={points} outputLabel={outputLabel} />
        </Col>
      ))}
    </Row>
  );
}

function PdpChart({ points, outputLabel }: { points: [number, number][]; outputLabel: string }) {
  const { token } = theme.useToken();
  const chart = useChartTokens();
  const option = useMemo<EChartsOption>(() => {
    const text = { color: token.colorTextSecondary, fontSize: 12 };
    return {
      animation: false,
      grid: { left: 48, right: 12, top: 12, bottom: 28 },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (v) => (typeof v === 'number' ? formatNumber(v, 2) : '—'),
      },
      xAxis: {
        type: 'value',
        scale: true,
        axisLabel: { ...text, formatter: (v: number) => formatNumber(v, 1) },
        splitLine: { show: false },
      },
      yAxis: { type: 'value', scale: true, axisLabel: text, splitLine: { lineStyle: { color: chart.gridline } } },
      series: [
        {
          name: outputLabel,
          type: 'line',
          data: points,
          showSymbol: false,
          lineStyle: { width: 2, color: chart.series[0] },
          itemStyle: { color: chart.series[0] },
        },
      ],
    };
  }, [points, outputLabel, token, chart]);
  return <ReactECharts option={option} notMerge style={{ height: 160 }} />;
}
