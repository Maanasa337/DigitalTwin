import { App } from 'antd';
import { useTranslation } from 'react-i18next';

import { problemMessage } from '../lib/problem';

export function useApiError() {
  const { message } = App.useApp();
  const { t } = useTranslation();
  return (err: unknown) => {
    void message.error(problemMessage(err, t('errors.generic')));
  };
}
