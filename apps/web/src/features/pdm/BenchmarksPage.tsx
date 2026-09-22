import { FileTextOutlined, PlayCircleOutlined, TrophyOutlined } from '@ant-design/icons';
import { Alert, App, Button, Card, Drawer, Flex, Form, InputNumber, Modal, Select, Skeleton, Space, Switch, Table, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { BENCHMARK_DATASETS, type BenchmarkDataset, type BenchmarkRun, type BenchmarkTarget } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { MiniMarkdown } from '../../components/MiniMarkdown';
import { PageHeader } from '../../components/PageHeader';
import { useApiError } from '../../hooks/useApiError';
import { useBenchmark, useBenchmarkReport, useBenchmarks, useRunBenchmark } from '../../hooks/usePdm';
import { formatDateTime, formatDuration, formatNumber } from '../../lib/format';
import { QueryView } from '../twin/QueryView';
import { BenchmarkStatusTag, resultRows, VerdictTag, type ResultRow } from './benchmarkMeta';

const PAGE_SIZE = 20;

interface RunForm {
  datasets: BenchmarkDataset[];
  seed: number;
  quick: boolean;
}

const durationS = (run: BenchmarkRun) =>
  run.finished_at ? (Date.parse(run.finished_at) - Date.parse(run.started_at)) / 1000 : null;

const formatMetric = (value: number) =>
  Math.abs(value) >= 100 ? formatNumber(value, 1) : Math.abs(value) >= 1 ? formatNumber(value, 3) : formatNumber(value, 4);

const formatTarget = (target?: BenchmarkTarget) =>
  target ? `${target.op === 'le' ? '≤' : '≥'} ${formatMetric(target.value)}` : '—';

function RunModal({ open, onClose, onStarted }: { open: boolean; onClose: () => void; onStarted: (id: string) => void }) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const run = useRunBenchmark();
  const [form] = Form.useForm<RunForm>();

  const submit = (values: RunForm) =>
    run.mutate(values, {
      onSuccess: (started) => {
        void message.success(t('benchmarks.startedToast'));
        onStarted(started.id);
        onClose();
      },
      onError,
    });

  return (
    <Modal
      open={open}
      title={t('benchmarks.runTitle')}
      okText={t('benchmarks.run')}
      onOk={() => form.submit()}
      okButtonProps={{ loading: run.isPending }}
      onCancel={onClose}
      destroyOnHidden
    >
      <Form<RunForm>
        form={form}
        layout="vertical"
        initialValues={{ datasets: ['FD001'], seed: 42, quick: true }}
        onFinish={submit}
        preserve={false}
      >
        <Form.Item
          name="datasets"
          label={t('benchmarks.datasets')}
          rules={[{ required: true, message: t('benchmarks.datasetsRequired') }]}
        >
          <Select mode="multiple" options={BENCHMARK_DATASETS.map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item name="seed" label={t('benchmarks.seed')}>
          <InputNumber min={0} precision={0} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="quick" label={t('benchmarks.quick')} valuePropName="checked" extra={t('benchmarks.quickHint')}>
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function RunResults({ id, onReport }: { id: string; onReport: (run: BenchmarkRun) => void }) {
  const { t } = useTranslation();
  const query = useBenchmark(id);

  return (
    <QueryView query={query} rows={4}>
      {(run) => (
        <Card
          size="small"
          title={t('benchmarks.results', { date: formatDateTime(run.started_at) })}
          extra={
            <Button icon={<FileTextOutlined />} disabled={run.status !== 'done'} onClick={() => onReport(run)}>
              {t('benchmarks.report')}
            </Button>
          }
        >
          {run.status === 'running' ? (
            <Alert type="info" showIcon message={t('benchmarks.running')} />
          ) : run.status === 'failed' ? (
            <Alert type="error" showIcon message={t('benchmarks.failed')} description={run.error} />
          ) : (
            <Table<ResultRow>
              rowKey="key"
              size="small"
              pagination={false}
              dataSource={resultRows(run)}
              locale={{ emptyText: t('benchmarks.noResults') }}
              columns={[
                { title: t('benchmarks.dataset'), dataIndex: 'dataset', width: 120 },
                { title: t('benchmarks.metric'), dataIndex: 'metric', render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
                { title: t('benchmarks.value'), dataIndex: 'value', align: 'right', render: formatMetric },
                { title: t('benchmarks.target'), dataIndex: 'target', align: 'right', render: formatTarget },
                { title: t('benchmarks.verdictLabel'), dataIndex: 'verdict', width: 130, render: (v: ResultRow['verdict']) => <VerdictTag value={v} /> },
              ]}
            />
          )}
        </Card>
      )}
    </QueryView>
  );
}

function ReportDrawer({ run, onClose }: { run: BenchmarkRun | null; onClose: () => void }) {
  const { t } = useTranslation();
  const report = useBenchmarkReport(run?.id, Boolean(run));
  return (
    <Drawer open={Boolean(run)} onClose={onClose} width={820} title={t('benchmarks.reportTitle')}>
      {report.isPending ? (
        <Skeleton active paragraph={{ rows: 12 }} />
      ) : report.isError ? (
        <Alert type="error" showIcon message={t('errors.loadFailed')} action={<Button onClick={() => void report.refetch()}>{t('common.retry')}</Button>} />
      ) : (
        <MiniMarkdown source={report.data} />
      )}
    </Drawer>
  );
}

/**
 * `/models/benchmarks` (FR-PM-09, UC-7): start a benchmark run on the public datasets, follow it
 * while the worker runs it, and compare each metric with its PRD §4.5 target.
 */
export default function BenchmarksPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState<string>();
  const [reportRun, setReportRun] = useState<BenchmarkRun | null>(null);
  const runs = useBenchmarks({ page, size: PAGE_SIZE });
  const selectedId = selected ?? runs.data?.items[0]?.id;

  const runButton = (
    <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setRunning(true)}>
      {t('benchmarks.run')}
    </Button>
  );

  return (
    <>
      <PageHeader title={t('benchmarks.title')} subtitle={t('benchmarks.subtitle')} actions={runButton} />
      <QueryView query={runs}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState icon={<TrophyOutlined />} description={t('benchmarks.empty')} action={runButton} />
          ) : (
            <Flex vertical gap={16}>
              <Card size="small" title={t('benchmarks.runs')}>
                <Table<BenchmarkRun>
                  rowKey="id"
                  size="small"
                  dataSource={data.items}
                  rowSelection={{
                    type: 'radio',
                    selectedRowKeys: selectedId ? [selectedId] : [],
                    onChange: (keys) => setSelected(String(keys[0])),
                  }}
                  onRow={(row) => ({ onClick: () => setSelected(row.id), style: { cursor: 'pointer' } })}
                  pagination={{ current: page, pageSize: PAGE_SIZE, total: data.total, onChange: setPage, hideOnSinglePage: true }}
                  columns={[
                    { title: t('benchmarks.startedAt'), dataIndex: 'started_at', render: formatDateTime },
                    {
                      title: t('benchmarks.statusLabel'),
                      dataIndex: 'status',
                      width: 130,
                      render: (v: BenchmarkRun['status']) => <BenchmarkStatusTag status={v} />,
                    },
                    {
                      title: t('benchmarks.datasets'),
                      dataIndex: 'datasets',
                      render: (v: string[]) => (
                        <Space size={4} wrap>
                          {v.map((d) => (
                            <Tag key={d} style={{ marginInlineEnd: 0 }}>
                              {d}
                            </Tag>
                          ))}
                        </Space>
                      ),
                    },
                    { title: t('benchmarks.seed'), dataIndex: 'seed', width: 80, align: 'right' },
                    {
                      title: t('benchmarks.gitSha'),
                      dataIndex: 'git_sha',
                      width: 110,
                      render: (v: string | null) => (v ? <Typography.Text code>{v.slice(0, 7)}</Typography.Text> : '—'),
                    },
                    {
                      title: t('benchmarks.duration'),
                      key: 'duration',
                      width: 110,
                      align: 'right',
                      render: (_: unknown, row) => formatDuration(durationS(row)),
                    },
                  ]}
                />
              </Card>
              {selectedId && <RunResults id={selectedId} onReport={setReportRun} />}
            </Flex>
          )
        }
      </QueryView>
      <RunModal open={running} onClose={() => setRunning(false)} onStarted={(id) => setSelected(id)} />
      <ReportDrawer run={reportRun} onClose={() => setReportRun(null)} />
    </>
  );
}
