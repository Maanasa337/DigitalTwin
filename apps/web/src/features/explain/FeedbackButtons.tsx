import { DislikeOutlined, LikeOutlined, QuestionOutlined } from '@ant-design/icons';
import { App, Button, Flex, Form, Input, Modal, Select, Typography } from 'antd';
import { useState } from 'react';

import type { FeedbackVerdict } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useSubmitFeedback } from '../../hooks/useXai';

interface FeedbackButtonsProps {
  explanationId: string;
  sensors?: { id: string; name: string }[];
}

/**
 * Agree / Disagree / Unsure (FR-XAI-09).
 *
 * Disagreeing opens a dialog rather than submitting straight away: a bare "disagree" tells the
 * model team nothing, and naming the suspect sensor is what actually suppresses its confidence.
 */
export function FeedbackButtons({ explanationId, sensors = [] }: FeedbackButtonsProps) {
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
          void message.success('Thanks — your feedback was recorded');
        },
        onError,
      },
    );
  };

  if (given) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Feedback recorded: {given}
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
          Agree
        </Button>
        <Button size="small" icon={<DislikeOutlined />} onClick={() => setOpen(true)}>
          Disagree
        </Button>
        <Button
          size="small"
          icon={<QuestionOutlined />}
          loading={submit.isPending}
          onClick={() => send('unsure')}
        >
          Unsure
        </Button>
      </Flex>

      <Modal
        title="What does the explanation get wrong?"
        open={open}
        onCancel={() => setOpen(false)}
        okText="Submit"
        confirmLoading={submit.isPending}
        onOk={() => {
          void form.validateFields().then((values) => send('disagree', values));
        }}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="reason" label="Reason" rules={[{ max: 1000 }]}>
            <Input.TextArea rows={3} placeholder="What did you see that the model missed?" />
          </Form.Item>
          {sensors.length > 0 && (
            <Form.Item
              name="suspect_sensor_id"
              label="Suspect sensor"
              extra="Flagging a sensor lowers the confidence of predictions that use it for one hour."
            >
              <Select
                allowClear
                placeholder="Select a sensor you believe is misreading"
                options={sensors.map((s) => ({ value: s.id, label: s.name }))}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  );
}
