import { Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';

/**
 * The risk tier of an intent, always shown next to the assistant's answer.
 *
 * Colour is never the only signal: each tier carries its own label, so the badge still reads on a
 * monochrome screen and to a screen reader (NFR-A11Y).
 */
const TIER_COLOUR: Record<string, string> = {
  T0: 'default',
  T1: 'blue',
  T2: 'gold',
  T3: 'red',
};

export function TierBadge({ tier }: { tier: string }) {
  const { t } = useTranslation();
  const label = t(`voice.tier.${tier}`, { defaultValue: tier });
  return (
    <Tooltip title={t(`voice.tierHint.${tier}`, { defaultValue: '' })}>
      <Tag color={TIER_COLOUR[tier] ?? 'default'} style={{ marginInlineEnd: 0 }}>
        {tier} · {label}
      </Tag>
    </Tooltip>
  );
}
