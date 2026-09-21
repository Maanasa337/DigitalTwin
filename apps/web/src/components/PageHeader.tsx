import { Flex, Typography } from 'antd';
import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  tags?: ReactNode;
  actions?: ReactNode;
  level?: 1 | 2;
}

export function PageHeader({ title, subtitle, tags, actions, level = 1 }: PageHeaderProps) {
  return (
    <Flex wrap gap={12} justify="space-between" align="center" style={{ marginBottom: 16 }}>
      <Flex vertical gap={4} style={{ minWidth: 0 }}>
        <Flex wrap gap={8} align="center">
          <Typography.Title level={level} style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
            {title}
          </Typography.Title>
          {tags}
        </Flex>
        {subtitle && <Typography.Text type="secondary">{subtitle}</Typography.Text>}
      </Flex>
      {actions && (
        <Flex wrap gap={8}>
          {actions}
        </Flex>
      )}
    </Flex>
  );
}
