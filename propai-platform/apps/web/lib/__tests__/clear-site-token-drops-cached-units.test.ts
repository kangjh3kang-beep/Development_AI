/**
 * ★현장 토큰을 버렸는데 **그 현장의 세대가 메모리에 남는다**(2026-09-09 · Stage 3 · 리뷰 M2).
 *
 * 【축】`clearSite` 는 스토어에 **선언만** 돼 있고 소비처가 0건이었다(파생 전수 실측).
 * 「선언만」은 잠금이 아니다 — 함수가 옳게 동작해도 아무도 부르지 않으면 결함은 그대로다.
 *
 * 【결함】`clearSiteToken` 은 `sessionStorage` 의 토큰만 지운다. 스토어는 **모듈 싱글톤**이라
 * 세대 목록·선택 세대는 살아남는다. 멤버십 상실(4403)로 토큰이 폐기된 뒤 같은 탭에서
 * 그 현장으로 돌아가면 **권한이 사라진 현장의 데이터가 다시 그려진다.**
 *
 * 【이 락이 보는 것】«`clearSite` 가 불렸는가» 가 아니라 **«그래서 상태가 비었는가»** 다.
 * 그리고 **두 모집단**을 같은 실행에서 본다 — A 는 비워지고 **B 는 남아야 한다**
 * (전부 비우는 구현도 첫 단언만으로는 통과한다).
 */
import { beforeEach, describe, expect, it } from "vitest";

import { clearSiteToken, storeSiteToken, getStoredSiteToken } from "@/lib/salesApi";
import { useSalesStore, type Unit } from "@/store/useSalesStore";

const SITE_A = "site-a";
const SITE_B = "site-b";

const unitsA: Unit[] = [
  { id: "a1", dong: "101", ho: "1001", floor: 10, line: "1", status: "AVAILABLE" },
];
const unitsB: Unit[] = [
  { id: "b1", dong: "201", ho: "2001", floor: 20, line: "1", status: "AVAILABLE" },
];

beforeEach(() => {
  useSalesStore.setState(useSalesStore.getInitialState(), true);
  window.sessionStorage.clear();
});

describe("현장 토큰 폐기 — 캐시된 세대도 함께 버린다", () => {
  it("대조군: 담은 것이 **실제로 읽힌다**(조회기 생존)", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    storeSiteToken(SITE_A, "tok", 3600, { role: "MEMBER", features: [] });
    expect(useSalesStore.getState().unitsOf(SITE_A)).toHaveLength(1);
    expect(getStoredSiteToken(SITE_A)?.token).toBe("tok");
  });

  it("★★토큰을 버리면 그 현장의 세대·선택이 **비워진다**(「불렸는가」가 아니라 「비었는가」)", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    useSalesStore.getState().select(SITE_A, unitsA[0]);
    storeSiteToken(SITE_A, "tok", 3600, { role: "MEMBER", features: [] });

    clearSiteToken(SITE_A);

    expect(getStoredSiteToken(SITE_A)).toBeNull();
    expect(useSalesStore.getState().unitsOf(SITE_A)).toEqual([]);
    expect(useSalesStore.getState().selectedOf(SITE_A)).toBeUndefined();
  });

  it("★★반대편 모집단 — **다른 현장은 남는다**(전부 비우는 구현도 결함이다)", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    useSalesStore.getState().setUnits(SITE_B, unitsB);
    useSalesStore.getState().select(SITE_B, unitsB[0]);
    storeSiteToken(SITE_A, "tok-a", 3600, { role: "MEMBER", features: [] });
    storeSiteToken(SITE_B, "tok-b", 3600, { role: "MEMBER", features: [] });

    clearSiteToken(SITE_A);

    expect(useSalesStore.getState().unitsOf(SITE_B).map((u) => u.id)).toEqual(["b1"]);
    expect(useSalesStore.getState().selectedOf(SITE_B)?.id).toBe("b1");
    expect(getStoredSiteToken(SITE_B)?.token).toBe("tok-b");
  });

  it("★빈 siteId 는 **아무것도 지우지 않는다**(가드의 위양성도 결함이다)", () => {
    useSalesStore.getState().setUnits(SITE_A, unitsA);
    clearSiteToken("");
    expect(useSalesStore.getState().unitsOf(SITE_A)).toHaveLength(1);
  });
});
