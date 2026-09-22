import { Flex, Segmented, Select } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import type { AnalyticsScope } from '../../api/types';
import { useAssets, useLines, usePlants } from '../../hooks/useAssets';

interface ScopePickerProps {
  scope: AnalyticsScope;
  scopeId: string | undefined;
  onChange: (scope: AnalyticsScope, scopeId: string | undefined) => void;
}

/**
 * Plant / line / asset selector shared by both analytics pages.
 *
 * Changing the level clears the id rather than guessing a sibling: silently analysing a different
 * machine than the one on screen is worse than an empty picker.
 */
export function ScopePicker({ scope, scopeId, onChange }: ScopePickerProps) {
  const { t } = useTranslation();
  const { data: plants } = usePlants();
  const { data: lines } = useLines();
  const { data: assets } = useAssets({ size: 200 });

  const options =
    scope === 'asset'
      ? (assets?.items ?? []).map((a) => ({ value: a.id, label: `${a.code} — ${a.name}` }))
      : scope === 'line'
        ? (lines?.items ?? []).map((l) => ({ value: l.id, label: `${l.code} — ${l.name}` }))
        : (plants?.items ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` }));

  // Default to the first option so the page has data on first paint instead of an empty state.
  useEffect(() => {
    if (!scopeId && options.length > 0) onChange(scope, options[0].value);
  }, [scope, scopeId, options, onChange]);

  return (
    <Flex gap={8} wrap>
      <Segmented
        value={scope}
        onChange={(v) => onChange(v as AnalyticsScope, undefined)}
        options={[
          { value: 'plant', label: t('analytics.plant') },
          { value: 'line', label: t('analytics.line') },
          { value: 'asset', label: t('analytics.asset') },
        ]}
      />
      <Select
        style={{ minWidth: 240 }}
        showSearch
        optionFilterProp="label"
        value={scopeId}
        onChange={(v) => onChange(scope, v)}
        placeholder={t('analytics.pickScope')}
        options={options}
      />
    </Flex>
  );
}
