import { InboxOutlined } from '@ant-design/icons';
import { Flex, Typography } from 'antd';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  description: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ description, icon = <InboxOutlined />, action }: EmptyStateProps) {
  return (
    <Flex vertical align="center" justify="center" gap={16} style={{ padding: '48px 16px', textAlign: 'center' }}>
      <span aria-hidden style={{ fontSize: 40, lineHeight: 1, opacity: 0.6 }}>
        {icon}
      </span>
      <Typography.Text type="secondary" style={{ fontSize: 16 }}>
        {description}
      </Typography.Text>
      {action}
    </Flex>
  );
}
