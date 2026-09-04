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
  /**
   * 켜져 있는 레이어. ★`Set` 이 아니라 **배열**인 이유: `Set` 은 `JSON.stringify` 로 `{}` 가
   * 되어 영속되지 않는다. 소비처는 `useMemo` 로 `Set` 을 파생한다(9곳이 `.has()` 를 쓴다).
   */
  enabledLayerIds: SatongMapLayerState["enabledLayerIds"];
  /**
   * 레이어를 켜고 끈다. ★`cadastre` 는 **기반 레이어라 끄지 않는다**(종전 계약 이식).
   * ★변화가 없으면 **같은 배열 참조**를 돌려준다 — 그러지 않으면 소비처의 `useMemo` 가
   *   재계산돼 `mapLayerState` identity 가 바뀌고, 그걸 deps 로 쓰는 오버레이·POI effect 가
   *   **전량 파괴·재생성**된다(저장소가 «깜빡임의 근원» 이라 적은 그 축).
   */
  toggleLayerEnabled: (id: SatongMapLayerState["enabledLayerIds"][number]) => void;
  /** 켜져 있지 않으면 켠다. ★이미 켜져 있으면 **같은 배열 참조**(종전 조기반환 이식). */
  ensureLayerEnabled: (id: SatongMapLayerState["enabledLayerIds"][number]) => void;
  resetEnabledLayers: () => void;
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
/**
 * 기본으로 켜져 있는 레이어 — 지적도 하나(종전 `new Set(["cadastre"])` 그대로).
 * ★`cadastre` 는 기반 레이어라 끄지 못한다(`toggleLayerEnabled` 가 지킨다).
 */
export function defaultEnabledLayerIds(): SatongMapLayerState["enabledLayerIds"] {
  return ["cadastre"];
}

export const SATONG_MAP_PREFS_STORE_KEY = "propai-satong-map-prefs";

export const useSatongMapPrefs = create<SatongMapPrefsState>()(
  persist(
    (set) => ({
      enabledLayerIds: defaultEnabledLayerIds(),
      toggleLayerEnabled: (id) =>
        set((s) => {
          const has = s.enabledLayerIds.includes(id);
          if (has && id === "cadastre") return s; // ★기반 레이어 — 못 끈다(변화 없음 = 같은 참조)
          return {
            enabledLayerIds: has
              ? s.enabledLayerIds.filter((x) => x !== id)
              : [...s.enabledLayerIds, id],
          };
        }),
      ensureLayerEnabled: (id) =>
        set((s) =>
          // ★이미 켜져 있으면 **같은 참조** — 종전 `if (prev.has(layerId)) return prev;` 의 이식.
          s.enabledLayerIds.includes(id) ? s : { enabledLayerIds: [...s.enabledLayerIds, id] },
        ),
      resetEnabledLayers: () => set({ enabledLayerIds: defaultEnabledLayerIds() }),
      controlsByLayer: defaultSatongMapControls(),
      setControlsByLayer: (next) =>
        set((s) => ({
          controlsByLayer: typeof next === "function" ? next(s.controlsByLayer) : next,
        })),
      resetControlsByLayer: () => set({ controlsByLayer: defaultSatongMapControls() }),
    }),
    {
      name: SATONG_MAP_PREFS_STORE_KEY,
      storage: createAccountScopedStorage<SatongMapPrefsState>(),
      version: 1,
      /**
       * ★`version` 만 올리고 `migrate` 를 안 두면 **옛 저장분이 조용히 버려진다**
       *   (실측: v0 블롭을 심었더니 기본값이 이겼다 — 사용자가 껐던 것이 되돌아온다).
       *   이 스토어의 스키마 변경은 **레이어 추가**뿐이고 그건 아래 `merge` 가 메운다.
       *   그래서 마이그레이션은 **통과**시키고, 실제 복구는 `merge` 가 한다.
       * ★언제 이걸 바꿔야 하나: 컨트롤 **id 어휘**가 바뀔 때(`selected` ↔ `selected-parcel`
       *   통합이 그 경우다 — 계획서 §3 에 미정으로 적어 뒀다). 그때는 여기서 옛 id 를 옮긴다.
       */
      migrate: (persisted) => persisted as SatongMapPrefsState,
      /**
       * ★zustand 기본 `merge` 는 **얕다**(top-level spread) — 저장분의 `controlsByLayer` 가
       *   기본값 맵을 **통째로 대체**한다. 그래서 저장 당시 없던 레이어는 **영구히 빠진다.**
       *   (2026-09-04 적대 리뷰 Finding 2 실측: 저장분 `{cadastre:[…]}` 하나가 나머지 8개
       *    레이어의 기본값을 **전부 지웠다**. 그리고 내 테스트가 정확히 그 픽스처를 쓰면서
       *    «selected 가 꺼졌나» 만 보고 **그 파괴를 못 봤다.**)
       * ★이 저장소는 그 실패를 이미 한 번 겪었다 — 이 파일이 옮겨 온 주석에 적혀 있다:
       *   *"R1 MEDIUM-E: capacity 키 부재로 켜도 showCapacity=false였다."*
       *   그때는 한 릴리스로 끝났지만, 저장분이 생기면 **사용자마다 영구히** 남는다.
       * → 레이어 단위로 **기본값 위에 저장분을 덮는다.** 새 레이어가 추가되면 기존 사용자도 받는다.
       */
      merge: (persisted, current) => {
        const p = (persisted ?? {}) as Partial<SatongMapPrefsState>;
        // ★★identity 보존(2026-09-04 · 2차 적대 리뷰 MAJOR-1). 초판은 저장분이 **없어도**
        //   객체 리터럴을 새로 만들었다 — zustand 는 hydrate 에서 merge+set 을 **무조건**
        //   부르므로(`middleware.js:415`), 저장분이 없는 **모든 사용자**가
        //   `getInitialState().controlsByLayer !== getState().controlsByLayer` 가 됐다.
        //   그 identity 가 `mapLayerState` memo → `layerState` 로 흘러가고, 이 저장소는
        //   그 귀결을 **명문으로** 적어 뒀다(`SatongMapShell.tsx`):
        //     *"layerState identity 가 바뀌고, 그걸 deps 로 쓰는 필지 오버레이·POI effect 가
        //       전량 파괴·재생성된다(레이어 토글 시 깜빡임의 근원)."*
        //   ★그 자리는 `new Set` 을 안 만들려고 **참조 동일 조기반환**까지 넣어 둔 곳이다.
        //   내가 봉합(MAJOR-2 의 깊은 merge)을 하면서 그 방어를 **모든 사용자에게** 깼다.
        //   ★그리고 내 계획서 §3 은 이것을 *"저장분이 있는 사용자"* 로 좁혀 적었다 — **틀렸다.**
        //   → 저장분이 없으면 **현재 참조를 그대로** 돌려준다. 있으면 그때만 새로 만든다.
        //   ★함수 등 **알려진 키만** 취한다(리뷰 minor 5): `...p` 는 손으로 편집된 저장분의
        //     아무 키나 덮어써서 액션까지 갈아 끼울 수 있었다.
        const hasControls = !!p.controlsByLayer;
        const hasLayers = Array.isArray(p.enabledLayerIds);
        // ★저장분이 아무것도 없으면 **현재 참조 그대로**(2차 리뷰 MAJOR-1 — hydrate 는 저장분이
        //   없어도 merge+set 을 무조건 부르므로, 여기서 새 객체를 만들면 **전 사용자**가
        //   identity 교체를 겪는다).
        if (!hasControls && !hasLayers) return current;
        return {
          ...current,
          // ★`controlsByLayer` 는 **레이어 단위로 기본값 위에 덮는다** — 새 레이어가 추가되면
          //   기존 사용자도 그 기본 컨트롤을 받아야 한다(«capacity 키 부재» 사고의 영속판 방지).
          ...(hasControls
            ? { controlsByLayer: { ...defaultSatongMapControls(), ...p.controlsByLayer } }
            : {}),
          // ★★`enabledLayerIds` 는 **성질이 다르다** — 여기 담긴 것은 «사용자가 켠 것» 이다.
          //   기본값과 합치면 사용자가 **끈 레이어가 되살아난다.** 그래서 **저장분을 그대로**
          //   존중한다. 귀결: 새 레이어가 추가돼도 기존 사용자에게 **자동으로 켜지지 않는다.**
          //   그 절충을 계획서 §3 에 적었고 아래 락이 고정한다.
          ...(hasLayers ? { enabledLayerIds: p.enabledLayerIds } : {}),
        };
      },
    },
  ),
);
