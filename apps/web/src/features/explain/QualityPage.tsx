import { Alert, Card, Col, Flex, Row, Select, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { NarrationAuditRow, XaiQualityMetric } from '../../api/types';
import { KpiTile } from '../../components/KpiTile';
import { PageHeader } from '../../components/PageHeader';
import { useModels } from '../../hooks/usePdm';
import { useNarrationAudits, useXaiQualityMetrics } from '../../hooks/useXai';
import { formatDateTime } from '../../lib/format';

/** How each metric reads, so the table does not present six numbers with no direction. */
const METRIC_HELP: Record<string, { label: string; better: 'higher' | 'lower' }> = {
  deletion_auc: { label: 'Deletion AUC', better: 'lower' },
  insertion_auc: { label: 'Insertion AUC', better: 'higher' },
  pgi: { label: 'Prediction Gap (important)', better: 'higher' },
  sensitivity_max: { label: 'Max sensitivity', better: 'lower' },
  sparsity: { label: 'Sparsity', better: 'higher' },
  truth_top1_agreement: { label: 'Truth top-1 agreement', better: 'higher' },
  window_jaccard: { label: 'Window stability', better: 'higher' },
};

/**
 * Explanation quality per model (FR-XAI-08): faithfulness metrics plus the narration audit record.
 */
export default function QualityPage() {
  const { t } = useTranslation();
  const [modelId, setModelId] = useState<string | undefined>();

  const { data: models } = useModels({ size: 200 });
  const { data: quality, isLoading } = useXaiQualityMetrics(modelId);
  const { data: audits, isLoading: auditsLoading } = useNarrationAudits({ model: modelId, limit: 100 });

  const failed = (audits ?? []).filter((row) => !row.audit.passed);

  const metricColumns: ColumnsType<XaiQualityMetric> = [
    {
      title: 'Metric',
      dataIndex: 'metric',
      render: (v: string) => {
        const help = METRIC_HELP[v];
        return help ? (
          <Tooltip title={`${help.better === 'higher' ? 'Higher' : 'Lower'} is better`}>
            <span>{help.label}</span>
          </Tooltip>
        ) : (
          v
        );
      },
    },
    { title: 'Method', dataIndex: 'method', width: 140 },
    {
      title: 'Value',
      dataIndex: 'value',
      width: 110,
      align: 'right',
      render: (v: number) => v.toFixed(4),
    },
    { title: 'Dataset', dataIndex: 'dataset_ref', width: 160, render: (v: string | null) => v ?? '—' },
    {
      title: 'Computed',
      dataIndex: 'computed_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
  ];

  const auditColumns: ColumnsType<NarrationAuditRow> = [
    { title: 'Kind', dataIndex: 'kind', width: 110 },
    { title: 'Lang', dataIndex: 'lang', width: 70 },
    {
      title: 'Rank',
      width: 90,
      align: 'right',
      render: (_, r) => r.audit.rank_agreement.toFixed(2),
    },
    {
      title: 'Sign',
      width: 90,
      align: 'right',
      render: (_, r) => r.audit.sign_agreement.toFixed(2),
    },
    {
      title: 'Numbers',
      width: 100,
      render: (_, r) => (
        <Tag color={r.audit.numeric_within_tolerance ? 'success' : 'error'} style={{ marginInlineEnd: 0 }}>
          {r.audit.numeric_within_tolerance ? 'ok' : 'drifted'}
        </Tag>
      ),
    },
    {
      title: 'Hallucinated',
      render: (_, r) =>
        r.audit.hallucinated_features.length ? r.audit.hallucinated_features.join(', ') : '—',
    },
    { title: 'Text shown', dataIndex: 'final_text', ellipsis: true },
  ];

  const passRate = quality?.narration_audit_pass_rate;

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title={t('explainQuality.title', 'Explanation quality')}
        subtitle={t(
          'explainQuality.subtitle',
          'How faithful the attributions are, and whether generated narration survives its audit.',
        )}
        actions={
          <Select
            style={{ minWidth: 280 }}
            placeholder={t('explainQuality.pickModel', 'Select a model')}
            value={modelId}
            onChange={setModelId}
            showSearch
            optionFilterProp="label"
            options={(models?.items ?? []).map((m) => ({
              value: m.id,
              label: `${m.name} v${m.version} (${m.task})`,
            }))}
          />
        }
      />

      {!modelId ? (
        <Alert
          type="info"
          showIcon
          message={t('explainQuality.selectPrompt', 'Select a model to see its explanation quality.')}
        />
      ) : (
        <Flex vertical gap={16}>
          <Row gutter={[12, 12]}>
            <Col xs={12} md={8}>
              <KpiTile
                title={t('explainQuality.passRate', 'Narration audit pass rate')}
                value={passRate != null ? passRate * 100 : null}
                unit="%"
                digits={1}
                formula="Narrations whose LLM wording passed rank, sign, numeric and vocabulary checks"
              />
            </Col>
            <Col xs={12} md={8}>
              <KpiTile
                title={t('explainQuality.audited', 'Narrations audited')}
                value={quality?.narration_audit_count ?? 0}
              />
            </Col>
            <Col xs={24} md={8}>
              <KpiTile
                title={t('explainQuality.failed', 'Failed audits shown')}
                value={failed.length}
                formula="Narrations that fell back to the deterministic template"
              />
            </Col>
          </Row>

          <Card size="small" title={t('explainQuality.metrics', 'Faithfulness and stability')}>
            <Table<XaiQualityMetric>
              rowKey="id"
              size="small"
              loading={isLoading}
              columns={metricColumns}
              dataSource={quality?.metrics ?? []}
              pagination={false}
              locale={{
                emptyText: t(
                  'explainQuality.noMetrics',
                  'No quality metrics recorded yet — they are computed at train time and nightly.',
                ),
              }}
            />
          </Card>

          <Card
            size="small"
            title={
              <Flex gap={8} align="center">
                <span>{t('explainQuality.audits', 'Recent narration audits')}</span>
                {failed.length > 0 && (
                  <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                    {failed.length} failed
                  </Tag>
                )}
              </Flex>
            }
          >
            <Table<NarrationAuditRow>
              rowKey={(r) => r.audit.id}
              size="small"
              loading={auditsLoading}
              columns={auditColumns}
              dataSource={audits ?? []}
              pagination={{ pageSize: 20, showSizeChanger: false }}
              rowClassName={(r) => (r.audit.passed ? '' : 'row-audit-failed')}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {t(
                'explainQuality.auditNote',
                'A failed audit is not an outage: the deterministic template text is shown instead.',
              )}
            </Typography.Text>
          </Card>
        </Flex>
      )}
    </div>
  );
}
