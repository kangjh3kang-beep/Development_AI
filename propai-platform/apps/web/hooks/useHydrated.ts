"use client";

import { useSyncExternalStore } from "react";

/**
 * 클라이언트 **재수화가 끝났는지** 알려준다. 첫 렌더는 서버와 동일하게 `false` 다.
 *
 * ★왜 필요한가(쉬운 말로): `localStorage` 에 저장된 상태(zustand persist 등)는 **서버에 없다.**
 *   그걸 렌더 중에 그대로 쓰면 서버는 `0`, 브라우저는 `1` 을 그려 **하이드레이션 불일치**가 난다.
 *   React 는 그 서브트리를 통째로 버리고 다시 그리며 uncaught error 를 던진다.
 *
 * ★실제 사고(2026-08-13): `LifecycleProgressRail` 의 진행도 배지가 서버 `0` / 클라 `1` 이라
 *   `/projects/[id]/site-analysis` 에서 매번 하이드레이션 오류가 났다. 증상은 엉뚱한 곳에서
 *   드러났다 — 3D 스모크 e2e 의 "무크래시" 단언이 붉었고, 원인이 3D 와 무관해 진단이 늦었다.
 *
 * ★쓰는 법: 저장소에서 파생한 값을 **`hydrated` 가 true 일 때만** 렌더에 쓴다.
 *   그러면 서버와 클라 첫 렌더가 같은 것을 그리고, 그다음 프레임에 실제 값으로 채워진다.
 *
 *     const hydrated = useHydrated();
 *     const count = hydrated ? completedCount : 0;
 *
 * ★`suppressHydrationWarning` 은 대안이 아니다 — 경고만 지우고 **불일치는 그대로**라
 *   서브트리 재생성 비용과 깜빡임이 남는다.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * ★★2026-08-26 정정 — **"persist 파생값을 렌더에 쓰면 위험" 은 너무 넓다.**
 *
 * 위 문장을 그대로 믿고 `#850` 이 **결함이 아닌 것**을 고쳤고, 배포 후 예측(오류 0)이 **반증**됐다.
 * 실측한 계약은 이렇다:
 *
 *   zustand v5 의 `useStore` 는
 *     `useSyncExternalStore(api.subscribe, api.getState, **api.getInitialState**)`
 *   로 붙는다. React 는 **클라이언트 하이드레이션 렌더에서도 세 번째 인자(서버 스냅샷)** 를 쓴다.
 *   → **셀렉터로만 읽는 persist 소비(`useXStore((s) => s.foo)`)는 원리적으로 불일치를 못 만든다.**
 *      (그 전제 자체를 `lib/hydration/__tests__/zustand-server-snapshot.contract.test.tsx` 가 잠근다.)
 *
 * 위험한 것은 **그 스냅샷을 우회하는 읽기** 셋이다:
 *   ① `useXStore.getState()` 를 **렌더 중** 호출 — `useState` 지연 초기값·`useMemo` 포함
 *   ② 스토어가 노출한 **메서드**(`stageCompletion()`·`getNextRecommendedStage()` …)를 렌더 중 호출
 *      — 내부에서 `get()`(라이브 상태)을 읽는다. **2026-08-13 `LifecycleProgressRail` 사고가 이것이다.**
 *   ③ 렌더 중 `localStorage` 직접 읽기
 *
 * 실증(2026-08-26 · 라이브 + 로컬 dev 재현 diff): `GlobalAddressSearch` 의
 * `useState(() => … getState().siteAnalysis?.parcels …)` 가 서버 `[]`(배지 "대기") /
 * 클라 77필지(배지 "77필지")를 그려 `/ko/regulations`·`/ko/permits` 에서 React #418 이 났다.
 *
 * ★분류를 틀리면 처방이 헛돈다. 판정은 눈이 아니라 파서로 —
 *   `lib/hydration/render-path-store-reads.ts` + 그 계약 테스트가 저장소 전수를 감시한다.
 */
export function useHydrated(): boolean {
  // ★`useState`+`useEffect(setState)` 대신 `useSyncExternalStore` 를 쓴다 — React 가 서버/클라
  //   스냅샷을 **명시적으로** 받는 API 라 의도가 드러나고, `react-hooks/set-state-in-effect`
  //   경고도 없다. 구독은 필요 없다(값이 바뀌지 않는다) → no-op 구독을 넘긴다.
  return useSyncExternalStore(
    NO_SUBSCRIBE,
    () => true, // 클라이언트 스냅샷 — 재수화 이후
    () => false, // 서버 스냅샷 — SSR·클라 첫 렌더가 이 값으로 일치한다
  );
}

/** 값이 바뀌지 않으므로 구독하지 않는다(모듈 상수 — 매 렌더 새 함수가 되면 재구독한다). */
const NO_SUBSCRIBE = () => () => {};
