import { theme } from 'antd';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';

import type { ScheduleItem } from '../../api/types';

export interface GanttRow {
  id: string;
  label: string;
}

interface GanttChartProps {
  items: ScheduleItem[];
  rows: GanttRow[];
  labelFor: (item: ScheduleItem) => string;
  horizonStart: string;
  horizonEnd: string;
  onSelect?: (item: ScheduleItem) => void;
}

const BAR_HEIGHT = 0.6;

/**
 * Schedule Gantt (FR-MS-03): one row per technician, bars coloured by failure risk.
 *
 * Drawn with an ECharts custom series rather than a chart type: no built-in series can place an
 * arbitrary time interval on a categorical row and still share the time axis with a risk overlay.
 */
export function GanttChart({
  items,
  rows,
  labelFor,
  horizonStart,
  horizonEnd,
  onSelect,
}: GanttChartProps) {
  const { token } = theme.useToken();

  const option = useMemo<EChartsOption>(() => {
    const rowIndex = new Map(rows.map((row, index) => [row.id, index]));

    const data = items.map((item) => ({
      value: [
        rowIndex.get(item.technician_id ?? 'unassigned') ?? rows.length - 1,
        new Date(item.starts_at).getTime(),
        new Date(item.ends_at).getTime(),
        labelFor(item),
        item.risk_before ?? 0,
        item.manually_adjusted ? 1 : 0,
      ],
      itemId: item.id,
    }));

    return {
      grid: { left: 140, right: 24, top: 24, bottom: 48 },
      tooltip: {
        formatter: (params: { value: (string | number)[] }) => {
          const [, start, end, label, risk, adjusted] = params.value;
          const from = new Date(Number(start)).toLocaleString();
          const to = new Date(Number(end)).toLocaleTimeString();
          return [
            `<strong>${label}</strong>`,
            `${from} → ${to}`,
            `Risk before slot: ${(Number(risk) * 100).toFixed(1)}%`,
            Number(adjusted) ? '<em>Manually adjusted</em>' : '',
          ]
            .filter(Boolean)
            .join('<br/>');
        },
      },
      xAxis: {
        type: 'time',
        min: new Date(horizonStart).getTime(),
        max: new Date(horizonEnd).getTime(),
        axisLabel: { color: token.colorTextSecondary },
        splitLine: { lineStyle: { color: token.colorBorderSecondary } },
      },
      yAxis: {
        type: 'category',
        data: rows.map((row) => row.label),
        axisLabel: { color: token.colorTextSecondary },
        axisTick: { show: false },
      },
      dataZoom: [{ type: 'slider', height: 18, bottom: 8 }, { type: 'inside' }],
      series: [
        {
          type: 'custom',
          renderItem: (_params, api) => {
            const rowValue = api.value(0) as number;
            const start = api.coord([api.value(1), rowValue]);
            const end = api.coord([api.value(2), rowValue]);
            const height = (api.size?.([0, 1]) as number[])[1] * BAR_HEIGHT;
            const risk = api.value(4) as number;
            const adjusted = (api.value(5) as number) === 1;

            const rect = {
              x: start[0],
              y: start[1] - height / 2,
              width: Math.max(end[0] - start[0], 2),
              height,
            };
            return {
              type: 'rect',
              shape: rect,
              style: {
                fill: risk >= 0.5 ? token.colorError : risk >= 0.2 ? token.colorWarning : token.colorPrimary,
                // A dashed outline marks a bar a planner moved by hand, so it is not mistaken
                // for something the solver chose.
                stroke: adjusted ? token.colorText : 'transparent',
                lineDash: adjusted ? [4, 3] : undefined,
                lineWidth: adjusted ? 1.5 : 0,
                opacity: 0.9,
              },
            };
          },
          encode: { x: [1, 2], y: 0 },
          data,
        },
      ],
    } as EChartsOption;
  }, [items, rows, labelFor, horizonStart, horizonEnd, token]);

  return (
    <ReactECharts
      option={option}
      style={{ height: Math.max(240, rows.length * 44 + 90) }}
      notMerge
      onEvents={
        onSelect
          ? {
              click: (params: { dataIndex?: number }) => {
                const item = params.dataIndex != null ? items[params.dataIndex] : undefined;
                if (item) onSelect(item);
              },
            }
          : undefined
      }
    />
  );
}
