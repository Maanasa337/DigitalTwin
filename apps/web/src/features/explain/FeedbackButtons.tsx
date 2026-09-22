import { DislikeOutlined, LikeOutlined, QuestionOutlined } from '@ant-design/icons';
import { App, Button, Flex, Form, Input, Modal, Select, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { FeedbackVerdict } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useSubmitFeedback } from '../../hooks/useXai';

interface FeedbackButtonsProps {
  explanationId: string;
  /** The explained asset's sensors; `Sensor` from api/types fits. Without them the suspect field is hidden. */
  sensors?: { id: string; name: string }[];
}

/**
 * Agree / Disagree / Unsure (FR-XAI-09).
 *
 * Disagreeing opens a dialog rather than submitting straight away: a bare "disagree" tells the
 * model team nothing, and naming the suspect sensor is what actually suppresses its confidence.
 */
export function FeedbackButtons({ explanationId, sensors = [] }: FeedbackButtonsProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const submit = useSubmitFeedback(explanationId);
  const [open, setOpen] = useState(false);
  const [given, setGiven] = useState<FeedbackVerdict | null>(null);
  const [form] = Form.useForm<{ reason?: string; suspect_sensor_id?: string }>();

  const send = (verdict: FeedbackVerdict, extra: { reason?: string; suspect_sensor_id?: string } = {}) => {
    submit.mutate(
      { verdict, ...extra },
      {
        onSuccess: () => {
          setGiven(verdict);
          setOpen(false);
          form.resetFields();
          void message.success(t('explain.feedback.thanks'));
        },
        onError,
      },
    );
  };

  if (given) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {t('explain.feedback.recorded', { verdict: t(`explain.feedback.verdict.${given}`) })}
      </Typography.Text>
    );
  }

  return (
    <>
      <Flex gap={8} wrap>
        <Button
          size="small"
          icon={<LikeOutlined />}
          loading={submit.isPending}
          onClick={() => send('agree')}
        >
          {t('explain.feedback.verdict.agree')}
        </Button>
        <Button size="small" icon={<DislikeOutlined />} onClick={() => setOpen(true)}>
          {t('explain.feedback.verdict.disagree')}
        </Button>
        <Button
          size="small"
          icon={<QuestionOutlined />}
          loading={submit.isPending}
          onClick={() => send('unsure')}
        >
          {t('explain.feedback.verdict.unsure')}
        </Button>
      </Flex>

      <Modal
        title={t('explain.feedback.disagreeTitle')}
        open={open}
        onCancel={() => setOpen(false)}
        okText={t('explain.feedback.submit')}
        confirmLoading={submit.isPending}
        onOk={() => {
          void form.validateFields().then((values) => send('disagree', values));
        }}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="reason" label={t('explain.feedback.reason')} rules={[{ max: 1000 }]}>
            <Input.TextArea rows={3} placeholder={t('explain.feedback.reasonPlaceholder')} />
          </Form.Item>
          {sensors.length > 0 && (
            <Form.Item
              name="suspect_sensor_id"
              label={t('explain.feedback.suspectSensor')}
              extra={t('explain.feedback.suspectSensorHint')}
            >
              <Select
                allowClear
                placeholder={t('explain.feedback.suspectSensorPlaceholder')}
                options={sensors.map((s) => ({ value: s.id, label: s.name }))}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  );
}
