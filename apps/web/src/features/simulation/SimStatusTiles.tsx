import { Alert, Card, Col, Flex, Row, Tag, Typography } from 'antd';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { SimStatus } from '../../api/types';
import { formatDateTime, formatDuration, formatNumber, formatRelative } from '../../lib/format';
import { STATUS_PALETTE } from '../../lib/status';

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Card size="small" style={{ height: '100%' }}>
      <Flex vertical gap={4}>
        <Typography.Text type="secondary">{label}</Typography.Text>
        <div className="tabular" style={{ fontSize: 20, fontWeight: 600 }}>
          {children}
        </div>
      </Flex>
    </Card>
  );
}

export function SimStatusTiles({ status, stale }: { status: SimStatus; stale: boolean }) {
  const { t } = useTranslation();
  const running = status.running ? STATUS_PALETTE.good : STATUS_PALETTE.neutral;

  return (
    <Flex vertical gap={12}>
      {stale && <Alert type="warning" showIcon message={t('sim.stale')} />}
      <Row gutter={[16, 16]}>
        <Col xs={12} lg={6}>
          <Tile label={t('sim.tiles.clock')}>{formatDateTime(status.sim_time)}</Tile>
        </Col>
        <Col xs={12} lg={6}>
          <Tile label={t('sim.tiles.elapsed')}>{formatDuration(status.sim_elapsed_s)}</Tile>
        </Col>
        <Col xs={12} lg={6}>
          <Tile label={t('sim.tiles.running')}>
            <Flex align="center" gap={8}>
              <running.Icon aria-hidden style={{ color: running.color }} />
              {status.running ? t('sim.running') : t('sim.paused')}
              <Typography.Text type="secondary" style={{ fontSize: 14, fontWeight: 400 }}>
                {formatNumber(status.time_scale, 0)}×
              </Typography.Text>
            </Flex>
          </Tile>
        </Col>
        <Col xs={12} lg={6}>
          <Tile label={t('sim.tiles.scenario')}>
            {status.scenario ? (
              <Flex vertical gap={0}>
                <Tag style={{ alignSelf: 'flex-start', fontSize: 14 }}>{status.scenario.code}</Tag>
                <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                  {t('sim.startedAt', { time: formatRelative(status.scenario.started_at) })}
                </Typography.Text>
              </Flex>
            ) : (
              <Typography.Text type="secondary">{t('sim.noScenario')}</Typography.Text>
            )}
          </Tile>
        </Col>
      </Row>
    </Flex>
  );
}
