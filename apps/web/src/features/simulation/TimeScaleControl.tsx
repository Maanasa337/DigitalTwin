import { Slider, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useApiError } from '../../hooks/useApiError';
import { useSetTimeScale } from '../../hooks/useSimulation';

const MARKS = [1, 10, 60, 100, 1000];

function toFactor(position: number): number {
  return Math.min(1000, Math.max(1, Math.round(10 ** position)));
}

export function TimeScaleControl({ timeScale }: { timeScale: number }) {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState<number | null>(null);
  const setScale = useSetTimeScale();
  const onError = useApiError();
  const position = dragging ?? Math.log10(Math.min(1000, Math.max(1, timeScale)));

  const apply = (value: number) =>
    setScale.mutate(toFactor(value), { onError, onSettled: () => setDragging(null) });

  return (
    <>
      <Typography.Text type="secondary">{t('sim.timeScale.help')}</Typography.Text>
      <Slider
        min={0}
        max={3}
        step={0.01}
        value={position}
        disabled={setScale.isPending}
        marks={Object.fromEntries(MARKS.map((m) => [Math.log10(m), `${m}×`]))}
        tooltip={{ formatter: (value) => `${toFactor(value ?? 0)}×` }}
        onChange={setDragging}
        onChangeComplete={apply}
        aria-label={t('sim.timeScale.title')}
        style={{ marginInline: 16, marginBlock: 24 }}
      />
    </>
  );
}
