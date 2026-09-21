import { LogoutOutlined, MenuOutlined, MoonOutlined, SunOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Dropdown, Flex, Segmented, Tag, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

import { useMe } from '../hooks/useMe';
import { useNow } from '../hooks/useNow';
import { STATUS_PALETTE, type StatusLevel } from '../lib/status';
import { useUiStore, type Language } from '../store/uiStore';
import { useAuth } from './authContext';
import { useWsStatus } from './wsContext';

const HEARTBEAT_FRESH_MS = 45_000;

function WsIndicator({ compact }: { compact: boolean }) {
  const { t } = useTranslation();
  const { status, lastHeartbeat } = useWsStatus();
  const now = useNow(5_000);
  const fresh = status === 'open' && lastHeartbeat !== null && now - lastHeartbeat < HEARTBEAT_FRESH_MS;
  const state: { level: StatusLevel; key: string } = fresh
    ? { level: 'good', key: 'live' }
    : status === 'closed'
      ? { level: 'critical', key: 'offline' }
      : { level: 'warning', key: status === 'open' ? 'stale' : 'connecting' };
  const { color, Icon } = STATUS_PALETTE[state.level];
  const label = t(`ws.${state.key}`);

  return (
    <Tooltip title={t('ws.tooltip', { status: label })}>
      <Flex align="center" gap={6} role="status" aria-label={t('ws.tooltip', { status: label })}>
        <Icon aria-hidden style={{ color }} />
        {!compact && <Typography.Text type="secondary">{label}</Typography.Text>}
      </Flex>
    </Tooltip>
  );
}

function UserMenu({ compact }: { compact: boolean }) {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const me = useMe();
  const name = me.data?.display_name || user.name || user.sub;

  return (
    <Dropdown
      trigger={['click']}
      menu={{
        items: [
          {
            key: 'info',
            disabled: true,
            label: (
              <Flex vertical gap={4} style={{ cursor: 'default' }}>
                <Typography.Text strong>{name}</Typography.Text>
                {user.email && <Typography.Text type="secondary">{user.email}</Typography.Text>}
                <Flex wrap gap={4}>
                  {user.roles.map((role) => (
                    <Tag key={role} style={{ marginInlineEnd: 0 }}>
                      {t(`roles.${role}`)}
                    </Tag>
                  ))}
                </Flex>
              </Flex>
            ),
          },
          { type: 'divider' },
          { key: 'logout', icon: <LogoutOutlined />, label: t('topbar.logout'), onClick: logout },
        ],
      }}
    >
      <Button type="text" icon={<UserOutlined />} aria-label={t('topbar.userMenu')}>
        {!compact && name}
      </Button>
    </Dropdown>
  );
}

export function TopBar({ showNavToggle, compact }: { showNavToggle: boolean; compact: boolean }) {
  const { t, i18n } = useTranslation();
  const { themeMode, toggleTheme, toggleNav, setLanguage, language } = useUiStore();

  const changeLanguage = (value: Language) => {
    setLanguage(value);
    void i18n.changeLanguage(value);
  };

  return (
    <Flex align="center" justify="space-between" gap={8} style={{ height: '100%' }}>
      <Flex align="center" gap={8}>
        {showNavToggle && (
          <Button type="text" icon={<MenuOutlined />} onClick={toggleNav} aria-label={t('topbar.toggleNav')} />
        )}
        <Typography.Text strong style={{ fontSize: 16 }}>
          TwinVoice
        </Typography.Text>
      </Flex>
      <Flex align="center" gap={compact ? 4 : 12}>
        <WsIndicator compact={compact} />
        <Segmented<Language>
          size="small"
          value={language}
          onChange={changeLanguage}
          options={[
            { value: 'en', label: 'EN' },
            { value: 'hi', label: 'हि' },
          ]}
          aria-label={t('topbar.language')}
        />
        <Tooltip title={t(themeMode === 'dark' ? 'topbar.lightTheme' : 'topbar.darkTheme')}>
          <Button
            type="text"
            icon={themeMode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
            onClick={toggleTheme}
            aria-label={t(themeMode === 'dark' ? 'topbar.lightTheme' : 'topbar.darkTheme')}
          />
        </Tooltip>
        <UserMenu compact={compact} />
      </Flex>
    </Flex>
  );
}
