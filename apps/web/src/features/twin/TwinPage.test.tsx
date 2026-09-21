import { AxiosError } from 'axios';
import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as assetsApi from '../../api/assets';
import * as twinApi from '../../api/twin';
import type { AasEnvironment, TwinTree } from '../../api/types';
import { renderWithProviders } from '../../test/renderWithProviders';
import TwinPage from './TwinPage';

vi.mock('../../api/twin');
vi.mock('../../api/assets');

const tree: TwinTree = {
  plants: [
    {
      id: 'p1',
      code: 'pune',
      name: 'Pune plant',
      health: null,
      lines: [
        {
          id: 'l1',
          code: 'line-a',
          name: 'Line A',
          health: null,
          assets: [
            {
              id: 'a1',
              code: 'cnc-01',
              name: 'CNC mill 1',
              asset_type: 'cnc_mill',
              status: 'RUNNING',
              fidelity_level: 3,
              health: null,
              components: [],
            },
          ],
        },
      ],
    },
  ],
};

const aas: AasEnvironment = {
  assetAdministrationShells: [],
  conceptDescriptions: [],
  submodels: [
    {
      idShort: 'Nameplate',
      id: 'urn:nameplate',
      submodelElements: [{ modelType: 'Property', idShort: 'SerialNumber', valueType: 'xs:string', value: 'SN-1' }],
    },
  ],
};

describe('TwinPage', () => {
  beforeEach(() => {
    vi.mocked(twinApi.getTwinTree).mockResolvedValue(tree);
    vi.mocked(assetsApi.getAas).mockResolvedValue(aas);
  });

  it('asks for a selection when no asset is in the URL', async () => {
    renderWithProviders(<TwinPage />, { route: '/twin' });
    expect(await screen.findByText('Select an asset in the tree to see its twin')).toBeInTheDocument();
    expect(screen.getByText('CNC mill 1')).toBeInTheDocument();
    expect(screen.getByText('New asset')).toBeInTheDocument();
  });

  it('renders the selected asset with its Nameplate submodel and write actions', async () => {
    renderWithProviders(<TwinPage />, { route: '/twin?asset=cnc-01' });
    expect(await screen.findByText('CNC mill 1', { selector: 'h2' })).toBeInTheDocument();
    expect(screen.getByText('L3 Physics')).toBeInTheDocument();
    expect(await screen.findByText('SN-1')).toBeInTheDocument();
    expect(screen.getByText('Send command')).toBeInTheDocument();
  });

  it('hides write actions for technicians', async () => {
    renderWithProviders(<TwinPage />, { route: '/twin?asset=cnc-01', roles: ['technician'] });
    expect(await screen.findByText('CNC mill 1', { selector: 'h2' })).toBeInTheDocument();
    expect(screen.queryByText('Send command')).not.toBeInTheDocument();
    expect(screen.queryByText('New asset')).not.toBeInTheDocument();
  });

  it('shows an error result with retry when the tree fails to load', async () => {
    vi.mocked(twinApi.getTwinTree).mockRejectedValue(new AxiosError('Network Error'));
    renderWithProviders(<TwinPage />, { route: '/twin' });
    expect(await screen.findByText('Could not load data')).toBeInTheDocument();
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });
});
