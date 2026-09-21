import { ApartmentOutlined, ImportOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Card, Col, Row } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import type { Asset } from '../../api/types';
import { useAuth } from '../../app/authContext';
import { EmptyState } from '../../components/EmptyState';
import { PageHeader } from '../../components/PageHeader';
import { useTwinTree } from '../../hooks/useTwin';
import { AssetPanel } from './AssetPanel';
import { ImportAasxModal } from './ImportAasxModal';
import { NewAssetDrawer } from './NewAssetDrawer';
import { QueryView } from './QueryView';
import { findAsset } from './treeData';
import { TwinTree } from './TwinTree';

export default function TwinPage() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canWrite = hasRole('engineer', 'admin');
  const tree = useTwinTree();
  const [params, setParams] = useSearchParams();
  const selectedCode = params.get('asset');
  const [dialog, setDialog] = useState<'new' | 'import' | null>(null);

  const select = (code: string | null) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (code) next.set('asset', code);
      else next.delete('asset');
      return next;
    });

  const onCreated = (asset: Asset) => {
    setDialog(null);
    select(asset.code);
  };

  const createActions = canWrite && (
    <>
      <Button type="primary" icon={<PlusOutlined />} onClick={() => setDialog('new')}>
        {t('twin.actions.newAsset')}
      </Button>
      <Button icon={<ImportOutlined />} onClick={() => setDialog('import')}>
        {t('twin.actions.importAasx')}
      </Button>
    </>
  );

  return (
    <>
      <PageHeader title={t('twin.title')} subtitle={t('twin.subtitle')} actions={createActions} />
      <QueryView query={tree} rows={10}>
        {(data) => {
          if (data.plants.length === 0) {
            return (
              <Card>
                <EmptyState icon={<ApartmentOutlined />} description={t('twin.empty.noAssets')} action={createActions} />
              </Card>
            );
          }
          const asset = findAsset(data, selectedCode);
          return (
            <Row gutter={[24, 24]} align="top">
              <Col xs={24} lg={9} xxl={7}>
                <Card styles={{ body: { padding: 16 } }}>
                  <TwinTree tree={data} selectedCode={asset ? asset.code : null} onSelect={select} />
                </Card>
              </Col>
              <Col xs={24} lg={15} xxl={17}>
                {asset ? (
                  <AssetPanel key={asset.code} asset={asset} onSelect={select} />
                ) : (
                  <Card>
                    <EmptyState
                      description={selectedCode ? t('twin.empty.notFound', { code: selectedCode }) : t('twin.empty.noSelection')}
                    />
                  </Card>
                )}
              </Col>
            </Row>
          );
        }}
      </QueryView>
      {canWrite && (
        <>
          <NewAssetDrawer open={dialog === 'new'} onClose={() => setDialog(null)} onCreated={onCreated} />
          <ImportAasxModal open={dialog === 'import'} onClose={() => setDialog(null)} onImported={onCreated} />
        </>
      )}
    </>
  );
}
