import { Part } from '../Part';

const ALONG_X: [number, number, number] = [0, 0, Math.PI / 2];

/**
 * Horizontal injection moulding machine: clamp unit at -x, injection unit at +x. Component codes
 * from apps/simulator/sim/machines/injection_moulder.yaml: barrel, screw, clamp, drive.
 */
export function InjectionMoulder() {
  return (
    <group>
      {/* Machine base and hopper */}
      <Part position={[0, 0.4, 0]}>
        <boxGeometry args={[4.2, 0.8, 1.1]} />
      </Part>
      <Part position={[0.75, 1.62, 0]}>
        <coneGeometry args={[0.25, 0.4, 20, 1, true]} />
      </Part>
      {/* Clamp unit with its platen */}
      <Part code="clamp" position={[-1.35, 1.3, 0]}>
        <boxGeometry args={[1.2, 1.0, 0.95]} />
      </Part>
      <Part position={[-0.65, 1.25, 0]}>
        <boxGeometry args={[0.12, 0.8, 0.8]} />
      </Part>
      {/* Barrel with heater bands, screw housing, drive */}
      <Part code="barrel" position={[0.25, 1.2, 0]} rotation={ALONG_X}>
        <cylinderGeometry args={[0.17, 0.17, 1.6, 24]} />
      </Part>
      <Part code="screw" position={[1.35, 1.2, 0]} rotation={ALONG_X}>
        <cylinderGeometry args={[0.13, 0.13, 0.6, 20]} />
      </Part>
      <Part code="drive" position={[1.85, 1.2, 0]}>
        <boxGeometry args={[0.5, 0.6, 0.7]} />
      </Part>
    </group>
  );
}
