import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons';
import { Flex, Tooltip, Typography, theme } from 'antd';

import type { Attribution } from '../../api/types';
import { formatNumber } from '../../lib/format';

interface AttributionWaterfallProps {
  attributions: Attribution[];
  topK?: number;
}

/**
 * Horizontal waterfall of the top attributions.
 *
 * Bars are scaled against the largest contribution rather than the total, so the second driver
 * still reads as substantial when one feature dominates.
 */
export function AttributionWaterfall({ attributions, topK = 8 }: AttributionWaterfallProps) {
  const { token } = theme.useToken();
  const rows = attributions.slice(0, topK);
  const max = Math.max(...rows.map((a) => Math.abs(a.contribution)), Number.EPSILON);

  if (rows.length === 0) {
    return <Typography.Text type="secondary">No attributions recorded.</Typography.Text>;
  }

  return (
    <Flex vertical gap={8}>
      {rows.map((a) => {
        const raising = a.direction === 'raising';
        const color = raising ? token.colorError : token.colorSuccess;
        return (
          <Flex key={a.feature} align="center" gap={8}>
            <Tooltip title={a.feature}>
              <Typography.Text
                style={{ width: 150, flexShrink: 0, fontSize: 13 }}
                ellipsis
              >
                {a.label}
              </Typography.Text>
            </Tooltip>

            <Typography.Text
              type="secondary"
              style={{ width: 84, flexShrink: 0, fontSize: 12, textAlign: 'right' }}
            >
              {formatNumber(a.value, 2)}
              {a.unit ? ` ${a.unit}` : ''}
            </Typography.Text>

            <div
              style={{
                flex: 1,
                height: 16,
                background: token.colorFillQuaternary,
                borderRadius: 3,
                overflow: 'hidden',
                minWidth: 60,
              }}
            >
              <div
                style={{
                  width: `${(Math.abs(a.contribution) / max) * 100}%`,
                  height: '100%',
                  background: color,
                  borderRadius: 3,
                  transition: 'width 240ms ease',
                }}
              />
            </div>

            <Flex align="center" gap={4} style={{ width: 74, flexShrink: 0, color }}>
              <span aria-hidden style={{ fontSize: 11 }}>
                {raising ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              </span>
              <Typography.Text style={{ fontSize: 12, color, fontVariantNumeric: 'tabular-nums' }}>
                {(a.share * 100).toFixed(0)}%
              </Typography.Text>
            </Flex>
          </Flex>
        );
      })}
    </Flex>
  );
}
