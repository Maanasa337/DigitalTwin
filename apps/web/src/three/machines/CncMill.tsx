import { Part } from '../Part';

/**
 * Vertical machining centre. Component codes from apps/simulator/sim/machines/cnc_mill.yaml:
 * spindle, lube, tool, axis, motor. Units are metres; the base sits on y = 0.
 */
export function CncMill() {
  return (
    <group>
      {/* Bed and column */}
      <Part position={[0, 0.4, 0]}>
        <boxGeometry args={[2.4, 0.8, 1.6]} />
      </Part>
      <Part position={[0, 1.8, -0.5]}>
        <boxGeometry args={[0.8, 2.0, 0.6]} />
      </Part>
      {/* X-axis table on its ball screw */}
      <Part code="axis" position={[0, 0.9, 0.25]}>
        <boxGeometry args={[1.9, 0.18, 0.9]} />
      </Part>
      {/* Spindle head, spindle and cutting tool */}
      <Part code="spindle" position={[0, 2.25, 0.05]}>
        <boxGeometry args={[0.6, 0.6, 0.6]} />
      </Part>
      <Part code="spindle" position={[0, 1.75, 0.15]}>
        <cylinderGeometry args={[0.13, 0.13, 0.45, 24]} />
      </Part>
      <Part code="tool" position={[0, 1.38, 0.15]}>
        <cylinderGeometry args={[0.05, 0.02, 0.3, 16]} />
      </Part>
      {/* Spindle motor on top of the column */}
      <Part code="motor" position={[0, 3.05, -0.4]}>
        <cylinderGeometry args={[0.24, 0.24, 0.5, 24]} />
      </Part>
      {/* Lubrication unit beside the column */}
      <Part code="lube" position={[0.85, 1.15, -0.55]}>
        <boxGeometry args={[0.4, 0.7, 0.4]} />
      </Part>
    </group>
  );
}
