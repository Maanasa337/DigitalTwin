import { useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Flex, Form, Modal, Radio, Result, Select, Spin, Steps, Typography } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { trainModel } from '../../api/pdm';
import { ASSET_TYPES, type AssetType } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useJob, useTrainModel } from '../../hooks/usePdm';
import { problemStatus } from '../../lib/problem';

type Source = 'synthetic' | 'cmapss' | 'ai4i';

interface TrainForm {
  source: Source;
  asset_type: AssetType;
  subset: string;
}

/** The simulator exports every modelled type; `other` has no physics, hence no training data. */
const TRAINABLE_TYPES = ASSET_TYPES.filter((type) => type !== 'other');
const CMAPSS_SUBSETS = ['FD001', 'FD002', 'FD003', 'FD004'];

/** What the worker's `train_and_register` accepts: RUL on simulator or C-MAPSS data, failure on AI4I. */
function requestFor(values: TrainForm): Parameters<typeof trainModel>[0] {
  switch (values.source) {
    case 'cmapss':
      return { task: 'rul', dataset_ref: `cmapss:${values.subset}` };
    case 'ai4i':
      return { task: 'failure', dataset_ref: 'ai4i' };
    default:
      return { task: 'rul', asset_type: values.asset_type, dataset_ref: `synthetic:${values.asset_type}` };
  }
}

const STEP: Record<string, number> = { queued: 0, running: 1, done: 2, failed: 1 };

/**
 * Queue a training job and follow it to a registered candidate model (FR-PM-02). The job is polled
 * from here rather than the dialog body, so closing the dialog does not lose it: the toast and the
 * registry refresh still happen when the worker finishes.
 */
export function TrainModelModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const queryClient = useQueryClient();
  const train = useTrainModel();
  const [form] = Form.useForm<TrainForm>();
  const source = Form.useWatch('source', form);
  const [jobId, setJobId] = useState<string>();
  // The API answers 503 when it could not reach the task queue, so nothing was queued.
  const [workerDown, setWorkerDown] = useState(false);
  const job = useJob(jobId);
  const status = job.data?.status ?? 'queued';
  const finished = status === 'done' || status === 'failed';

  const announced = useRef<string>(undefined);
  useEffect(() => {
    if (!jobId || !job.data || announced.current === jobId) return;
    if (job.data.status === 'done') {
      announced.current = jobId;
      void message.success(t('models.train.doneToast'));
      void queryClient.invalidateQueries({ queryKey: ['models'] });
    } else if (job.data.status === 'failed') {
      announced.current = jobId;
      void message.error(t('models.train.failedToast'));
    }
  }, [jobId, job.data, message, queryClient, t]);

  const submit = (values: TrainForm) =>
    train.mutate(requestFor(values), {
      onSuccess: (queued) => setJobId(queued.job_id),
      onError: (error) => (problemStatus(error) === 503 ? setWorkerDown(true) : onError(error)),
    });

  const reset = () => {
    setJobId(undefined);
    setWorkerDown(false);
  };

  const footer = !jobId
    ? [
        <Button key="cancel" onClick={onClose}>
          {t('common.cancel')}
        </Button>,
        <Button key="start" type="primary" loading={train.isPending} onClick={() => form.submit()}>
          {t('models.train.start')}
        </Button>,
      ]
    : [
        finished && (
          <Button key="another" onClick={reset}>
            {t('models.train.another')}
          </Button>
        ),
        <Button key="close" type={finished ? 'primary' : 'default'} onClick={onClose}>
          {t('common.close')}
        </Button>,
      ];

  return (
    <Modal open={open} title={t('models.train.title')} onCancel={onClose} footer={footer} width={560}>
      {!jobId ? (
        <Form<TrainForm>
          form={form}
          layout="vertical"
          initialValues={{ source: 'synthetic', asset_type: 'cnc_mill', subset: 'FD001' }}
          onFinish={submit}
          onValuesChange={() => setWorkerDown(false)}
        >
          <Form.Item name="source" label={t('models.train.source')}>
            <Radio.Group style={{ width: '100%' }}>
              <Flex vertical gap={8}>
                {(['synthetic', 'cmapss', 'ai4i'] as const).map((value) => (
                  <Radio key={value} value={value}>
                    <Flex vertical>
                      <Typography.Text>{t(`models.train.sourceName.${value}`)}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {t(`models.train.sourceHint.${value}`)}
                      </Typography.Text>
                    </Flex>
                  </Radio>
                ))}
              </Flex>
            </Radio.Group>
          </Form.Item>

          {source === 'synthetic' && (
            <Form.Item name="asset_type" label={t('models.assetType')} rules={[{ required: true }]}>
              <Select options={TRAINABLE_TYPES.map((value) => ({ value, label: t(`assetType.${value}`) }))} />
            </Form.Item>
          )}
          {source === 'cmapss' && (
            <Form.Item name="subset" label={t('models.train.subset')} rules={[{ required: true }]}>
              <Select options={CMAPSS_SUBSETS.map((value) => ({ value, label: value }))} />
            </Form.Item>
          )}

          {workerDown ? (
            <Alert type="error" showIcon message={t('models.train.workerDown')} />
          ) : (
            <Typography.Text type="secondary">{t('models.train.note')}</Typography.Text>
          )}
        </Form>
      ) : (
        <Flex vertical gap={16} style={{ paddingTop: 8 }}>
          <Steps
            size="small"
            current={STEP[status] ?? 0}
            status={status === 'failed' ? 'error' : status === 'done' ? 'finish' : 'process'}
            items={[
              { title: t('models.train.step.queued') },
              { title: t('models.train.step.running') },
              { title: t('models.train.step.done') },
            ]}
          />

          {job.isError && <Alert type="warning" showIcon message={t('errors.loadFailed')} />}

          {status === 'done' ? (
            <Result
              status="success"
              title={t('models.train.doneTitle')}
              subTitle={t('models.train.doneSubtitle')}
              extra={
                job.data?.model_id && (
                  <Link to={`/models/${job.data.model_id}`} onClick={onClose}>
                    <Button type="primary">{t('models.train.openModel')}</Button>
                  </Link>
                )
              }
            />
          ) : status === 'failed' ? (
            <Result
              status="error"
              title={t('models.train.failedTitle')}
              subTitle={job.data?.error || t('models.train.failedUnknown')}
            />
          ) : (
            <Flex vertical align="center" gap={12} style={{ padding: '24px 0' }} role="status" aria-live="polite">
              <Spin />
              <Typography.Text type="secondary" style={{ textAlign: 'center' }}>
                {t(status === 'running' ? 'models.train.running' : 'models.train.queued')}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('models.train.jobId', { id: jobId })}
              </Typography.Text>
            </Flex>
          )}
        </Flex>
      )}
    </Modal>
  );
}
