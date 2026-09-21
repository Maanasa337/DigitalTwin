import { Empty, theme, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

import { TimeRangePicker, useTimeRange } from '../../components/TimeRangePicker';

const { Title, Text } = Typography;

/**
 * Telemetry explorer page — multi-sensor time-series chart.
 * Placeholder until ECharts is installed.
 */
export default function Explorer() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { range, setRange } = useTimeRange('1h');

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={4} style={{ margin: 0 }}>
          {t('explorer.title', 'Telemetry Explorer')}
        </Title>
        <TimeRangePicker value={range} onChange={setRange} />
      </div>

      <div
        style={{
          background: token.colorBgContainer,
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadiusLG,
          padding: 32,
          textAlign: 'center',
          minHeight: 400,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Empty
          description={
            <div>
              <div style={{ marginBottom: 8 }}>
                <Text type="secondary">
                  Select sensors from the tree to visualise time-series data.
                </Text>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Multi-line ECharts chart with shared crosshair, zoom, and export. Max 8 series.
              </Text>
            </div>
          }
        />
      </div>
    </div>
  );
}
