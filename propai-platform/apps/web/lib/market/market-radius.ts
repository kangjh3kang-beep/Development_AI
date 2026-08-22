/**
 * 실거래 조회 반경 요청 조립 — **고른 값이 곧 적용값**임을 보장하는 한 곳.
 *
 * ## 왜 공용 함수인가
 *
 * 반경에는 두 모드가 있고 둘을 섞으면 화면이 거짓말을 한다:
 *   · **자동**(`null`) — 1km 로 조회하고, 반경 내 렌더 가능 마커가 희소하면 백엔드가
 *     사다리(1/3/5/10km)로 넓힌다. 넓히면 배너가 **반드시 고지**한다.
 *   · **수동**(숫자) — 사용자가 명시적으로 고른 값. 이때 자동확대를 켜 두면 1km 를 고른
 *     사용자에게 서버가 3km 결과를 주게 되고, **컨트롤이 거짓말이 된다.**
 *
 * 그래서 "수동이면 자동확대를 끈다"를 **호출부마다 손으로 쓰지 않고** 여기 한 곳에 둔다
 * (이 저장소가 반복해 데인 "구현 여러 벌" 을 만들지 않는다).
 */
export type MarketRadiusRequest = {
  radius_m: number;
  auto_expand_radius: boolean;
};

/** 기본 조회 반경(m) — 자동 모드의 출발점이자 수동 미선택 시의 값. */
export const MARKET_RADIUS_DEFAULT_M = 1000;

/**
 * @param manualRadiusM 사용자가 고른 반경(m). `null`/`undefined` 면 자동 모드.
 */
export function marketRadiusRequest(
  manualRadiusM: number | null | undefined,
): MarketRadiusRequest {
  const manual = typeof manualRadiusM === "number" && manualRadiusM > 0;
  return {
    radius_m: manual ? (manualRadiusM as number) : MARKET_RADIUS_DEFAULT_M,
    // ★수동 선택이면 확대하지 않는다 — 고른 값과 적용값이 달라지면 컨트롤이 거짓말이 된다.
    auto_expand_radius: !manual,
  };
}
