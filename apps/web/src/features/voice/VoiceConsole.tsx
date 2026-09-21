import { MessageOutlined } from '@ant-design/icons';
import { Button, Drawer, FloatButton, Grid, Space, Tooltip } from 'antd';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useVoiceStore } from '../../store/voiceStore';
import { ChatPanel } from './ChatPanel';

/**
 * The always-present assistant (§9.1: "voice is a first-class input, not an add-on").
 *
 * Push-to-talk is not wired: the speech service is a later module. What is here is the whole
 * command path a microphone would feed — router, tiers, read-back — driven by typed text, so the
 * button opens a console that already works rather than a placeholder.
 */
export function VoiceConsole() {
  const { t } = useTranslation();
  const screens = Grid.useBreakpoint();
  const open = useVoiceStore((s) => s.open);
  const setOpen = useVoiceStore((s) => s.setOpen);
  const pendingAction = useVoiceStore((s) => s.pendingAction);

  // A read-back must never be left behind a closed drawer; the operator has to answer it.
  useEffect(() => {
    if (pendingAction) setOpen(true);
  }, [pendingAction, setOpen]);

  return (
    <>
      <Tooltip title={t('voice.open')} placement="left">
        <FloatButton
          icon={<MessageOutlined />}
          type="primary"
          badge={pendingAction ? { dot: true } : undefined}
          onClick={() => setOpen(true)}
          aria-label={t('voice.open')}
          style={{ insetInlineEnd: 24, insetBlockEnd: (screens.md ?? true) ? 24 : 80, width: 56, height: 56 }}
        />
      </Tooltip>

      <Drawer
        open={open}
        onClose={() => setOpen(false)}
        title={t('voice.title')}
        width={(screens.md ?? true) ? 460 : '100%'}
        // Closing while a read-back is open would strand the action; cancel it from the modal instead.
        maskClosable={!pendingAction}
        closable={!pendingAction}
        extra={
          <Space>
            <Link to="/voice" onClick={() => setOpen(false)}>
              <Button size="small">{t('voice.history')}</Button>
            </Link>
          </Space>
        }
        styles={{ body: { paddingTop: 12 } }}
      >
        <ChatPanel compact />
      </Drawer>
    </>
  );
}
