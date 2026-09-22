import { Part } from '../Part';

const COLUMNS: [number, number][] = [
  [-0.6, -0.4],
  [-0.6, 0.4],
  [0.6, -0.4],
  [0.6, 0.4],
];

/**
 * Four-column press with its power unit alongside. Component codes from
 * apps/simulator/sim/machines/hydraulic_press.yaml: pump, seal, oil, valve, motor, ram.
 */
export function HydraulicPress() {
  return (
    <group>
      {/* Bolster, columns and crown */}
      <Part position={[0, 0.25, 0]}>
        <boxGeometry args={[1.6, 0.5, 1.2]} />
      </Part>
      {COLUMNS.map(([x, z]) => (
        <Part key={`${x},${z}`} position={[x, 1.65, z]}>
          <cylinderGeometry args={[0.08, 0.08, 2.3, 16]} />
        </Part>
      ))}
      <Part position={[0, 3.0, 0]}>
        <boxGeometry args={[1.6, 0.45, 1.2]} />
      </Part>
      {/* Cylinder seal under the crown, ram (slide) below it */}
      <Part code="seal" position={[0, 2.68, 0]}>
        <cylinderGeometry args={[0.28, 0.28, 0.14, 24]} />
      </Part>
      <Part code="ram" position={[0, 2.05, 0]}>
        <boxGeometry args={[1.05, 0.5, 0.85]} />
      </Part>
      {/* Power unit: oil tank, pump, motor, directional valve */}
      <Part code="oil" position={[1.45, 0.35, 0]}>
        <boxGeometry args={[0.8, 0.7, 0.8]} />
      </Part>
      <Part code="pump" position={[1.3, 0.9, -0.2]}>
        <cylinderGeometry args={[0.14, 0.14, 0.4, 20]} />
      </Part>
      <Part code="motor" position={[1.3, 0.95, 0.2]}>
        <cylinderGeometry args={[0.19, 0.19, 0.5, 24]} />
      </Part>
      <Part code="valve" position={[1.65, 0.85, 0]}>
        <boxGeometry args={[0.2, 0.22, 0.3]} />
      </Part>
    </group>
  );
}
