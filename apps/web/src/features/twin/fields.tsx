import { Select, type SelectProps } from 'antd';
import { useTranslation } from 'react-i18next';

import { ASSET_TYPES, type AssetType } from '../../api/types';
import { useLines } from '../../hooks/useAssets';

export const ASSET_CODE_PATTERN = /^[a-z0-9][a-z0-9-]{1,48}$/;

export function LineSelect(props: SelectProps<string>) {
  const { t } = useTranslation();
  const lines = useLines();
  return (
    <Select<string>
      {...props}
      showSearch
      optionFilterProp="label"
      loading={lines.isPending}
      status={lines.isError ? 'error' : undefined}
      placeholder={lines.isError ? t('errors.loadFailed') : t('twin.form.linePlaceholder')}
      options={lines.data?.items.map((line) => ({ value: line.id, label: `${line.code} — ${line.name}` }))}
    />
  );
}

export function AssetTypeSelect(props: SelectProps<AssetType>) {
  const { t } = useTranslation();
  return (
    <Select<AssetType>
      {...props}
      options={ASSET_TYPES.map((type) => ({ value: type, label: t(`assetType.${type}`) }))}
    />
  );
}
