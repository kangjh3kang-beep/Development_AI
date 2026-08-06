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
 *   ├ 좌중앙: 측정 rail(top-1/2 left-4 — 콜러 계약: 지도높이 500px 미만 배치 금지. 282px는 기하 충돌점이지 계약이 아님 — MultiMap 주석 참조)
 *   ├ 상중앙: 측정 상태 칩(top-14)
 *   ├ 하단 전폭: cornerDock(bottom-16 left-14~right-3) = 상태 칩(좌) + bottomDockSlot(우,
 *   │   베이스맵 스위처) — 하단 신규 요소는 **이 도크 flow에 합류**(독립 absolute 금지:
 *   │   암묵 예약값이 겹침의 근원이었다. 계약 테스트 SatongMultiMap.bottomDock.test.tsx)
 *   └ 지도 기준(Leaflet): 줌=bottomleft · 출처표기=bottomright — 래퍼 기준 absolute와
 *     좌표계가 다름(완료바 높이만큼 어긋남)에 주의.
 */
/**
 * ★본문 ↔ 지도 오버레이 층위 계약 (2026-08-06 — 사용자 실측 지적의 근원).
 *
 * 종전에 이 파일은 **오버레이끼리의 상대 층위만** 정의했고, 지도 밖 본문과의 층위는
 * 어디에도 계약이 없었다. 그 공백에서 실제 결함이 났다:
 *   · 지도 래퍼(SatongMultiMap 의 wrapperRef)는 `relative` 뿐이라 **스태킹 컨텍스트를
 *     만들지 않는다** → 오버레이 380~500 이 **루트에서** 본문과 경쟁한다.
 *   · 그런데 지도 타일은 `.leaflet-container { isolation:isolate; z-index:0 }`(globals.css)
 *     으로 격리돼 본문 아래로 얌전히 지나간다. **지도는 헤더 밑으로 가는데 지도 위
 *     컨트롤만 헤더 위로 뜨는** 비대칭이 여기서 나온다.
 *   · 그 결과 sticky ContextHeader(종전 z-30)가 스크롤 중 지도 영역에 들어오면
 *     레이어 레일·팝오버·코너 도크에 **가려졌다**. sticky 를 건 목적(집계 SSOT 를 스크롤
 *     중에도 보이게)을 오버레이가 무효화한 셈이다.
 *
 * ★그래서 "지도 위에 떠 있어야 하는 본문"의 층위를 여기서 함께 계약한다 —
 *   오버레이 최대(confirmCard 500) **위**, 앱 셸 크롬(헤더 z-1000) **아래**.
 *   ※ 대안으로 지도 래퍼에 `isolate` 를 넣어 오버레이를 지도 박스에 가두는 방법이 있으나,
 *     그러면 루트의 플로팅 AI 버튼(z-95)이 지도 컨트롤 **위**로 올라와 의도한 서열
 *     (지도 위에서는 지도 컨트롤이 이긴다)이 뒤집힌다. 그래서 본문 쪽을 올린다.
 */
export const SATONG_CONTENT_Z = {
  /** 지도와 화면을 공유하는 sticky 본문(ContextHeader). Tailwind 로는 `z-[600]`. */
  stickyContextHeader: 600,
  /**
   * 앱 워크스페이스 네비 드롭다운(WorkspaceNavBar 플라이아웃). Tailwind 로는 `z-[700]`.
   *
   * ★왜 본문(600)보다 위인가 — **전역 내비게이션은 본문 정보보다 항상 위**여야 한다.
   *   그리고 이 값이 없으면 실제로 뒤집힌다: 종전 드롭다운 z-50 은 ContextHeader 가 z-30
   *   이던 시절엔 이겼지만, 위 stickyContextHeader 를 600 으로 올리는 순간 **네비 메뉴가
   *   본문 카드에 가려 클릭 불가**가 된다(전역 z 스윕이 적발한 신규 역전).
   * ★모바일 네비(MobileSidebarToggle z-[100]/[101])는 앱 헤더(z-[1000]) **안**에 렌더돼
   *   컨텍스트째 1000 으로 올라가므로 이 계약이 필요 없다 — 데스크톱 네비만 헤더 밖 형제라
   *   맨몸으로 경쟁한다. 이 비대칭이 결함의 서식지였다.
   */
  appNavFlyout: 700,
  /**
   * 지도와 화면을 공유하는 모달(백드롭 `fixed inset-0`). Tailwind 로는 `z-[800]`.
   *
   * ★왜 필요한가 — 지도 공존 화면의 모달이 **지도 오버레이·본문 sticky 아래로 깔려 있었다**:
   *   온보딩 위저드 z-50(DashboardHome — **신규 사용자 첫 화면**) · DeskAppraisalModal z-50 ·
   *   LandShareModal z-100(LandScheduleClient·GlobalAddressSearch) · 경매 상세 z-50.
   *   모달을 열었는데 지도 레일·팝오버(380~500)와 ContextHeader(600)가 백드롭을 관통했다.
   * ★네비 플라이아웃(700)보다 위인 이유 — 모달이 열린 동안에는 전역 내비보다 모달이 우선이다
   *   (키보드로 두 개가 동시에 열릴 수 있는 경로가 실재한다: 모달에 포커스 트랩이 없어
   *   Shift+Tab 으로 네비 버튼에 도달하고 onFocus 가 플라이아웃을 연다).
   * ★앱 크롬(헤더 z-1000)은 그대로 모달 위에 남긴다 — 현행 동작이고, 바꾸면 별개 회귀다.
   * ★적용 범위는 **지도와 공존하는 모달**로 한정한다. 저장소 전역 모달 z 는 50/60/70/100/120/1000
   *   여섯 등급으로 흩어져 있고 일괄 조정은 회귀 위험이 커서 여기서 다루지 않는다.
   */
  appModal: 800,
} as const;

export const SATONG_UI_Z = {
  fullscreenButton: 400,
  cornerDock: 410, // 좌하단 코너 도크(상태 칩 + 노후도 범례)
  tileFailure: 420,
  bottomBar: 460, // 선택 현황·완료/전체취소 바(풀스크린 오버레이 모드)
  clickMenu: 470, // 지도 클릭 팝오버(단일 팝오버) + 거리재기 상태 칩 — 확인 카드 아래
  confirmCard: 500,
} as const;
