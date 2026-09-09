/**
 * v62 분양관리 동호 상태 스토어 (zustand v5) — **현장별로 갈린다**.
 *
 * ## 왜 현장별인가 (2026-09-09 · Stage 3)
 *
 * 사용자 요구: *"현장에서 다른현장으로 실시간 접속을 변경할수있도록하면서
 * **상호 겹치거나 저촉되지않도록**"*.
 *
 * 종전에는 `units`/`selectedUnit` 을 **하나만** 들었다. 그런데 이 스토어는 **모듈 싱글톤**이라
 * 현장을 바꿔도 살아 있고, 리셋 경로가 없었다:
 *
 *   · `UnitGrid` 는 `siteCode` 가 바뀌면 조회를 새로 걸지만(`components/sales/UnitGrid.tsx`)
 *     **그 조회가 끝나기 전까지** 화면에는 **직전 현장의 동·호·상태**가 그대로 그려진다.
 *   · `selectedUnit` 은 조회가 성공해도 안 지워져 `Unit360Panel` 이
 *     **다른 현장의 세대**를 계속 띄운다.
 *
 * ★볼트의 Stage 3 사양(채택)이 이것을 명시한다 — `key={siteId}` **+** `bySite[siteId]`,
 *   *"하나만으론 부족 — **모듈 싱글톤이 남는다**"*. 이 파일이 그 두 번째 절반이다.
 *
 * ⇒ 상태를 **현장 키로** 나눈다. 그러면 «아직 안 불러온 현장» 은 정의상 **빈 목록**이고,
 *   이전 현장 데이터가 새어 나올 자리가 **원리적으로** 없어진다(«안 보이게 가리는» 것이 아니다).
 *
 * ★셀렉터 안정성: 빈 배열은 **모듈 상수**(`EMPTY_UNITS`)로 돌려준다.
 *   매번 새 배열을 만들면 zustand 셀렉터가 매 렌더 새 참조를 보고 무한 렌더(React #185)가 난다.
 */
import { create } from "zustand";
import type { UnitStatus } from "@/lib/salesApi";

export interface Unit {
  id: string;
  dong: string;
  ho: string;
  floor: number;
  line: string;
  aspect?: string;
  status: UnitStatus;
  total_price?: number;
  type_id?: string;
}

export const EMPTY_UNITS: Unit[] = [];

interface SalesState {
  /** 현장 → 세대 목록. ★키가 없으면 「아직 안 불러왔다」이지 「없다」가 아니다. */
  unitsBySite: Record<string, Unit[]>;
  selectedBySite: Record<string, Unit | undefined>;

  unitsOf: (siteId: string) => Unit[];
  selectedOf: (siteId: string) => Unit | undefined;

  setUnits: (siteId: string, u: Unit[]) => void;
  select: (siteId: string, u?: Unit) => void;
  /** 세대 상태 1건 반영 — **그 현장에만** 적용된다.
   *
   * ★**소비처 0건**(2026-09-09 파생 전수 실측). 종전 주석은 «WebSocket 실시간 반영» 이라고
   *   **동작을 주장**했는데 이 함수를 부르는 곳이 저장소에 없다. 실시간 갱신은 지금
   *   `UnitLiveBoard` 가 **자기 상태로** 하고 있고 이 스토어를 거치지 않는다.
   *   ⇒ 주장을 사실로 낮췄다. 배선은 부채(`store/__tests__/sales-store-site-scope.test.ts` 의 todo).
   */
  applyStatus: (siteId: string, unitId: string, to: UnitStatus) => void;
  /** 현장을 떠날 때 **그 현장 것만** 비운다(다른 현장은 남는다). */
  clearSite: (siteId: string) => void;
}

export const useSalesStore = create<SalesState>((set, get) => ({
  unitsBySite: {},
  selectedBySite: {},

  // ★`?? EMPTY_UNITS` — 모듈 상수라 미조회 현장끼리도 **같은 참조**다(셀렉터 안정).
  unitsOf: (siteId) => get().unitsBySite[siteId] ?? EMPTY_UNITS,
  selectedOf: (siteId) => get().selectedBySite[siteId],

  setUnits: (siteId, u) =>
    set((st) => ({ unitsBySite: { ...st.unitsBySite, [siteId]: u } })),

  select: (siteId, u) =>
    set((st) => ({ selectedBySite: { ...st.selectedBySite, [siteId]: u } })),

  applyStatus: (siteId, id, to) =>
    set((st) => ({
      unitsBySite: {
        ...st.unitsBySite,
        [siteId]: (st.unitsBySite[siteId] ?? EMPTY_UNITS).map(
          (u) => (u.id === id ? { ...u, status: to } : u),
        ),
      },
    })),

  clearSite: (siteId) =>
    set((st) => {
      const units = { ...st.unitsBySite };
      const selected = { ...st.selectedBySite };
      delete units[siteId];
      delete selected[siteId];
      return { unitsBySite: units, selectedBySite: selected };
    }),
}));
