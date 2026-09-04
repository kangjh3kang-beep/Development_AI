import { create } from "zustand";
import { persist } from "zustand/middleware";

import { createAccountScopedStorage } from "@/lib/account-scoped-storage";
import type { SatongMapLayerState } from "@/lib/satong-map-layers";

/**
 * 사통맵 **레이어 컨트롤 선호** — 계정별 영속.
 *
 * ## 왜 필요한가 (2026-09-04 · 사용자 요구의 잔여분)
 *
 * `#954` 가 「선택 필지」 라벨을 **끌 수 있게** 했고 `#960` 이 기본 화면의 밀도를 낮췄다.
 * 그런데 **끈 것이 새로고침하면 되돌아온다** — `layerControls` 가 `useState` 뿐이었다.
 * 206필지 작업 중 페이지를 다시 열면 사용자가 **매번 다시 꺼야 한다.**
 *
 * ## ★셀렉터로만 읽는다 — `useState` 지연 초기값으로 읽지 않는다
 *
 * `lib/hydration/render-path-store-reads.ts` 가 판정하는 하이드레이션 위험은 **스냅샷을
 * 우회하는 읽기 3종**이다: ①렌더 중 `getState()` ②스토어 메서드 호출 ③렌더 중 `localStorage`.
 * ★그리고 **`useState` 지연 초기값은 「렌더 중」에 포함된다.**
 * 이 저장소에는 정확히 그 형태로 프로덕션 React #418 이 난 실화가 있다
 * (`GlobalAddressSearch` 의 `useState(() => … getState() …)`).
 * → 소비처는 **셀렉터 전용**(`useSatongMapPrefs((s) => s.controlsByLayer)`)이어야 한다.
 *   셀렉터 읽기는 `zustand/middleware` 가 `api.getInitialState` 를 덮어쓰므로 **원리적으로**
 *   서버/클라 스냅샷이 갈리지 않는다.
 *
 * ## ★계정별 저장
 *
 * `lib/__tests__/persist-key-coverage.test.ts` 가 *"모든 `propai_*` 저장 키는 와이프되거나
 * 계정별이거나, 아니면 **사유를 지닌 면제부**"* 를 파생형으로 강제한다.
 * 실저장키는 `createAccountScopedStorage` 가 `__<uid>` 를 붙여 만든다 → 계정 전환 시 안 섞인다.
 */
export type SatongMapPrefsState = {
  controlsByLayer: SatongMapLayerState["controlsByLayer"];
  setControlsByLayer: (
    next:
      | SatongMapLayerState["controlsByLayer"]
      | ((prev: SatongMapLayerState["controlsByLayer"]) => SatongMapLayerState["controlsByLayer"]),
  ) => void;
  /**
   * 기본값으로 되돌린다.
   * ★UI 노출은 이 PR 범위 밖이지만 **스토어에는 둔다** — 저장된 상태가 나빠졌을 때
   *   빠져나갈 길이 없으면 사용자가 갇힌다. 나중에 붙이려면 배선까지 다시 해야 한다.
   */
  resetControlsByLayer: () => void;
};

/**
 * 기본 컨트롤 — **이 저장소의 단일 소유자**다.
 *
 * ★2026-09-04: 처음에 이 목록을 **기억으로** 다시 썼다가 원본과 **세 군데** 달랐다 —
 *   `transactions` 에서 토지·상업업무용을 빠뜨리고(리뷰가 의도적으로 넣은 것),
 *   `poi` 5개를 2개로 줄이고, `development` 를 **통째로 누락**했다. 그대로 나갔으면
 *   **남의 의도된 기본값을 조용히 되돌리는** 회귀였다.
 *   → 원본을 그대로 옮기고 `SatongMapShell` 은 **여기서 가져다 쓴다**(소유자 하나).
 *   ★「목록은 곧 상한」 — 두 벌이면 반드시 갈린다.
 */
export function defaultSatongMapControls(): SatongMapLayerState["controlsByLayer"] {
  return {
    cadastre: ["boundary", "selected"],
    zoning: ["land-use"],
    "official-price": ["unit-price"],
    age: ["building-age"],
    // ★개발 실무 기본값(레인G 권고) — 아파트만 보이던 종전 하드코딩 대신 토지·상업업무용을
    //   기본 포함해, 레이어를 켜자마자 개발행위 판단에 필요한 유형이 바로 보이게 한다.
    transactions: ["kind-trade", "type-apt", "type-land", "type-commercial"],
    poi: ["station", "school", "commerce", "park", "hospital"],
    development: ["facilities"],
    terrain: ["base"],
    // ★R1 MEDIUM-E: capacity 키 부재로 켜도 showCapacity=false였다 — "지도 표시 중"이
    //   거짓이 되는 terrain과 같은 결함 클래스. mapEffect 컨트롤이 하나뿐이라 논쟁 없음.
    capacity: ["far-headroom"],
  };
}

/**
 * persist 이름. 실저장키는 `propai-satong-map-prefs__<uid>`.
 * ★레거시 공유키가 **없다**(신규 스토어) — 그래서 이름 승계 고민이 없다.
 */
export const SATONG_MAP_PREFS_STORE_KEY = "propai-satong-map-prefs";

export const useSatongMapPrefs = create<SatongMapPrefsState>()(
  persist(
    (set) => ({
      controlsByLayer: defaultSatongMapControls(),
      setControlsByLayer: (next) =>
        set((s) => ({
          controlsByLayer: typeof next === "function" ? next(s.controlsByLayer) : next,
        })),
      resetControlsByLayer: () => set({ controlsByLayer: defaultSatongMapControls() }),
    }),
    { name: SATONG_MAP_PREFS_STORE_KEY, storage: createAccountScopedStorage<SatongMapPrefsState>() },
  ),
);
