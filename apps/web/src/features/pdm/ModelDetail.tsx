import { ArrowLeftOutlined, DownloadOutlined, RobotOutlined } from '@ant-design/icons';
import { Button, Card, Col, Descriptions, Flex, Row, Table, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { fetchModelOnnx } from '../../api/pdm';
import type { ModelMetric } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { PageHeader } from '../../components/PageHeader';
import { useApiError } from '../../hooks/useApiError';
import { useModel, useModelMetrics } from '../../hooks/usePdm';
import { downloadBlob } from '../../lib/download';
import { formatDateTime } from '../../lib/format';
import { problemStatus } from '../../lib/problem';
import { FeatureImportance } from '../explain/FeatureImportance';
import { QueryView } from '../twin/QueryView';
import { ModelStageTag } from './modelMeta';

/** Written by the training task: max |ONNX − native| over the parity sample (FR-EDGE-01). */
const PARITY_METRIC = 'onnx_parity_max_abs';
/**
 * Model detail page — description, metrics, top features and the ONNX export (§9.7 `/models/:id`).
 */
export default function ModelDetail() {
  const { t } = useTranslation();
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const onError = useApiError();
  const model = useModel(id);
  const metrics = useModelMetrics(id);
  const [downloading, setDownloading] = useState(false);

  const back = (
    <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/models')}>
      {t('models.back')}
    </Button>
  );

  if (model.isError && problemStatus(model.error) === 404) {
    return <EmptyState icon={<RobotOutlined />} description={t('models.notFound')} action={back} />;
  }

  const metricCols: ColumnsType<ModelMetric> = [
    { title: t('models.split'), dataIndex: 'split', width: 100 },
    { title: t('models.metric'), dataIndex: 'metric' },
    { title: t('models.value'), dataIndex: 'value', width: 120, align: 'right', render: (v: number) => v.toFixed(4) },
  ];

  return (
    <QueryView query={model} rows={8}>
      {(m) => {
        const parity = metrics.data?.find((x) => x.metric === PARITY_METRIC);
        const downloadOnnx = () => {
          setDownloading(true);
          fetchModelOnnx(m.id)
            .then((blob) => downloadBlob(blob, `${m.name}-${m.version}.onnx`))
            .catch(onError)
            .finally(() => setDownloading(false));
        };
        const onnxButton = (
          <Button icon={<DownloadOutlined />} disabled={!m.onnx_uri} loading={downloading} onClick={downloadOnnx}>
            {t('models.downloadOnnx')}
          </Button>
        );

        return (
          <>
            <PageHeader
              title={`${m.name} v${m.version}`}
              tags={<ModelStageTag stage={m.stage} />}
              actions={
                <>
                  {back}
                  {m.onnx_uri ? onnxButton : <Tooltip title={t('models.noOnnx')}>{onnxButton}</Tooltip>}
                </>
              }
            />
            <Flex vertical gap={16}>
              <Card size="small">
                <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small">
                  <Descriptions.Item label={t('models.task')}>{t(`models.taskName.${m.task}`)}</Descriptions.Item>
                  <Descriptions.Item label={t('models.algorithm')}>{m.algorithm}</Descriptions.Item>
                  <Descriptions.Item label={t('models.assetType')}>
                    {m.asset_type ? t(`assetType.${m.asset_type}`, { defaultValue: m.asset_type }) : '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('models.dataset')}>{m.dataset_ref}</Descriptions.Item>
                  <Descriptions.Item label={t('models.window')}>{m.window_size ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={t('models.stride')}>{m.stride ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={t('models.horizon')}>{m.horizon ?? '—'}</Descriptions.Item>
                  <Descriptions.Item label={t('models.trained')}>{formatDateTime(m.trained_at)}</Descriptions.Item>
                  <Descriptions.Item label={t('models.artifact')}>
                    <Typography.Text code copyable>
                      {m.artifact_uri}
                    </Typography.Text>
                  </Descriptions.Item>
                  <Descriptions.Item label={t('models.onnx')}>
                    {m.onnx_uri ? (
                      <Typography.Text code copyable>
                        {m.onnx_uri}
                      </Typography.Text>
                    ) : (
                      t('models.noOnnx')
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('models.onnxParity')}>
                    {parity ? parity.value.toExponential(2) : '—'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>

              <Row gutter={[16, 16]}>
                <Col xs={24} md={12}>
                  <Card title={t('models.metrics')} size="small">
                    <Table<ModelMetric>
                      rowKey="id"
                      columns={metricCols}
                      dataSource={metrics.data ?? []}
                      loading={metrics.isLoading}
                      locale={{ emptyText: t('models.noMetrics') }}
                      pagination={false}
                      size="small"
                    />
                  </Card>
                </Col>
                <Col xs={24} md={12}>
                  <Card title={t('models.importance')} size="small">
                    <FeatureImportance modelId={m.id} />
                  </Card>
                </Col>
              </Row>
            </Flex>
          </>
        );
      }}
    </QueryView>
  );
}
