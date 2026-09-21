import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { AasElement } from '../../api/types';
import { SubmodelView } from './SubmodelView';

const elements: AasElement[] = [
  { modelType: 'Property', idShort: 'SerialNumber', valueType: 'xs:string', value: 'SN-4711' },
  {
    modelType: 'MultiLanguageProperty',
    idShort: 'ManufacturerName',
    value: [
      { language: 'en', text: 'Acme Machines' },
      { language: 'de', text: 'Acme Maschinen' },
    ],
  },
  {
    modelType: 'SubmodelElementCollection',
    idShort: 'ContactInformation',
    value: [
      { modelType: 'Property', idShort: 'City', valueType: 'xs:string', value: 'Pune' },
      {
        modelType: 'SubmodelElementList',
        idShort: 'Phones',
        value: [{ modelType: 'Property', valueType: 'xs:string', value: '+91 20 1234' }],
      },
    ],
  },
  { modelType: 'File', idShort: 'Manual', contentType: 'application/pdf', value: 'manual.pdf' },
];

describe('SubmodelView', () => {
  it('renders properties, multi-language values and nested collections', () => {
    render(<SubmodelView elements={elements} />);

    expect(screen.getByText('SerialNumber')).toBeInTheDocument();
    expect(screen.getByText('SN-4711')).toBeInTheDocument();

    expect(screen.getByText('ManufacturerName')).toBeInTheDocument();
    expect(screen.getByText('Acme Machines')).toBeInTheDocument();
    expect(screen.getByText('Acme Maschinen')).toBeInTheDocument();
    expect(screen.getByText('de')).toBeInTheDocument();

    const city = screen.getByText('City');
    expect(city.closest('.ant-descriptions')?.parentElement?.closest('.ant-descriptions')).not.toBeNull();
    expect(screen.getByText('Pune')).toBeInTheDocument();
    expect(screen.getByText('Phones')).toBeInTheDocument();
    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('+91 20 1234')).toBeInTheDocument();
  });

  it('shows unknown model types as JSON', () => {
    render(<SubmodelView elements={elements} />);
    expect(screen.getByText(/"contentType": "application\/pdf"/)).toBeInTheDocument();
  });

  it('shows an empty state when the submodel has no elements', () => {
    render(<SubmodelView elements={undefined} />);
    expect(screen.getByText('This submodel has no data yet')).toBeInTheDocument();
  });
});
