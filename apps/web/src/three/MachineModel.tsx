import type { AssetType } from '../api/types';
import { CncMill } from './machines/CncMill';
import { Compressor } from './machines/Compressor';
import { Conveyor } from './machines/Conveyor';
import { HydraulicPress } from './machines/HydraulicPress';
import { InjectionMoulder } from './machines/InjectionMoulder';
import { useMachine } from './machineContext';
import { Part } from './Part';

/** Approximate top of each model in metres, for placing labels and framing the camera. */
export const MACHINE_HEIGHT: Record<AssetType, number> = {
  cnc_mill: 3.3,
  compressor: 1.45,
  conveyor: 1.1,
  hydraulic_press: 3.25,
  injection_moulder: 1.85,
  other: 1.6,
};

/**
 * Unknown asset types get a plain cabinet with one cube per component on top, so every component
 * still has a mesh to colour and hover.
 */
function GenericMachine() {
  const codes = Object.keys(useMachine().health);
  return (
    <group>
      <Part position={[0, 0.6, 0]}>
        <boxGeometry args={[1.4, 1.2, 1.2]} />
      </Part>
      {codes.map((code, i) => (
        <Part key={code} code={code} position={[(i - (codes.length - 1) / 2) * 0.35, 1.35, 0]}>
          <boxGeometry args={[0.28, 0.28, 0.28]} />
        </Part>
      ))}
    </group>
  );
}

export function MachineModel({ assetType }: { assetType: AssetType }) {
  switch (assetType) {
    case 'cnc_mill':
      return <CncMill />;
    case 'compressor':
      return <Compressor />;
    case 'conveyor':
      return <Conveyor />;
    case 'hydraulic_press':
      return <HydraulicPress />;
    case 'injection_moulder':
      return <InjectionMoulder />;
    default:
      return <GenericMachine />;
  }
}
