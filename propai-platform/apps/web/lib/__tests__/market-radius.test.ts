import { readFileSync } from "node:fs";
import { resolve } from "node:path";
/**
 * "고른 값이 곧 적용값" 계약 — 수동 선택은 자동확대를 **끈다**.
 *
 * ★두 모집단을 함께 단언한다: "수동이면 끈다"만 잠그면 **항상 끔**도 통과하고,
 *   그러면 자동 모드(기본)가 죽어 지방 필지가 다시 1km 에 갇힌다(#736 이 고친 그 결함).
 */
import { describe, expect, it } from "vitest";

import { MARKET_RADIUS_DEFAULT_M, marketRadiusRequest,
  shouldShowFetchFailureNotice,
  shouldShowMarketDetails,
  shouldShowRadiusControl,
} from "@/lib/market/market-radius";

describe("marketRadiusRequest", () => {
  it("★수동 선택 — 고른 값 그대로, 확대는 끈다", () => {
    expect(marketRadiusRequest(1000)).toEqual({ radius_m: 1000, auto_expand_radius: false });
    expect(marketRadiusRequest(10000)).toEqual({ radius_m: 10000, auto_expand_radius: false });
  });

  it("★대조군 — 자동(null/undefined)이면 기본 반경 + 확대 **켬**", () => {
    // 이것이 없으면 "항상 끔"도 위 테스트를 통과해 #736 의 효과가 사라진다.
    expect(marketRadiusRequest(null)).toEqual({
      radius_m: MARKET_RADIUS_DEFAULT_M, auto_expand_radius: true,
    });
    expect(marketRadiusRequest(undefined)).toEqual({
      radius_m: MARKET_RADIUS_DEFAULT_M, auto_expand_radius: true,
    });
  });

  it("0·음수는 수동으로 보지 않는다(잘못된 값으로 반경이 붕괴하지 않게)", () => {
    expect(marketRadiusRequest(0).auto_expand_radius).toBe(true);
    expect(marketRadiusRequest(0).radius_m).toBe(MARKET_RADIUS_DEFAULT_M);
    expect(marketRadiusRequest(-5).radius_m).toBe(MARKET_RADIUS_DEFAULT_M);
  });
});

// ── 반경 컨트롤 게이트 (2026-08-23) ──────────────────────────────────────────
//  종전엔 반경 칩이 `marketPayload && !fetch_failed` 게이트 **안**에 있어서, 조회가
//  실패하면 칩도 함께 사라졌다. 그런데 고른 반경은 부모 상태로 **그대로 남아** 같은
//  반경으로 계속 실패한다 — **새로고침 말고는 빠져나갈 길이 없었다.**

describe("반경 컨트롤 게이트 — 실패해도 빠져나갈 수 있어야 한다", () => {
  const on = { marketTypeCount: 1, hasRadiusHandler: true };

  it("★조회 실패와 **무관하게** 반경 컨트롤을 보여준다(탈출구)", () => {
    // 이 함수는 payload 를 **인자로 받지도 않는다** — 그것이 요점이다.
    expect(shouldShowRadiusControl(on)).toBe(true);
  });

  it("★음성대조 — 레이어가 꺼져 있으면 안 보여준다(아무 때나 뜨지 않는다)", () => {
    expect(shouldShowRadiusControl({ ...on, marketTypeCount: 0 })).toBe(false);
  });

  it("★음성대조 — 누를 수 없는 칩은 띄우지 않는다(핸들러 없음)", () => {
    expect(shouldShowRadiusControl({ ...on, hasRadiusHandler: false })).toBe(false);
  });

  it("★상세(유형 건수·위치미확인)는 **응답이 있어야** 보인다 — 반경과 다른 조건", () => {
    expect(shouldShowMarketDetails({ fetch_failed: false })).toBe(true);
    expect(shouldShowMarketDetails({ fetch_failed: true })).toBe(false);
    expect(shouldShowMarketDetails(null)).toBe(false);
    expect(shouldShowMarketDetails(undefined)).toBe(false);
  });

  it("★두 게이트가 **갈린다** — 실패 시 반경은 남고 상세는 사라진다", () => {
    // 두 판정이 같은 값을 내면 게이트를 하나로 합쳐도 테스트가 통과한다(= 결함 재발).
    const failed = { fetch_failed: true };
    expect(shouldShowRadiusControl(on)).toBe(true);
    expect(shouldShowMarketDetails(failed)).toBe(false);
  });

  it("★실패는 침묵하지 않는다 — 고지 조건", () => {
    expect(shouldShowFetchFailureNotice({ fetch_failed: true })).toBe(true);
    expect(shouldShowFetchFailureNotice({ fetch_failed: false })).toBe(false);
    expect(shouldShowFetchFailureNotice(null)).toBe(false);
  });

  it("★배선 — SatongMultiMap 이 이 판정들을 **호출**한다(인라인 조건으로 되돌아가면 실패)", () => {
    const src = readFileSync(
      resolve(process.cwd(), "components/map/SatongMultiMap.tsx"),
      "utf-8",
    );
    // ★import 줄이 아니라 **호출 형태**를 본다(이름만 보면 import 가 대신 만족시킨다).
    expect(src).toContain("shouldShowRadiusControl({");
    expect(src).toContain("shouldShowMarketDetails(marketPayload)");
    expect(src).toContain("shouldShowFetchFailureNotice(marketPayload)");
    // ★음성대조 — 종전 인라인 게이트가 되살아나면 잡는다.
    expect(src).not.toContain("marketPayload && !marketPayload.fetch_failed && marketTypes.length > 0");
  });

  it("★배선 — **형제**(NearbyTransactionsMap)도 같은 공용 조립을 쓴다(발산 차단)", () => {
    // 변이 검증에서 이 줄삭제가 **생존**했다 — 공용화를 해 놓고 잠그지 않으면, 다음 사람이
    // 손으로 `radius_m` 만 실어도 아무도 모른다(다시 두 벌이 된다).
    const sibling = readFileSync(
      resolve(process.cwd(), "components/map/NearbyTransactionsMap.tsx"),
      "utf-8",
    );
    expect(
      sibling,
      "형제가 공용 조립을 쓰지 않는다 — 자동확대 정책이 바뀌면 두 화면이 갈린다",
    ).toContain("marketRadiusRequest(radiusM)");
    // ★음성대조 — 손으로 조립하던 형태가 되살아나면 잡는다.
    expect(sibling).not.toContain("radius_m: radiusM,");
  });
});
