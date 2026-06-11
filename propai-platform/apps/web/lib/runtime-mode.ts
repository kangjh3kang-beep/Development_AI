/* ── 런타임 모드(mock/live) 판정식 SSOT ──
   배경: api-client는 `NEXT_PUBLIC_USE_MOCKS === "true"`일 때만 mock으로 동작하는 반면,
   페이지들은 `=== "false"`(미설정 시 mock 라벨)로 정반대 해석을 해 라벨과 실제 동작이
   모순됐다. 판정식은 이 파일 한 곳에서만 정의하고 전 소비처가 이를 사용한다.
   제약: NEXT_PUBLIC_* 변수는 빌드 시 리터럴 치환되므로 동적 키 접근 없이
   `process.env.NEXT_PUBLIC_USE_MOCKS`를 직접 참조해야 한다. */

export type RuntimeMode = "mock" | "live";

/** mock 모드 여부 — "true"일 때만 mock. 미설정·그 외 값은 전부 live(api-client 동작과 일치). */
export function isMockMode(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCKS === "true";
}

/** 현재 런타임 모드 — mock 게이트 판정식의 단일 출처. */
export function runtimeMode(): RuntimeMode {
  return isMockMode() ? "mock" : "live";
}
