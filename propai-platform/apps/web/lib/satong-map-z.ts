/**
 * 사통맵 z-index 계약(SSOT) — Leaflet 내부 pane와 지도 위 React 오버레이 UI의 층위를 한 곳에서 관리한다.
 *
 * ★배경(왜 한 곳에 모으나): 지도(.leaflet-container)는 globals.css에서
 *   `isolation:isolate; z-index:0` 으로 독립 스택 컨텍스트에 격리된다. 따라서 지도 위(형제)에
 *   놓이는 React 오버레이는 z-index ≥ 1 이면 지도 안 모든 pane(타일·폴리곤·마커·툴팁·팝업)
 *   위에 그려진다 → 상시 라벨(툴팁)이 범례·칩·확인카드를 덮던 문제(S5)를 구조적으로 차단한다.
 *   아래 UI_* 상수는 그 격리를 전제로 '오버레이끼리'의 상대 층위를 정의한다.
 *
 * ★사용 규칙: JSX에서는 `style={{ zIndex: SATONG_UI_Z.* }}` 로 인라인 적용한다.
 *   Tailwind v4 는 `z-[${동적값}]` 같은 런타임 문자열 클래스를 생성하지 못하므로(JIT 미탐지),
 *   상수를 클래스가 아닌 인라인 스타일로 흘려보내 SSOT를 깨지 않는다.
 */

/** Leaflet 기본 pane z-index(참고용 — 격리 전제이므로 UI 비교엔 쓰지 않는다). */
export const LEAFLET_PANE_Z = {
  tile: 200,
  overlay: 400, // 폴리곤
  shadow: 500,
  marker: 600,
  tooltip: 650,
  popup: 700,
} as const;

/**
 * 커스텀 pane z-index.
 *   label pane 은 폴리곤(overlay=400) 위, 마커(600) 아래에 둔다 —
 *   Hybrid 오버레이 타일(도로·라벨)이 필지 폴리곤 위로 올라오되 마커/툴팁 흐름은 가리지 않게.
 */
export const SATONG_PANE_Z = {
  label: 450,
} as const;

/**
 * 지도 위 React 오버레이(형제) 상대 층위 — 값이 클수록 위.
 *   확인 카드(confirmCard)는 항상 최상위: 사용자 결정(＋추가/제거) 흐름이 어떤 오버레이에도
 *   가려지지 않아야 한다.
 *
 * ★코너 슬롯 레지스트리(x/y — 2026-07-17 겹침 구조 진단의 처방②):
 *   z는 이 레지스트리로 충돌이 사라졌지만 x/y는 각자 absolute 좌표를 고르다 겹침이
 *   3회 재발했다(측정rail↔줌·칩행↔스위처·배너↔완료바). 신규 오버레이는 아래 슬롯
 *   소유권을 확인하고 **빈 슬롯에만** 배치하거나 기존 도크 flow에 합류할 것.
 *   ┌ 좌상: 검색/네비(셸) · 우상: 풀스크린 버튼 + 레이어 레일(right-4 top-20)
 *   ├ 좌중앙: 측정 rail(top-1/2 left-4 — 지도높이<282px 배치 금지, MultiMap 주석 참조)
 *   ├ 상중앙: 측정 상태 칩(top-14)
 *   ├ 하단 전폭: cornerDock(bottom-16 left-14~right-3) = 상태 칩(좌) + bottomDockSlot(우,
 *   │   베이스맵 스위처) — 하단 신규 요소는 **이 도크 flow에 합류**(독립 absolute 금지:
 *   │   암묵 예약값이 겹침의 근원이었다. 계약 테스트 SatongMultiMap.bottomDock.test.tsx)
 *   └ 지도 기준(Leaflet): 줌=bottomleft · 출처표기=bottomright — 래퍼 기준 absolute와
 *     좌표계가 다름(완료바 높이만큼 어긋남)에 주의.
 */
export const SATONG_UI_Z = {
  fullscreenButton: 400,
  cornerDock: 410, // 좌하단 코너 도크(상태 칩 + 노후도 범례)
  tileFailure: 420,
  bottomBar: 460, // 선택 현황·완료/전체취소 바(풀스크린 오버레이 모드)
  clickMenu: 470, // 지도 클릭 팝오버(단일 팝오버) + 거리재기 상태 칩 — 확인 카드 아래
  confirmCard: 500,
} as const;
