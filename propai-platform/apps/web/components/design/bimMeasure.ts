/**
 * §4-E BIM 3D 측정도구 순수 코어 — 두 점 사이 거리·중점·표기(결정론).
 *
 * 3D 뷰어(R3F)에서 분리해 단위 테스트 가능하게 한다. 픽킹(raycast)·렌더는 컴포넌트가, 거리/표기
 * 계산은 본 모듈이 담당한다. 좌표 단위는 m(씬 좌표).
 */

export type Vec3 = { x: number; y: number; z: number };

/** 두 점의 3D 유클리드 거리(m). */
export function distance3D(a: Vec3, b: Vec3): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

/** 두 점의 중점(거리 라벨 배치용). */
export function midpoint3D(a: Vec3, b: Vec3): Vec3 {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2 };
}

/** 길이(m) 표기 — 1m 이상은 소수 2자리 m, 1m 미만은 정수 mm. 무효값은 '—'(가짜 금지). */
export function formatLength(m: number): string {
  if (!Number.isFinite(m) || m < 0) return "—";
  if (m < 1) return `${Math.round(m * 1000)} mm`;
  return `${m.toFixed(2)} m`;
}
