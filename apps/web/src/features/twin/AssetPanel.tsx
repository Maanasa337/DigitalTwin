import { CopyOutlined, DeleteOutlined, DownloadOutlined, SendOutlined } from '@ant-design/icons';
import { Button, Card, Popconfirm, Tabs } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { downloadAasx } from '../../api/assets';
import { SUBMODEL_IDS, type Asset, type TreeAsset } from '../../api/types';
import { useAuth } from '../../app/authContext';
import { PageHeader } from '../../components/PageHeader';
import { StatusTag } from '../../components/StatusTag';
import { useApiError } from '../../hooks/useApiError';
import { useAas, useAssetDocument, useRetireAsset } from '../../hooks/useAssets';
import { downloadBlob, downloadJson } from '../../lib/download';
import { CloneAssetModal } from './CloneAssetModal';
import { CommandModal } from './CommandModal';
import { ComponentsSensorsTab } from './ComponentsSensorsTab';
import { FidelityBadge } from './FidelityBadge';
import { JsonDocument } from './JsonDocument';
import { LiveTwinTab } from './LiveTwinTab';
import { QueryView } from './QueryView';
import { SubmodelView } from './SubmodelView';

type Dialog = 'clone' | 'command' | null;

function AasSubmodelTab({ assetId, idShort }: { assetId: string; idShort: string }) {
  const aas = useAas(assetId);
  return (
    <QueryView query={aas}>
      {(env) => <SubmodelView elements={env.submodels.find((s) => s.idShort === idShort)?.submodelElements} />}
    </QueryView>
  );
}

function RawAasTab({ asset }: { asset: TreeAsset }) {
  const aas = useAas(asset.id);
  return <QueryView query={aas}>{(env) => <JsonDocument data={env} filename={`${asset.code}.aas.json`} />}</QueryView>;
}

function DocumentTab({ asset, kind }: { asset: TreeAsset; kind: 'dtdl' | 'ngsi-ld' }) {
  const doc = useAssetDocument(asset.id, kind);
  return <QueryView query={doc}>{(data) => <JsonDocument data={data} filename={`${asset.code}.${kind}.json`} />}</QueryView>;
}

function ExportButtons({ asset }: { asset: TreeAsset }) {
  const { t } = useTranslation();
  const aas = useAas(asset.id);
  const onError = useApiError();
  const [downloading, setDownloading] = useState(false);

  const exportAasx = async () => {
    setDownloading(true);
    try {
      downloadBlob(await downloadAasx(asset.id), `${asset.code}.aasx`);
    } catch (err) {
      onError(err);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      <Button icon={<DownloadOutlined />} loading={downloading} onClick={() => void exportAasx()}>
        {t('twin.actions.exportAasx')}
      </Button>
      <Button
        icon={<DownloadOutlined />}
        disabled={!aas.data}
        onClick={() => aas.data && downloadJson(aas.data, `${asset.code}.aas.json`)}
      >
        {t('twin.actions.exportAasJson')}
      </Button>
    </>
  );
}

interface AssetPanelProps {
  asset: TreeAsset;
  onSelect: (code: string | null) => void;
}

export function AssetPanel({ asset, onSelect }: AssetPanelProps) {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canWrite = hasRole('engineer', 'admin');
  const [dialog, setDialog] = useState<Dialog>(null);
  const retire = useRetireAsset();
  const onError = useApiError();

  const onCloned = (created: Asset) => {
    setDialog(null);
    onSelect(created.code);
  };

  const tabs = [
    ...SUBMODEL_IDS.map((id) => ({
      key: id,
      label: id,
      children: <AasSubmodelTab assetId={asset.id} idShort={id} />,
    })),
    { key: 'sensors', label: t('twin.tabs.sensors'), children: <ComponentsSensorsTab assetId={asset.id} /> },
    { key: 'live', label: t('twin.tabs.live'), children: <LiveTwinTab code={asset.code} /> },
    { key: 'raw', label: t('twin.tabs.raw'), children: <RawAasTab asset={asset} /> },
    { key: 'dtdl', label: 'DTDL', children: <DocumentTab asset={asset} kind="dtdl" /> },
    { key: 'ngsi', label: 'NGSI-LD', children: <DocumentTab asset={asset} kind="ngsi-ld" /> },
  ];

  return (
    <Card>
      <PageHeader
        level={2}
        title={asset.name}
        subtitle={asset.code}
        tags={
          <>
            <StatusTag status={asset.status} />
            <FidelityBadge level={asset.fidelity_level} />
          </>
        }
        actions={
          <>
            <ExportButtons asset={asset} />
            {canWrite && (
              <>
                <Button icon={<SendOutlined />} onClick={() => setDialog('command')}>
                  {t('twin.actions.sendCommand')}
                </Button>
                <Button icon={<CopyOutlined />} onClick={() => setDialog('clone')}>
                  {t('twin.actions.clone')}
                </Button>
                <Popconfirm
                  title={t('twin.retire.title', { code: asset.code })}
                  description={t('twin.retire.description')}
                  okText={t('twin.actions.retire')}
                  okButtonProps={{ danger: true, loading: retire.isPending }}
                  cancelText={t('common.cancel')}
                  onConfirm={() => retire.mutateAsync(asset.id).then(() => onSelect(null), onError)}
                >
                  <Button danger icon={<DeleteOutlined />}>
                    {t('twin.actions.retire')}
                  </Button>
                </Popconfirm>
              </>
            )}
          </>
        }
      />
      <Tabs items={tabs} destroyOnHidden />
      {canWrite && (
        <>
          <CloneAssetModal asset={asset} open={dialog === 'clone'} onClose={() => setDialog(null)} onCloned={onCloned} />
          <CommandModal asset={asset} open={dialog === 'command'} onClose={() => setDialog(null)} />
        </>
      )}
    </Card>
  );
}
