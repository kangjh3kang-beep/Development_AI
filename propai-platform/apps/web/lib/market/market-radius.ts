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

/**
 * 반경 컨트롤을 **보여야 하는가**.
 *
 * ## 왜 순수 함수인가
 *
 * 종전 게이트는 `marketPayload && !marketPayload.fetch_failed && marketTypes.length > 0`
 * 이었고, 반경 칩이 그 **안**에 있었다. 그래서 조회가 실패하면 칩도 함께 사라졌다.
 * 반경은 조회를 **다시 시키는** 수단이라 실패했을 때야말로 있어야 하고, 게다가 고른
 * 반경은 부모 상태로 **그대로 남아** 같은 반경으로 계속 실패한다 —
 * **새로고침 말고는 빠져나갈 길이 없었다.**
 *
 * ★이 판정을 JSX 안에 인라인으로 두면 **아무 테스트도 태울 수 없다.** 지도 오버레이는
 *   Leaflet 이 실제로 뜬 뒤에야 그려져서 jsdom 렌더로 닿지 않기 때문이다(그래서 이 지도의
 *   기존 계약 테스트들이 전부 소스 검사다). 판정만 밖으로 꺼내면 **직접** 검증할 수 있다.
 */
export function shouldShowRadiusControl(opts: {
  /** 켜진 실거래 레이어 유형 수(= 사용자가 레이어를 켰는가). */
  marketTypeCount: number;
  /** 반경 변경 핸들러가 있는가(없으면 눌러도 아무 일이 없다). */
  hasRadiusHandler: boolean;
}): boolean {
  // ★응답(payload)을 보지 않는다 — 그것이 이 함수의 요점이다.
  return opts.marketTypeCount > 0 && opts.hasRadiusHandler;
}

/**
 * 응답이 있어야 뜻이 있는 것(유형별 건수·위치 미확인 목록)을 보여야 하는가.
 *
 * 반경 컨트롤과 **다른 조건**이다 — 이 둘을 한 게이트로 묶은 것이 결함의 원인이었다.
 */
export function shouldShowMarketDetails(payload: { fetch_failed?: boolean } | null | undefined): boolean {
  return Boolean(payload) && !payload?.fetch_failed;
}

/** 조회 실패를 사용자에게 알려야 하는가(침묵 금지). */
export function shouldShowFetchFailureNotice(
  payload: { fetch_failed?: boolean } | null | undefined,
): boolean {
  return Boolean(payload?.fetch_failed);
}
