import { ReloadOutlined } from '@ant-design/icons';
import { Alert, App, Button, Card, Col, Flex, Row, Select, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { NarrationAuditRow, PdmModel, XaiQualityMetric } from '../../api/types';
import { KpiTile } from '../../components/KpiTile';
import { PageHeader } from '../../components/PageHeader';
import { useApiError } from '../../hooks/useApiError';
import { useModels } from '../../hooks/usePdm';
import { useNarrationAudits, useRefreshQualityMetrics, useXaiQualityMetrics } from '../../hooks/useXai';
import { formatDateTime } from '../../lib/format';
import { FeatureImportance, PartialDependence } from './FeatureImportance';

/** How each metric reads, so the table does not present numbers with no direction. */
const METRIC_HELP: Record<string, { better: 'higher' | 'lower' }> = {
  deletion_auc: { better: 'lower' },
  insertion_auc: { better: 'higher' },
  pgi: { better: 'higher' },
  sensitivity_max: { better: 'lower' },
  sparsity: { better: 'higher' },
  truth_top1_agreement: { better: 'higher' },
  window_jaccard: { better: 'higher' },
};
const METRIC_ORDER = Object.keys(METRIC_HELP);

/** Live fleet models first (they have an asset type), newest first; benchmark models after. */
function defaultModel(models: PdmModel[]): PdmModel | undefined {
  const production = models.filter((m) => m.stage === 'production');
  return production.find((m) => m.asset_type) ?? production[0] ?? models[0];
}

/**
 * Explanation quality per model (FR-XAI-08): global importance and partial dependence, the
 * faithfulness and stability metrics, and — when an LLM paraphrases narrations — the audit record.
 */
export default function QualityPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const onError = useApiError();
  const [picked, setPicked] = useState<string | undefined>();

  const { data: models, isPending: modelsPending } = useModels({ size: 200 });
  const modelId = picked ?? defaultModel(models?.items ?? [])?.id;
  const model = models?.items.find((m) => m.id === modelId);
  const { data: quality, isLoading } = useXaiQualityMetrics(modelId);
  const { data: audits, isLoading: auditsLoading } = useNarrationAudits({ model: modelId, limit: 100 });
  const refresh = useRefreshQualityMetrics(modelId);

  const failed = (audits ?? []).filter((row) => !row.audit.passed);
  const metrics = [...(quality?.metrics ?? [])].sort(
    (a, b) => METRIC_ORDER.indexOf(a.metric) - METRIC_ORDER.indexOf(b.metric),
  );
  const metricValue = (name: string) => metrics.find((m) => m.metric === name)?.value ?? null;

  const recompute = () =>
    refresh.mutate(undefined, {
      onSuccess: () => void message.success(t('explainQuality.refreshQueued')),
      onError,
    });

  const metricColumns: ColumnsType<XaiQualityMetric> = [
    {
      title: t('explainQuality.col.metric'),
      dataIndex: 'metric',
      render: (v: string) => (
        <Tooltip title={t(`explainQuality.metric.${v}.help`, { defaultValue: '' }) || undefined}>
          <span>{t(`explainQuality.metric.${v}.label`, { defaultValue: v })}</span>
        </Tooltip>
      ),
    },
    {
      title: t('explainQuality.col.better'),
      dataIndex: 'metric',
      width: 110,
      render: (v: string) =>
        METRIC_HELP[v] ? t(`explainQuality.better.${METRIC_HELP[v].better}`) : '—',
    },
    {
      title: t('explainQuality.col.value'),
      dataIndex: 'value',
      width: 110,
      align: 'right',
      render: (v: number) => <span className="tabular">{v.toFixed(4)}</span>,
    },
    { title: t('explainQuality.col.sample'), dataIndex: 'dataset_ref', render: (v: string | null) => v ?? '—' },
    {
      title: t('explainQuality.col.computed'),
      dataIndex: 'computed_at',
      width: 180,
      render: (v: string) => formatDateTime(v),
    },
  ];

  const auditColumns: ColumnsType<NarrationAuditRow> = [
    { title: t('explainQuality.audit.kind'), dataIndex: 'kind', width: 110 },
    { title: t('explainQuality.audit.lang'), dataIndex: 'lang', width: 70 },
    {
      title: t('explainQuality.audit.rank'),
      width: 90,
      align: 'right',
      render: (_, r) => r.audit.rank_agreement.toFixed(2),
    },
    {
      title: t('explainQuality.audit.sign'),
      width: 90,
      align: 'right',
      render: (_, r) => r.audit.sign_agreement.toFixed(2),
    },
    {
      title: t('explainQuality.audit.numbers'),
      width: 100,
      render: (_, r) => (
        <Tag color={r.audit.numeric_within_tolerance ? 'success' : 'error'} style={{ marginInlineEnd: 0 }}>
          {t(r.audit.numeric_within_tolerance ? 'explainQuality.audit.ok' : 'explainQuality.audit.drifted')}
        </Tag>
      ),
    },
    {
      title: t('explainQuality.audit.hallucinated'),
      render: (_, r) =>
        r.audit.hallucinated_features.length ? r.audit.hallucinated_features.join(', ') : '—',
    },
    { title: t('explainQuality.audit.text'), dataIndex: 'final_text', ellipsis: true },
  ];

  const outputLabel =
    model?.task === 'rul' ? t('explainQuality.outputRul') : t('explainQuality.outputProbability');

  return (
    <>
      <PageHeader
        title={t('explainQuality.title')}
        subtitle={t('explainQuality.subtitle')}
        actions={
          <>
            <Select
              style={{ minWidth: 300 }}
              placeholder={t('explainQuality.pickModel')}
              loading={modelsPending}
              value={modelId}
              onChange={setPicked}
              showSearch
              optionFilterProp="label"
              options={(models?.items ?? []).map((m) => ({
                value: m.id,
                label: `${m.name} v${m.version} (${t(`models.stageName.${m.stage}`)})`,
              }))}
              aria-label={t('explainQuality.pickModel')}
            />
            <Button icon={<ReloadOutlined />} disabled={!modelId} loading={refresh.isPending} onClick={recompute}>
              {t('explainQuality.refresh')}
            </Button>
          </>
        }
      />

      {!modelId ? (
        <Alert type="info" showIcon message={t('explainQuality.noModels')} />
      ) : (
        <Flex vertical gap={16}>
          <Row gutter={[12, 12]}>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('explainQuality.metric.deletion_auc.label')}
                value={metricValue('deletion_auc')}
                digits={3}
                formula={t('explainQuality.metric.deletion_auc.help')}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('explainQuality.metric.insertion_auc.label')}
                value={metricValue('insertion_auc')}
                digits={3}
                formula={t('explainQuality.metric.insertion_auc.help')}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('explainQuality.metric.window_jaccard.label')}
                value={metricValue('window_jaccard')}
                digits={3}
                formula={t('explainQuality.metric.window_jaccard.help')}
              />
            </Col>
            <Col xs={12} md={6}>
              <KpiTile
                title={t('explainQuality.passRate')}
                value={quality?.narration_audit_pass_rate != null ? quality.narration_audit_pass_rate * 100 : null}
                unit="%"
                digits={1}
                formula={t('explainQuality.passRateHelp')}
              />
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={10}>
              <Card size="small" title={t('models.importance')} style={{ height: '100%' }}>
                <FeatureImportance modelId={modelId} />
              </Card>
            </Col>
            <Col xs={24} lg={14}>
              <Card size="small" title={t('explainQuality.metrics')} style={{ height: '100%' }}>
                <Table<XaiQualityMetric>
                  rowKey="id"
                  size="small"
                  loading={isLoading}
                  columns={metricColumns}
                  dataSource={metrics}
                  pagination={false}
                  scroll={{ x: 640 }}
                  locale={{ emptyText: t('explainQuality.noMetrics') }}
                />
              </Card>
            </Col>
          </Row>

          <Card size="small" title={t('explainQuality.pdp')}>
            <PartialDependence modelId={modelId} outputLabel={outputLabel} />
          </Card>

          <Card
            size="small"
            title={
              <Flex gap={8} align="center">
                <span>{t('explainQuality.audits')}</span>
                {failed.length > 0 && (
                  <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                    {t('explainQuality.failedCount', { count: failed.length })}
                  </Tag>
                )}
              </Flex>
            }
          >
            {quality && !quality.llm_enabled && quality.narration_audit_count === 0 ? (
              <Alert type="info" showIcon message={t('explainQuality.llmOff')} description={t('explainQuality.llmOffDetail')} />
            ) : (
              <>
                <Table<NarrationAuditRow>
                  rowKey={(r) => r.audit.id}
                  size="small"
                  loading={auditsLoading}
                  columns={auditColumns}
                  dataSource={audits ?? []}
                  pagination={{ pageSize: 20, showSizeChanger: false }}
                  rowClassName={(r) => (r.audit.passed ? '' : 'row-audit-failed')}
                  locale={{ emptyText: t('explainQuality.noAudits') }}
                />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {t('explainQuality.auditNote')}
                </Typography.Text>
              </>
            )}
          </Card>
        </Flex>
      )}
    </>
  );
}
