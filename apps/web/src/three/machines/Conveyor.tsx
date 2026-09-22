import { Part } from '../Part';

const ALONG_Z: [number, number, number] = [Math.PI / 2, 0, 0];
const LEGS: [number, number][] = [
  [-1.8, -0.35],
  [-1.8, 0.35],
  [1.8, -0.35],
  [1.8, 0.35],
];

/**
 * Belt conveyor with its drive at the +x end. Component codes from
 * apps/simulator/sim/machines/conveyor.yaml: bearing, drive, belt, motor.
 */
export function Conveyor() {
  return (
    <group>
      {/* Legs and end pulleys */}
      {LEGS.map(([x, z]) => (
        <Part key={`${x},${z}`} position={[x, 0.4, z]}>
          <boxGeometry args={[0.1, 0.8, 0.1]} />
        </Part>
      ))}
      <Part position={[-2, 0.88, 0]} rotation={ALONG_Z}>
        <cylinderGeometry args={[0.12, 0.12, 0.9, 20]} />
      </Part>
      <Part position={[2, 0.88, 0]} rotation={ALONG_Z}>
        <cylinderGeometry args={[0.12, 0.12, 0.9, 20]} />
      </Part>
      <Part code="belt" position={[0, 1.0, 0]}>
        <boxGeometry args={[4.0, 0.06, 0.8]} />
      </Part>
      {/* Drive train on the +x pulley: bearing, gearbox (alignment), motor */}
      <Part code="bearing" position={[2, 0.88, 0.52]} rotation={ALONG_Z}>
        <cylinderGeometry args={[0.13, 0.13, 0.12, 20]} />
      </Part>
      <Part code="drive" position={[2, 0.88, 0.78]}>
        <boxGeometry args={[0.34, 0.34, 0.34]} />
      </Part>
      <Part code="motor" position={[2, 0.88, 1.18]} rotation={ALONG_Z}>
        <cylinderGeometry args={[0.19, 0.19, 0.46, 24]} />
      </Part>
    </group>
  );
}
