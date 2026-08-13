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
