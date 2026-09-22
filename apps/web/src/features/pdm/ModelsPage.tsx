import { ExperimentOutlined, RobotOutlined, RocketOutlined, TrophyOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { App, Button, Popconfirm, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { promoteModel } from '../../api/pdm';
import type { PdmModel, ModelTask } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { PageHeader } from '../../components/PageHeader';
import { useApiError } from '../../hooks/useApiError';
import { useModels } from '../../hooks/usePdm';
import { formatDateTime } from '../../lib/format';
import { QueryView } from '../twin/QueryView';
import { ModelStageTag } from './modelMeta';
import { TrainModelModal } from './TrainModelModal';

/**
 * Models registry page — table with promote actions, and training of new candidates.
 */
export default function ModelsPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const models = useModels();
  const [training, setTraining] = useState(false);

  const handlePromote = async (id: string) => {
    try {
      await promoteModel(id);
      void message.success(t('models.promoted'));
      void queryClient.invalidateQueries({ queryKey: ['models'] });
    } catch (err) {
      onError(err);
    }
  };

  const columns: ColumnsType<PdmModel> = [
    {
      title: t('models.name'),
      dataIndex: 'name',
      render: (v: string, r) => (
        <Link to={`/models/${r.id}`} onClick={(e) => e.stopPropagation()} style={{ fontWeight: 500 }}>
          {v}
        </Link>
      ),
    },
    { title: t('models.version'), dataIndex: 'version', width: 120 },
    {
      title: t('models.task'),
      dataIndex: 'task',
      width: 120,
      render: (v: ModelTask) => <Tag style={{ marginInlineEnd: 0 }}>{t(`models.taskName.${v}`)}</Tag>,
    },
    { title: t('models.algorithm'), dataIndex: 'algorithm', width: 140 },
    {
      title: t('models.stage'),
      dataIndex: 'stage',
      width: 140,
      render: (v: PdmModel['stage']) => <ModelStageTag stage={v} />,
    },
    { title: t('models.trained'), dataIndex: 'trained_at', width: 170, render: (v: string) => formatDateTime(v) },
    {
      title: t('models.action'),
      width: 130,
      render: (_, r) =>
        r.stage === 'candidate' ? (
          <span onClick={(e) => e.stopPropagation()}>
            <Popconfirm title={t('models.promoteConfirm', { name: r.name, version: r.version })} onConfirm={() => handlePromote(r.id)}>
              <Button size="small" icon={<RocketOutlined />}>
                {t('models.promote')}
              </Button>
            </Popconfirm>
          </span>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title={t('models.title')}
        subtitle={t('models.subtitle')}
        actions={
          <>
            <Link to="/models/benchmarks">
              <Button icon={<TrophyOutlined />}>{t('nav.benchmarks')}</Button>
            </Link>
            <Button type="primary" icon={<ExperimentOutlined />} onClick={() => setTraining(true)}>
              {t('models.train.button')}
            </Button>
          </>
        }
      />
      <QueryView query={models}>
        {(data) =>
          data.items.length === 0 ? (
            <EmptyState
              icon={<RobotOutlined />}
              description={t('models.empty')}
              action={
                <Button type="primary" icon={<ExperimentOutlined />} onClick={() => setTraining(true)}>
                  {t('models.train.button')}
                </Button>
              }
            />
          ) : (
            <Table<PdmModel>
              rowKey="id"
              columns={columns}
              dataSource={data.items}
              pagination={{ pageSize: 20, showSizeChanger: false, hideOnSinglePage: true }}
              size="small"
              onRow={(record) => ({
                onClick: () => navigate(`/models/${record.id}`),
                style: { cursor: 'pointer' },
              })}
            />
          )
        }
      </QueryView>
      <TrainModelModal open={training} onClose={() => setTraining(false)} />
    </>
  );
}
