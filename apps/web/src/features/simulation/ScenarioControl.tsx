import { PlayCircleOutlined } from '@ant-design/icons';
import { App, Button, Flex, Popconfirm, Select, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useApiError } from '../../hooks/useApiError';
import { useScenarios, useStartScenario } from '../../hooks/useSimulation';

export function ScenarioControl({ current }: { current: string | null }) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const scenarios = useScenarios();
  const start = useStartScenario();
  const onError = useApiError();
  const [selected, setSelected] = useState<string | null>(null);
  const code = selected ?? current;
  const description = scenarios.data?.find((s) => s.code === code)?.description;

  const run = () =>
    code &&
    start.mutateAsync(code).then(
      (res) => void message.success(t('sim.scenario.started', { code: res.scenario_code, seed: res.seed ?? '—' })),
      onError,
    );

  return (
    <Flex vertical gap={12}>
      <Flex gap={8} wrap>
        <Select<string>
          style={{ flex: 1, minWidth: 220 }}
          value={code ?? undefined}
          onChange={setSelected}
          loading={scenarios.isPending}
          status={scenarios.isError ? 'error' : undefined}
          placeholder={scenarios.isError ? t('errors.loadFailed') : t('sim.scenario.placeholder')}
          aria-label={t('sim.scenario.title')}
          options={scenarios.data?.map((s) => ({ value: s.code, label: `${s.name} (${s.code})` }))}
        />
        <Popconfirm
          title={t('sim.scenario.confirmTitle', { code })}
          description={t('sim.scenario.confirmDescription')}
          okText={t('sim.scenario.start')}
          cancelText={t('common.cancel')}
          onConfirm={run}
          disabled={!code}
        >
          <Button type="primary" icon={<PlayCircleOutlined />} disabled={!code} loading={start.isPending}>
            {t('sim.scenario.start')}
          </Button>
        </Popconfirm>
      </Flex>
      {description && <Typography.Text type="secondary">{description}</Typography.Text>}
    </Flex>
  );
}
