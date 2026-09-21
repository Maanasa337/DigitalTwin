import { UploadOutlined } from '@ant-design/icons';
import { Button, Form, Modal, Upload, type UploadFile } from 'antd';
import { useTranslation } from 'react-i18next';

import type { Asset, AssetType } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useImportAasx } from '../../hooks/useAssets';
import { AssetTypeSelect, LineSelect } from './fields';

interface FormValues {
  files: UploadFile[];
  line_id: string;
  asset_type: AssetType;
}

interface ImportAasxModalProps {
  open: boolean;
  onClose: () => void;
  onImported: (asset: Asset) => void;
}

export function ImportAasxModal({ open, onClose, onImported }: ImportAasxModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<FormValues>();
  const importAasx = useImportAasx();
  const onError = useApiError();

  const submit = ({ files, line_id, asset_type }: FormValues) => {
    const file = files[0]?.originFileObj;
    if (!file) return;
    importAasx.mutate(
      { file, lineId: line_id, assetType: asset_type },
      {
        onSuccess: (asset) => {
          form.resetFields();
          onImported(asset);
        },
        onError,
      },
    );
  };

  return (
    <Modal
      open={open}
      title={t('twin.actions.importAasx')}
      okText={t('twin.import.submit')}
      cancelText={t('common.cancel')}
      onOk={() => form.submit()}
      onCancel={onClose}
      confirmLoading={importAasx.isPending}
      destroyOnHidden
    >
      <Form<FormValues> form={form} layout="vertical" onFinish={submit}>
        <Form.Item
          name="files"
          label={t('twin.import.file')}
          valuePropName="fileList"
          getValueFromEvent={(e: { fileList: UploadFile[] }) => e.fileList.slice(-1)}
          rules={[{ required: true, type: 'array', min: 1, message: t('twin.import.fileRequired') }]}
        >
          <Upload accept=".aasx" maxCount={1} beforeUpload={() => false}>
            <Button icon={<UploadOutlined />}>{t('twin.import.choose')}</Button>
          </Upload>
        </Form.Item>
        <Form.Item name="line_id" label={t('twin.form.line')} rules={[{ required: true }]}>
          <LineSelect />
        </Form.Item>
        <Form.Item name="asset_type" label={t('twin.form.type')} rules={[{ required: true }]}>
          <AssetTypeSelect />
        </Form.Item>
      </Form>
    </Modal>
  );
}
