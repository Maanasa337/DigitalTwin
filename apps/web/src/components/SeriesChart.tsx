import { theme } from 'antd';
import type { EChartsOption } from 'echarts';
import * as echarts from 'echarts';
import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';

import { useChartTokens } from '../app/theme';
import { formatNumber } from '../lib/format';

export interface ChartSeries {
  name: string;
  color: string;
  data: [string, number | null][];
  /** Lower/upper bound per point, drawn as a translucent band behind the line. */
  band?: [string, number | null, number | null][];
  step?: boolean;
}

export interface ChartMarker {
  /** A horizontal reference (a threshold) or a vertical one (an event in time). */
  axis: 'x' | 'y';
  value: number | string;
  label: string;
  color: string;
}

interface SeriesChartProps {
  unit: string;
  series: ChartSeries[];
  from: string;
  to: string;
  markers?: ChartMarker[];
  /** Charts sharing a group share the crosshair, so stacked small multiples read as one. */
  group?: string;
  height?: number;
  yMin?: number;
  yMax?: number;
  digits?: number;
}

/**
 * One measure on one y-axis over a fixed time window. Different units are separate stacked charts
 * that share the window and the crosshair, never a second y-axis.
 */
export function SeriesChart({
  unit,
  series,
  from,
  to,
  markers = [],
  group,
  height = 220,
  yMin,
  yMax,
  digits = 2,
}: SeriesChartProps) {
  const { token } = theme.useToken();
  const chart = useChartTokens();

  const option = useMemo<EChartsOption>(() => {
    const text = { color: token.colorTextSecondary, fontSize: 12 };
    const horizontal = markers.filter((m) => m.axis === 'y');
    const vertical = markers.filter((m) => m.axis === 'x');
    const bands = series.flatMap((s) =>
      s.band
        ? [
            // Stacked pair: an invisible lower edge, then the band's height on top of it.
            {
              name: `${s.name}__low`,
              type: 'line' as const,
              stack: `band-${s.name}`,
              data: s.band.map(([t, low]) => [t, low]),
              lineStyle: { opacity: 0 },
              showSymbol: false,
              silent: true,
              tooltip: { show: false },
            },
            {
              name: `${s.name}__band`,
              type: 'line' as const,
              stack: `band-${s.name}`,
              data: s.band.map(([t, low, high]) => [t, low != null && high != null ? high - low : null]),
              lineStyle: { opacity: 0 },
              areaStyle: { color: s.color, opacity: 0.16 },
              showSymbol: false,
              silent: true,
              tooltip: { show: false },
            },
          ]
        : [],
    );
    return {
      animation: false,
      grid: { left: 56, right: 20, top: series.length > 1 ? 32 : 16, bottom: 28 },
      legend:
        series.length > 1
          ? { top: 0, left: 0, textStyle: text, icon: 'roundRect', data: series.map((s) => s.name) }
          : undefined,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: chart.axis } },
        valueFormatter: (v) => (typeof v === 'number' ? `${formatNumber(v, digits)} ${unit}`.trim() : '—'),
      },
      xAxis: {
        type: 'time',
        min: from,
        max: to,
        axisLabel: text,
        axisLine: { lineStyle: { color: chart.gridline } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        name: unit,
        nameTextStyle: text,
        scale: yMin == null,
        min: yMin,
        max: yMax,
        axisLabel: text,
        splitLine: { lineStyle: { color: chart.gridline } },
      },
      series: [
        ...bands,
        ...series.map((s, index) => ({
          name: s.name,
          type: 'line' as const,
          data: s.data,
          step: s.step ? ('end' as const) : undefined,
          showSymbol: false,
          symbolSize: 8,
          lineStyle: { width: 2, color: s.color },
          itemStyle: { color: s.color },
          connectNulls: false,
          markLine:
            index === 0 && (horizontal.length || vertical.length)
              ? {
                  symbol: 'none',
                  silent: false,
                  data: [
                    ...horizontal.map((m) => ({
                      yAxis: m.value as number,
                      name: m.label,
                      lineStyle: { color: m.color, type: 'dashed' as const, width: 1 },
                      label: { formatter: m.label, color: token.colorTextSecondary, position: 'insideEndTop' as const },
                    })),
                    ...vertical.map((m) => ({
                      xAxis: m.value,
                      name: m.label,
                      lineStyle: { color: m.color, type: 'solid' as const, width: 1, opacity: 0.7 },
                      label: { show: false },
                      emphasis: { label: { show: true, formatter: m.label, color: token.colorText } },
                    })),
                  ],
                }
              : undefined,
        })),
      ],
    };
  }, [series, markers, from, to, unit, token, chart, yMin, yMax, digits]);

  return (
    <ReactECharts
      option={option}
      notMerge
      style={{ height }}
      onChartReady={(instance: echarts.ECharts) => {
        if (!group) return;
        instance.group = group;
        echarts.connect(group);
      }}
    />
  );
}
