import type { UseQueryResult } from '@tanstack/react-query';
import { Button, Result, Skeleton } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { problemMessage } from '../../lib/problem';

interface QueryViewProps<T> {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  rows?: number;
}

export function QueryView<T>({ query, children, rows = 6 }: QueryViewProps<T>) {
  const { t } = useTranslation();
  if (query.isPending) return <Skeleton active paragraph={{ rows }} />;
  if (query.isError) {
    return (
      <Result
        status="error"
        title={t('errors.loadFailed')}
        subTitle={problemMessage(query.error, t('errors.generic'))}
        extra={
          <Button type="primary" onClick={() => void query.refetch()}>
            {t('common.retry')}
          </Button>
        }
      />
    );
  }
  return children(query.data);
}
