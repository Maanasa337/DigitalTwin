import { Button, Card, Col, Result, Row, Skeleton } from 'antd';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '../../components/PageHeader';
import { useSimStatus } from '../../hooks/useSimulation';
import { problemMessage, problemStatus } from '../../lib/problem';
import { ExportModal } from './ExportModal';
import { FleetDamageTable } from './FleetDamageTable';
import { InjectFaultCard } from './InjectFaultCard';
import { LiveLog } from './LiveLog';
import { ScenarioControl } from './ScenarioControl';
import { SimStatusTiles } from './SimStatusTiles';
import { TimeScaleControl } from './TimeScaleControl';

export default function SimulationPage() {
  const { t } = useTranslation();
  const status = useSimStatus();

  const header = <PageHeader title={t('sim.title')} subtitle={t('sim.subtitle')} actions={<ExportModal />} />;

  if (status.isPending) {
    return (
      <>
        {header}
        <Skeleton active paragraph={{ rows: 12 }} />
      </>
    );
  }

  if (status.isError && !status.data) {
    const code = problemStatus(status.error);
    const unreachable = code === 502 || code === 503;
    return (
      <>
        {header}
        <Result
          status={unreachable ? 'warning' : 'error'}
          title={unreachable ? t('sim.unreachable') : t('errors.loadFailed')}
          subTitle={problemMessage(status.error, t('errors.generic'))}
          extra={
            <Button type="primary" loading={status.isFetching} onClick={() => void status.refetch()}>
              {t('common.retry')}
            </Button>
          }
        />
      </>
    );
  }

  const data = status.data;
  return (
    <>
      {header}
      <Row gutter={[24, 24]}>
        <Col span={24}>
          <SimStatusTiles status={data} stale={status.isError} />
        </Col>
        <Col xs={24} xl={12}>
          <Card title={t('sim.timeScale.title')} style={{ height: '100%' }}>
            <TimeScaleControl timeScale={data.time_scale} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title={t('sim.scenario.title')} style={{ height: '100%' }}>
            <ScenarioControl current={data.scenario?.code ?? null} />
          </Card>
        </Col>
        <Col span={24}>
          <Card title={t('sim.fleet.title')} styles={{ body: { padding: 0 } }}>
            <FleetDamageTable assets={data.assets} />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <InjectFaultCard assets={data.assets} />
        </Col>
        <Col xs={24} lg={14}>
          <LiveLog entries={data.log} />
        </Col>
      </Row>
    </>
  );
}
