import { Part } from '../Part';

const ALONG_X: [number, number, number] = [0, 0, Math.PI / 2];

/**
 * Screw compressor on a skid. Component codes from apps/simulator/sim/machines/compressor.yaml:
 * bearing, airend, valve, filter, motor.
 */
export function Compressor() {
  return (
    <group>
      {/* Skid and receiver tank */}
      <Part position={[0, 0.1, 0]}>
        <boxGeometry args={[2.6, 0.2, 1.4]} />
      </Part>
      <Part position={[0, 0.55, -0.95]} rotation={ALONG_X}>
        <cylinderGeometry args={[0.35, 0.35, 2.2, 24]} />
      </Part>
      {/* Drive motor → air-end bearing → air-end */}
      <Part code="motor" position={[-0.75, 0.65, 0.1]} rotation={ALONG_X}>
        <cylinderGeometry args={[0.36, 0.36, 0.9, 24]} />
      </Part>
      <Part code="bearing" position={[-0.18, 0.65, 0.1]} rotation={ALONG_X}>
        <cylinderGeometry args={[0.22, 0.22, 0.2, 24]} />
      </Part>
      <Part code="airend" position={[0.35, 0.7, 0.1]}>
        <boxGeometry args={[0.75, 0.75, 0.75]} />
      </Part>
      {/* Inlet valve on the air-end, intake filter at the end */}
      <Part code="valve" position={[0.35, 1.25, 0.1]}>
        <cylinderGeometry args={[0.09, 0.09, 0.35, 16]} />
      </Part>
      <Part code="filter" position={[1.0, 0.8, 0.35]}>
        <cylinderGeometry args={[0.2, 0.2, 0.45, 24]} />
      </Part>
    </group>
  );
}
