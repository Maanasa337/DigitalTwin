import { Descriptions, Flex, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

import type { AasElement } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';

interface LangString {
  language: string;
  text: string;
}

function isElement(value: unknown): value is AasElement {
  return typeof value === 'object' && value !== null && typeof (value as AasElement).modelType === 'string';
}

function isLangString(value: unknown): value is LangString {
  return typeof value === 'object' && value !== null && typeof (value as LangString).text === 'string';
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function ElementValue({ element }: { element: AasElement }) {
  switch (element.modelType) {
    case 'Property':
      return (
        <Typography.Text className="tabular">
          {element.value === undefined || element.value === null || element.value === '' ? '—' : String(element.value)}
        </Typography.Text>
      );
    case 'MultiLanguageProperty':
      return (
        <Flex vertical gap={4}>
          {asArray(element.value)
            .filter(isLangString)
            .map((entry) => (
              <span key={entry.language}>
                <Tag bordered={false} style={{ marginInlineEnd: 6 }}>
                  {entry.language}
                </Tag>
                {entry.text}
              </span>
            ))}
        </Flex>
      );
    case 'SubmodelElementCollection':
    case 'SubmodelElementList':
      return <ElementList elements={asArray(element.value).filter(isElement)} />;
    default:
      return (
        <pre className="json-view" style={{ maxHeight: 240, padding: 8 }}>
          {JSON.stringify(element, null, 2)}
        </pre>
      );
  }
}

export function ElementList({ elements }: { elements: AasElement[] }) {
  const { t } = useTranslation();
  if (elements.length === 0) return <Typography.Text type="secondary">{t('twin.aas.emptyCollection')}</Typography.Text>;
  return (
    <Descriptions
      bordered
      size="small"
      column={1}
      styles={{ label: { width: '30%', minWidth: 120, verticalAlign: 'top' } }}
      items={elements.map((element, index) => ({
        key: `${element.idShort ?? ''}-${index}`,
        label: element.idShort ?? `#${index + 1}`,
        children: <ElementValue element={element} />,
      }))}
    />
  );
}

export function SubmodelView({ elements }: { elements: AasElement[] | undefined }) {
  const { t } = useTranslation();
  if (!elements?.length) return <EmptyState description={t('twin.aas.emptySubmodel')} />;
  return <ElementList elements={elements} />;
}
