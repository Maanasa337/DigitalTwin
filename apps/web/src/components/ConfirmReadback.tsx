import { Button, Flex, Input, Modal, Progress, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface ConfirmReadbackProps {
  open: boolean;
  text: string;
  requirePin?: boolean;
  seconds?: number;
  loading?: boolean;
  onConfirm: (pin: string | undefined) => void;
  onCancel: () => void;
}

export function ConfirmReadback({ open, ...rest }: ConfirmReadbackProps) {
  const { t } = useTranslation();
  return (
    <Modal
      open={open}
      title={t('confirm.title')}
      footer={null}
      keyboard={false}
      maskClosable={false}
      closable={false}
      destroyOnHidden
      width={480}
    >
      {open && <ReadbackBody {...rest} />}
    </Modal>
  );
}

function ReadbackBody({
  text,
  requirePin = false,
  seconds = 10,
  loading = false,
  onConfirm,
  onCancel,
}: Omit<ConfirmReadbackProps, 'open'>) {
  const { t } = useTranslation();
  const [remaining, setRemaining] = useState(seconds);
  const [pin, setPin] = useState('');
  const canConfirm = !loading && (!requirePin || pin.length > 0);

  useEffect(() => {
    if (loading) return;
    const id = setInterval(() => setRemaining((r) => r - 1), 1000);
    return () => clearInterval(id);
  }, [loading]);

  useEffect(() => {
    if (remaining <= 0) onCancel();
  }, [remaining, onCancel]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
      } else if (event.key === 'Enter' && !(event.target instanceof HTMLButtonElement)) {
        event.preventDefault();
        if (canConfirm) onConfirm(requirePin ? pin : undefined);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canConfirm, onCancel, onConfirm, pin, requirePin]);

  return (
    <Flex vertical gap={16}>
      <Flex gap={16} align="center">
        <Progress
          type="circle"
          size={64}
          percent={(Math.max(remaining, 0) / seconds) * 100}
          format={() => t('confirm.secondsLeft', { count: Math.max(remaining, 0) })}
          aria-label={t('confirm.countdown', { count: Math.max(remaining, 0) })}
        />
        <Typography.Paragraph style={{ fontSize: 20, margin: 0 }} aria-live="polite">
          {text}
        </Typography.Paragraph>
      </Flex>
      {requirePin && (
        <label>
          <Typography.Text type="secondary">{t('confirm.pin')}</Typography.Text>
          <Input.Password
            autoFocus
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={12}
            value={pin}
            aria-label={t('confirm.pin')}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
          />
        </label>
      )}
      <Flex justify="end" gap={8}>
        <Button onClick={onCancel}>{t('common.cancel')}</Button>
        <Button
          type="primary"
          autoFocus={!requirePin}
          disabled={!canConfirm && !loading}
          loading={loading}
          onClick={() => onConfirm(requirePin ? pin : undefined)}
        >
          {t('confirm.confirm')}
        </Button>
      </Flex>
    </Flex>
  );
}
