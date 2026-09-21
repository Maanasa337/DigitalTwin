import { DownloadOutlined } from '@ant-design/icons';
import { Alert, Button, Descriptions, Drawer, Flex, Skeleton, Typography } from 'antd';
import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { Report } from '../../api/types';
import { fetchReportFile } from '../../api/reports';
import { useApiError } from '../../hooks/useApiError';
import { useReportFile } from '../../hooks/useReports';
import { downloadBlob } from '../../lib/download';
import { formatDateTime } from '../../lib/format';
import { ReportStatusTag } from './reportMeta';

/**
 * Preview and download. A PDF or HTML report is shown in an object frame from a blob URL, because
 * the file endpoint needs a bearer token and a bare `src` cannot carry one.
 */
export function ReportPreviewDrawer({ report, onClose }: { report: Report | null; onClose: () => void }) {
  const { t } = useTranslation();
  const onError = useApiError();
  const inline = report?.format === 'pdf' || report?.format === 'html';
  const file = useReportFile(report?.id, Boolean(report) && report?.status === 'done');

  // The blob URL is derived from the fetched file, not stored: the effect only has to release it.
  const url = useMemo(() => (file.data ? URL.createObjectURL(file.data) : undefined), [file.data]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);

  const download = () => {
    if (!report) return;
    fetchReportFile(report.id, true)
      .then((blob) => downloadBlob(blob, `${report.type}-${report.id.slice(0, 8)}.${report.format}`))
      .catch(onError);
  };

  return (
    <Drawer
      open={Boolean(report)}
      onClose={onClose}
      width={880}
      title={report ? t(`reports.typeName.${report.type}`) : ''}
      extra={
        <Button
          icon={<DownloadOutlined />}
          type="primary"
          disabled={!report || report.status !== 'done'}
          onClick={download}
        >
          {t('common.download')}
        </Button>
      }
    >
      {report && (
        <Flex vertical gap={16}>
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label={t('reports.statusLabel')}>
              <ReportStatusTag status={report.status} />
            </Descriptions.Item>
            <Descriptions.Item label={t('reports.format')}>{report.format.toUpperCase()}</Descriptions.Item>
            <Descriptions.Item label={t('reports.period')} span={2}>
              {formatDateTime(report.period_start)} → {formatDateTime(report.period_end)}
            </Descriptions.Item>
            <Descriptions.Item label={t('reports.requestedVia')}>{report.requested_via}</Descriptions.Item>
            <Descriptions.Item label={t('reports.createdAt')}>
              {formatDateTime(report.created_at)}
            </Descriptions.Item>
          </Descriptions>

          {report.status === 'failed' && (
            <Alert type="error" showIcon message={t('reports.failed')} description={report.error} />
          )}

          {report.summary_text && (
            <Alert
              type={report.summary_audit?.passed === false ? 'warning' : 'info'}
              showIcon
              message={t('reports.summary')}
              description={
                <Flex vertical gap={6}>
                  <Typography.Paragraph style={{ margin: 0 }}>{report.summary_text}</Typography.Paragraph>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {report.summary_audit?.used_llm
                      ? t('reports.auditLlm')
                      : t('reports.auditTemplate')}
                    {report.summary_audit?.passed === false &&
                      ` · ${t('reports.auditFailed', { reason: report.summary_audit.reason })}`}
                  </Typography.Text>
                </Flex>
              }
            />
          )}

          {report.status === 'done' &&
            (file.isLoading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : inline && url ? (
              <object data={url} type={report.format === 'pdf' ? 'application/pdf' : 'text/html'} width="100%" height={560}>
                <Typography.Text>{t('reports.previewUnavailable')}</Typography.Text>
              </object>
            ) : (
              <Alert type="info" showIcon message={t('reports.previewUnavailable')} />
            ))}
        </Flex>
      )}
    </Drawer>
  );
}
