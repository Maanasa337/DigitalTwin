import { ArrowLeftOutlined } from '@ant-design/icons';
import { Button, Card, Col, Descriptions, Row, Skeleton, Table, Tag, theme, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useParams } from 'react-router-dom';

import type { ModelMetric } from '../../api/types';
import { useModel, useModelMetrics } from '../../hooks/usePdm';
import { formatDateTime } from '../../lib/format';

const { Title, Text } = Typography;

/**
 * Model detail page — description, metrics table, feature importance placeholder.
 */
export default function ModelDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const { data: model, isLoading } = useModel(id ?? '');
  const { data: metrics } = useModelMetrics(id ?? '');

  if (isLoading || !id) {
    return (
      <div style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

  if (!model) {
    return (
      <div style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/models')}>
          Back
        </Button>
        <Text type="secondary" style={{ display: 'block', marginTop: 24 }}>
          Model not found
        </Text>
      </div>
    );
  }

  const metricCols: ColumnsType<ModelMetric> = [
    { title: 'Split', dataIndex: 'split', width: 100 },
    { title: 'Metric', dataIndex: 'metric', width: 150 },
    {
      title: 'Value',
      dataIndex: 'value',
      width: 120,
      render: (v: number) => v.toFixed(4),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/models')}
        style={{ marginBottom: 16 }}
      >
        Models
      </Button>

      <Card
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Title level={4} style={{ margin: 0 }}>
              {model.name} v{model.version}
            </Title>
            <Tag color={model.stage === 'production' ? 'green' : model.stage === 'candidate' ? 'blue' : 'default'}>
              {model.stage.toUpperCase()}
            </Tag>
          </div>
        }
        style={{ marginBottom: 20, borderRadius: token.borderRadiusLG }}
      >
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small">
          <Descriptions.Item label="Task">
            <Tag>{model.task}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Algorithm">{model.algorithm}</Descriptions.Item>
          <Descriptions.Item label="Asset Type">{model.asset_type ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="Dataset">{model.dataset_ref}</Descriptions.Item>
          <Descriptions.Item label="Window">{model.window_size ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="Stride">{model.stride ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="Horizon">{model.horizon ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="Trained">{formatDateTime(model.trained_at)}</Descriptions.Item>
          <Descriptions.Item label="Artifact">{model.artifact_uri}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={[20, 20]}>
        <Col xs={24} md={12}>
          <Card
            title="Metrics"
            size="small"
            style={{ borderRadius: token.borderRadiusLG }}
          >
            <Table<ModelMetric>
              rowKey="id"
              columns={metricCols}
              dataSource={metrics ?? []}
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card
            title="Feature Importance"
            size="small"
            style={{ borderRadius: token.borderRadiusLG }}
          >
            <div
              style={{
                padding: 32,
                textAlign: 'center',
                color: token.colorTextSecondary,
              }}
            >
              Feature importance chart will be rendered here once M6 (Explain) is built.
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
