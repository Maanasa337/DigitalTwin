import { Form, Input, Modal } from 'antd';
import { useTranslation } from 'react-i18next';

import type { Asset, AssetClone, TreeAsset } from '../../api/types';
import { useApiError } from '../../hooks/useApiError';
import { useCloneAsset } from '../../hooks/useAssets';
import { ASSET_CODE_PATTERN } from './fields';

interface CloneAssetModalProps {
  asset: TreeAsset;
  open: boolean;
  onClose: () => void;
  onCloned: (asset: Asset) => void;
}

export function CloneAssetModal({ asset, open, onClose, onCloned }: CloneAssetModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<AssetClone>();
  const clone = useCloneAsset(asset.id);
  const onError = useApiError();

  return (
    <Modal
      open={open}
      title={t('twin.clone.title', { code: asset.code })}
      okText={t('twin.actions.clone')}
      cancelText={t('common.cancel')}
      onOk={() => form.submit()}
      onCancel={onClose}
      confirmLoading={clone.isPending}
      destroyOnHidden
    >
      <Form<AssetClone>
        form={form}
        layout="vertical"
        initialValues={{ code: `${asset.code}-copy`.slice(0, 49), name: t('twin.clone.defaultName', { name: asset.name }) }}
        onFinish={(values) => clone.mutate({ ...values, name: values.name.trim() }, { onSuccess: onCloned, onError })}
      >
        <Form.Item
          name="code"
          label={t('twin.form.code')}
          extra={t('twin.form.codeHelp')}
          rules={[{ required: true }, { pattern: ASSET_CODE_PATTERN, message: t('twin.form.codeInvalid') }]}
        >
          <Input autoComplete="off" />
        </Form.Item>
        <Form.Item name="name" label={t('twin.form.name')} rules={[{ required: true, whitespace: true }]}>
          <Input />
        </Form.Item>
      </Form>
    </Modal>
  );
}
