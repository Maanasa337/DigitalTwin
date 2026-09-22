import type { ThreeEvent } from '@react-three/fiber';
import type { ReactNode } from 'react';

import { healthMaterial } from './healthMaterial';
import { useMachine, type Vec3 } from './machineContext';

interface PartProps {
  /** Component code from the asset type's YAML (e.g. `spindle`); omit for structural meshes. */
  code?: string;
  position?: Vec3;
  rotation?: Vec3;
  /** A single three.js geometry element, e.g. `<boxGeometry args={[1, 1, 1]} />`. */
  children: ReactNode;
}

const HOVER_GLOW = 0.45;

/**
 * One mesh of a procedural machine. A mesh with a `code` is named after that component, coloured by
 * its health band and reports hover; one without is plain housing.
 */
export function Part({ code, position, rotation, children }: PartProps) {
  const { health, housing, hovered, onHover } = useMachine();

  if (!code) {
    return (
      <mesh position={position} rotation={rotation}>
        {children}
        <meshStandardMaterial color={housing} metalness={0.45} roughness={0.55} />
      </mesh>
    );
  }

  const material = healthMaterial(health[code]);
  const intensity = material.emissiveIntensity + (hovered === code ? HOVER_GLOW : 0);
  const over = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    onHover?.(code, [event.point.x, event.point.y, event.point.z]);
  };

  return (
    <mesh
      name={code}
      position={position}
      rotation={rotation}
      onPointerOver={onHover ? over : undefined}
      onPointerOut={onHover ? () => onHover(null) : undefined}
    >
      {children}
      <meshStandardMaterial
        color={material.color}
        emissive={material.emissive}
        emissiveIntensity={intensity}
        userData={{ baseIntensity: intensity }}
        metalness={0.25}
        roughness={0.5}
      />
    </mesh>
  );
}
