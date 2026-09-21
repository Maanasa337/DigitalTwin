import { ArrowRightOutlined } from '@ant-design/icons';
import { Alert, Flex, Table, Tag, Typography, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { Counterfactual, CounterfactualChange } from '../../api/types';
import { formatNumber } from '../../lib/format';

/**
 * "What would make this healthy" — the smallest actionable change the search found.
 *
 * Only the best (most feasible) counterfactual is shown: presenting several competing plans invites
 * an operator to pick the one they like rather than the one that costs least to apply.
 */
export function CounterfactualTable({ counterfactuals }: { counterfactuals: Counterfactual[] }) {
  const { token } = theme.useToken();
  const best = counterfactuals[0];

  if (!best) {
    return (
      <Typography.Text type="secondary">
        No actionable change was found that reaches a healthy state.
      </Typography.Text>
    );
  }

  const columns: ColumnsType<CounterfactualChange> = [
    { title: 'Setting', dataIndex: 'label', key: 'label' },
    {
      title: 'Now',
      dataIndex: 'from',
      key: 'from',
      width: 110,
      align: 'right',
      render: (v: number, r) => `${formatNumber(v, 2)}${r.unit ? ` ${r.unit}` : ''}`,
    },
    {
      title: '',
      key: 'arrow',
      width: 32,
      align: 'center',
      render: () => <ArrowRightOutlined style={{ color: token.colorTextTertiary }} />,
    },
    {
      title: 'Target',
      dataIndex: 'to',
      key: 'to',
      width: 110,
      align: 'right',
      render: (v: number, r) => (
        <Typography.Text strong style={{ color: token.colorSuccess }}>
          {formatNumber(v, 2)}
          {r.unit ? ` ${r.unit}` : ''}
        </Typography.Text>
      ),
    },
  ];

  const outcome = Object.entries(best.outcome)[0];

  return (
    <Flex vertical gap={10}>
      <Flex wrap gap={8} align="center">
        <Tag color="blue" style={{ marginInlineEnd: 0 }}>
          Target: {best.target}
        </Tag>
        {best.feasibility_score != null && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Feasibility {(best.feasibility_score * 100).toFixed(0)}%
          </Typography.Text>
        )}
      </Flex>

      <Table<CounterfactualChange>
        rowKey="feature"
        size="small"
        pagination={false}
        columns={columns}
        dataSource={best.changes}
      />

      {best.action_text && (
        <Alert
          type="info"
          showIcon
          message={best.action_text}
          description={
            outcome
              ? `Expected ${outcome[0].replace(/_/g, ' ')}: ${formatNumber(outcome[1], 0)}`
              : undefined
          }
        />
      )}
    </Flex>
  );
}
