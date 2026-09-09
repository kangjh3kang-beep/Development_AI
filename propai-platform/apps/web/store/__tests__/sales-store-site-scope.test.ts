/**
 * ★현장을 바꿔도 **이전 현장의 세대가 남는다** — 모듈 싱글톤 스토어의 교차현장 누출.
 *
 * 【왜 · 2026-09-09 Stage 3】
 * 사용자 요구: *"현장에서 다른현장으로 실시간 접속을 변경할수있도록하면서
 * **상호 겹치거나 저촉되지않도록**"*.
 *
 * 볼트의 Stage 3 사양(채택): `key={siteId}` **+** `bySite[siteId]`
 * — *"하나만으론 부족 — **모듈 싱글톤이 남는다**"*.
 *
 * 【실측한 결함】`useSalesStore` 는 `units`/`selectedUnit` 을 **현장 구분 없이** 하나로 들고,
 * 리셋 경로가 없다. `UnitGrid` 는 `siteCode` 가 바뀌면 조회를 새로 걸지만
 * (`components/sales/UnitGrid.tsx:31-40`) — **그 조회가 끝나기 전까지** 화면에는
 * **직전 현장의 동·호·상태**가 그대로 그려진다. `selectedUnit` 은 조회 성공 후에도 안 지워져
 * `Unit360Panel` 이 **다른 현장의 세대**를 계속 띄운다.
 *
 * 【축】스토어를 **현장별로** 나눈다. 그러면 «아직 안 불러온 현장» 은 정의상 **빈 목록**이고,
 * 이전 현장 데이터가 새어 나올 자리가 원리적으로 없어진다.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useSalesStore, type Unit } from "@/store/useSalesStore";

const SITE_A = "site-a";
const SITE_B = "site-b";

const unitsA: Unit[] = [
  { id: "a1", dong: "101", ho: "1001", floor: 10, line: "1", status: "AVAILABLE" },
  { id: "a2", dong: "101", ho: "1002", floor: 10, line: "2", status: "HOLD" },
];
const unitsB: Unit[] = [
  { id: "b1", dong: "201", ho: "2001", floor: 20, line: "1", status: "AVAILABLE" },
];

beforeEach(() => {
  useSalesStore.setState(useSalesStore.getInitialState(), true);
});

describe("현장 전환 — 스토어가 현장별로 갈리는가", () => {
  it("대조군: 담은 현장에서는 **그대로 읽힌다**(조회기 생존)", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    expect(useSalesStore.getState().unitsOf(SITE_A)).toHaveLength(2);
  });

  it("★★다른 현장으로 바꾸면 **이전 현장의 세대가 안 보인다**", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    // 아직 B 를 불러오지 않은 상태 — 여기서 A 가 보이면 그것이 누출이다.
    expect(useSalesStore.getState().unitsOf(SITE_B)).toEqual([]);
  });

  it("★★반대편 모집단 — 각 현장이 **자기 것**을 유지한다(전부 비우면 그것도 결함)", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    useSalesStore.getState().setUnits(SITE_B, unitsB);
    expect(useSalesStore.getState().unitsOf(SITE_A).map((u) => u.id)).toEqual(["a1", "a2"]);
    expect(useSalesStore.getState().unitsOf(SITE_B).map((u) => u.id)).toEqual(["b1"]);
  });

  it("★★선택한 세대도 현장별이다 — 다른 현장에서 **남의 세대가 열려 있으면 안 된다**", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    useSalesStore.getState().select(SITE_A, unitsA[0]);
    expect(useSalesStore.getState().selectedOf(SITE_A)?.id).toBe("a1");
    expect(useSalesStore.getState().selectedOf(SITE_B)).toBeUndefined();
  });

  it("★실시간 상태 반영도 **그 현장에만** 적용된다", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    useSalesStore.getState().setUnits(SITE_B, unitsB);
    // 같은 인덱스의 다른 현장 세대가 함께 바뀌면 안 된다.
    useSalesStore.getState().applyStatus(SITE_A, "a1", "CONTRACTED");
    expect(useSalesStore.getState().unitsOf(SITE_A)[0].status).toBe("CONTRACTED");
    expect(useSalesStore.getState().unitsOf(SITE_B)[0].status).toBe("AVAILABLE");
  });

  it("★빈 목록은 **모듈 상수**로 돌려준다 — 셀렉터가 매번 새 배열을 만들면 무한 렌더(React #185)", () => {
    const a = useSalesStore.getState().unitsOf("never-loaded");
    const b = useSalesStore.getState().unitsOf("never-loaded-2");
    expect(a).toBe(b);
  });

  it("★현장을 떠나면 그 현장 것만 비운다(다른 현장은 남는다)", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    useSalesStore.getState().setUnits(SITE_B, unitsB);
    useSalesStore.getState().clearSite(SITE_A);
    expect(useSalesStore.getState().unitsOf(SITE_A)).toEqual([]);
    expect(useSalesStore.getState().unitsOf(SITE_B)).toHaveLength(1);
  });
});

describe("부채 — 초록 안에 보이게 둔다", () => {
  // ★`applyStatus` 는 **소비처 0건**이다(2026-09-09 파생 전수). 종전 주석은 «WebSocket 실시간
  //   반영» 이라고 동작을 주장했지만 부르는 곳이 없다. 위 테스트는 함수 자체는 태우므로
  //   «현장별로 적용된다» 는 잠겨 있고, **배선**만 비어 있다.
  it.todo("WebSocket 이벤트가 applyStatus 를 부른다 — 지금은 소비처 0건(배선 부채)");

  // ★볼트 Stage 3 사양의 나머지 절반. `SiteWorkspaceClient` 는 PR #1022 가 편집 중이라
  //   그 PR 이 머지된 뒤에 붙인다(같은 파일을 두 브랜치에서 만지지 않는다).
  it.todo("워크스페이스가 key={siteId} 로 remount 된다 — 컴포넌트 지역 상태까지 갈린다");
});
