import { FileAddOutlined } from '@ant-design/icons';
import { Button, Card, Flex, Select, Space, Table } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Report, ReportStatus, ReportType } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { useReports } from '../../hooks/useReports';
import { formatDateTime, formatRelative } from '../../lib/format';
import { GenerateReportModal } from './GenerateReportModal';
import { ReportPreviewDrawer } from './ReportPreviewDrawer';
import { REPORT_TYPES, ReportStatusTag } from './reportMeta';
import { SchedulesTable } from './SchedulesTable';

const STATUSES: ReportStatus[] = ['queued', 'running', 'done', 'failed'];

/** `/reports`: the archive, the generate modal, the schedule table and the preview drawer (§M10 UI). */
export default function ReportsPage() {
  const { t } = useTranslation();
  const [type, setType] = useState<ReportType>();
  const [status, setStatus] = useState<ReportStatus>();
  const [page, setPage] = useState(1);
  const [generating, setGenerating] = useState(false);
  const [preview, setPreview] = useState<Report | null>(null);

  const reports = useReports({ page, size: 20, type, status });

  return (
    <>
      <PageHeader
        title={t('reports.pageTitle')}
        subtitle={t('reports.pageSubtitle')}
        actions={
          <Button type="primary" icon={<FileAddOutlined />} onClick={() => setGenerating(true)}>
            {t('reports.generate')}
          </Button>
        }
      />

      <Flex vertical gap={16}>
        <Card
          title={t('reports.archive')}
          extra={
            <Space>
              <Select
                allowClear
                placeholder={t('reports.type')}
                style={{ minWidth: 200 }}
                value={type}
                onChange={(value) => {
                  setType(value);
                  setPage(1);
                }}
                options={REPORT_TYPES.map((value) => ({ value, label: t(`reports.typeName.${value}`) }))}
              />
              <Select
                allowClear
                placeholder={t('reports.statusLabel')}
                style={{ minWidth: 140 }}
                value={status}
                onChange={(value) => {
                  setStatus(value);
                  setPage(1);
                }}
                options={STATUSES.map((value) => ({ value, label: t(`reports.status.${value}`) }))}
              />
            </Space>
          }
        >
          <Table<Report>
            rowKey="id"
            size="small"
            loading={reports.isLoading}
            dataSource={reports.data?.items ?? []}
            locale={{ emptyText: t('reports.noReports') }}
            onRow={(row) => ({ onClick: () => setPreview(row), style: { cursor: 'pointer' } })}
            pagination={{
              current: page,
              pageSize: 20,
              total: reports.data?.total ?? 0,
              onChange: setPage,
              hideOnSinglePage: true,
            }}
            columns={[
              {
                title: t('reports.type'),
                dataIndex: 'type',
                render: (value: ReportType) => t(`reports.typeName.${value}`),
              },
              {
                title: t('reports.statusLabel'),
                dataIndex: 'status',
                width: 130,
                render: (value: ReportStatus) => <ReportStatusTag status={value} />,
              },
              {
                title: t('reports.format'),
                dataIndex: 'format',
                width: 90,
                render: (value: string) => value.toUpperCase(),
              },
              {
                title: t('reports.period'),
                dataIndex: 'period_start',
                render: (_: unknown, row) =>
                  `${formatDateTime(row.period_start)} → ${formatDateTime(row.period_end)}`,
              },
              { title: t('reports.requestedVia'), dataIndex: 'requested_via', width: 110 },
              {
                title: t('reports.createdAt'),
                dataIndex: 'created_at',
                width: 140,
                render: (value: string) => formatRelative(value),
              },
            ]}
          />
        </Card>

        <SchedulesTable />
      </Flex>

      <GenerateReportModal open={generating} onClose={() => setGenerating(false)} />
      <ReportPreviewDrawer report={preview} onClose={() => setPreview(null)} />
    </>
  );
}
