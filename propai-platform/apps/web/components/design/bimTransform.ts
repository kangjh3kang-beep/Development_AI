/**
 * §4-D 3D 요소 이동/회전(gizmo) 순수 코어 — 변환모드 순환·각도/위치 표기(결정론).
 *
 * 3D 뷰어(R3F)에서 분리해 단위 테스트 가능하게 한다. 픽킹(raycast)·gizmo 드래그·카메라 잠금은
 * 컴포넌트가, 모드 전환·표기 계산은 본 모듈이 담당한다. 좌표 단위는 m(씬 좌표).
 *
 * 정직: 이동/회전은 뷰포트 상의 시점 편집(설계·IFC에 저장되지 않음). 사용자에겐 "원위치"로 복귀
 * 가능함을 함께 안내한다. 평면 배치 의미상 위치는 X·Z, 회전은 수직축(Y)만 표기한다.
 */

export type Vec3 = { x: number; y: number; z: number };

/** gizmo 변환 모드 — 이동(translate)·회전(rotate). */
export type TransformMode = "translate" | "rotate";

/** 모드 토글 — 이동↔회전 순환. */
export function cycleTransformMode(m: TransformMode): TransformMode {
  return m === "translate" ? "rotate" : "translate";
}

/** 라디안→도(°). */
export function radToDeg(rad: number): number {
  return (rad * 180) / Math.PI;
}

/** 각도(라디안) 표기 — 정수 도(°). 무효값은 '—'(가짜 금지). */
export function formatAngleDeg(rad: number): string {
  if (!Number.isFinite(rad)) return "—";
  // -0° 방지: 반올림 후 0이면 부호 제거
  const deg = Math.round(radToDeg(rad));
  return `${deg === 0 ? 0 : deg}°`;
}

/** 평면 위치(X·Z) 표기 — 소수 1자리 m. 무효 좌표는 '—'. */
export function formatPositionM(v: Vec3): string {
  if (!Number.isFinite(v.x) || !Number.isFinite(v.z)) return "—";
  const x = (v.x === 0 ? 0 : v.x).toFixed(1);
  const z = (v.z === 0 ? 0 : v.z).toFixed(1);
  return `X ${x} · Z ${z} m`;
}

/** 이동(위치 X·Z) + 회전(수직축) 한 줄 표기 — 비전문가 readout. 회전 무효면 위치만. */
export function transformReadout(v: Vec3, rotationYRad: number): string {
  const pos = formatPositionM(v);
  if (pos === "—") return "—";
  if (!Number.isFinite(rotationYRad)) return pos;
  return `${pos} · 회전 ${formatAngleDeg(rotationYRad)}`;
}
