import { CopyOutlined, DownloadOutlined } from '@ant-design/icons';
import { App, Button, Flex, theme } from 'antd';
import { useTranslation } from 'react-i18next';

import { downloadJson } from '../../lib/download';

export function JsonDocument({ data, filename }: { data: unknown; filename: string }) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const text = JSON.stringify(data, null, 2);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      void message.success(t('common.copied'));
    } catch {
      void message.error(t('common.copyFailed'));
    }
  };

  return (
    <Flex vertical gap={8}>
      <Flex gap={8} justify="end">
        <Button icon={<CopyOutlined />} onClick={() => void copy()}>
          {t('common.copy')}
        </Button>
        <Button icon={<DownloadOutlined />} onClick={() => downloadJson(data, filename)}>
          {t('common.download')}
        </Button>
      </Flex>
      <pre
        className="json-view"
        tabIndex={0}
        aria-label={filename}
        style={{ background: token.colorBgLayout, border: `1px solid ${token.colorBorder}` }}
      >
        {text}
      </pre>
    </Flex>
  );
}
