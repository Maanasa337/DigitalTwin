import { RocketOutlined } from '@ant-design/icons';
import { Button, message, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { promoteModel } from '../../api/pdm';
import type { PdmModel, ModelStage, ModelTask } from '../../api/types';
import { useModels } from '../../hooks/usePdm';
import { formatDateTime } from '../../lib/format';

const { Title } = Typography;

const STAGE_COLORS: Record<ModelStage, string> = {
  candidate: 'blue',
  production: 'green',
  archived: 'default',
};

const TASK_COLORS: Record<ModelTask, string> = {
  anomaly: 'purple',
  failure: 'orange',
  rul: 'cyan',
  survival: 'magenta',
};

/**
 * Models registry page — table with promote/rollback actions.
 */
export default function ModelsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data, isLoading, refetch } = useModels();

  const handlePromote = async (id: string) => {
    try {
      await promoteModel(id);
      message.success('Model promoted to production');
      refetch();
    } catch {
      message.error('Promotion failed');
    }
  };

  const columns: ColumnsType<PdmModel> = [
    {
      title: 'Name',
      dataIndex: 'name',
      render: (v: string, r) => (
        <a onClick={() => navigate(`/models/${r.id}`)} style={{ fontWeight: 500 }}>
          {v}
        </a>
      ),
    },
    {
      title: 'Version',
      dataIndex: 'version',
      width: 120,
    },
    {
      title: 'Task',
      dataIndex: 'task',
      width: 100,
      render: (v: ModelTask) => <Tag color={TASK_COLORS[v]}>{v}</Tag>,
    },
    {
      title: 'Algorithm',
      dataIndex: 'algorithm',
      width: 120,
    },
    {
      title: 'Stage',
      dataIndex: 'stage',
      width: 120,
      render: (v: ModelStage) => (
        <Tag color={STAGE_COLORS[v]} style={{ fontWeight: 600 }}>
          {v.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Trained',
      dataIndex: 'trained_at',
      width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: 'Action',
      width: 120,
      render: (_, r) =>
        r.stage === 'candidate' ? (
          <Button
            size="small"
            icon={<RocketOutlined />}
            onClick={(e) => {
              e.stopPropagation();
              handlePromote(r.id);
            }}
          >
            Promote
          </Button>
        ) : null,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          {t('models.title', 'Model Registry')}
        </Title>
      </div>
      <Table<PdmModel>
        rowKey="id"
        columns={columns}
        dataSource={data?.items ?? []}
        loading={isLoading}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        size="small"
        onRow={(record) => ({
          onClick: () => navigate(`/models/${record.id}`),
          style: { cursor: 'pointer' },
        })}
      />
    </div>
  );
}
