/** Shared rig: soft hemisphere fill plus one key light, no shadows (keeps the demand loop cheap). */
export function SceneLights() {
  return (
    <>
      <hemisphereLight args={['#ffffff', '#30363d', 0.9]} />
      <directionalLight position={[6, 10, 6]} intensity={1.4} />
      <directionalLight position={[-6, 4, -4]} intensity={0.4} />
    </>
  );
}
