import { Radio, DatePicker, Space } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useCallback, useState } from 'react';

const { RangePicker } = DatePicker;

export type TimePreset = '1h' | '8h' | '24h' | '7d' | '30d' | 'custom';

interface TimeRange {
  from: string;
  to: string;
  preset: TimePreset;
}

interface TimeRangePickerProps {
  value?: TimeRange;
  onChange?: (range: TimeRange) => void;
}

const PRESETS: { key: TimePreset; label: string; hours: number }[] = [
  { key: '1h', label: '1h', hours: 1 },
  { key: '8h', label: '8h', hours: 8 },
  { key: '24h', label: '24h', hours: 24 },
  { key: '7d', label: '7d', hours: 168 },
  { key: '30d', label: '30d', hours: 720 },
];

function makeRange(hours: number, preset: TimePreset): TimeRange {
  const to = dayjs();
  const from = to.subtract(hours, 'hour');
  return { from: from.toISOString(), to: to.toISOString(), preset };
}

/**
 * Preset-based time range selector with optional custom date range.
 */
export function TimeRangePicker({ value, onChange }: TimeRangePickerProps) {
  const [preset, setPreset] = useState<TimePreset>(value?.preset ?? '1h');

  const handlePreset = useCallback(
    (key: TimePreset) => {
      setPreset(key);
      const def = PRESETS.find((p) => p.key === key);
      if (def) {
        onChange?.(makeRange(def.hours, key));
      }
    },
    [onChange],
  );

  const handleCustom = useCallback(
    (dates: [Dayjs | null, Dayjs | null] | null) => {
      if (dates && dates[0] && dates[1]) {
        setPreset('custom');
        onChange?.({
          from: dates[0].toISOString(),
          to: dates[1].toISOString(),
          preset: 'custom',
        });
      }
    },
    [onChange],
  );

  return (
    <Space size={8}>
      <Radio.Group
        size="small"
        value={preset}
        onChange={(e) => handlePreset(e.target.value as TimePreset)}
        optionType="button"
        buttonStyle="solid"
        options={PRESETS.map((p) => ({ label: p.label, value: p.key }))}
      />
      <RangePicker
        size="small"
        showTime
        format="YYYY-MM-DD HH:mm"
        value={
          preset === 'custom' && value
            ? [dayjs(value.from), dayjs(value.to)]
            : undefined
        }
        onChange={(dates) => handleCustom(dates as [Dayjs | null, Dayjs | null] | null)}
      />
    </Space>
  );
}

export function useTimeRange(initial: TimePreset = '1h') {
  const def = PRESETS.find((p) => p.key === initial) ?? PRESETS[0];
  const [range, setRange] = useState<TimeRange>(makeRange(def.hours, initial));
  return { range, setRange } as const;
}
