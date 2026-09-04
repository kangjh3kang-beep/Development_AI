/**
 * ★R1 후속(레인G R2 항목2·MEDIUM 필수) — 실거래 다중 유형 렌더 계획 회귀망.
 *
 * 배경: 유형 다중 표시(레인G) 커밋이 테스트 0개로 머지될 뻔했다 — "유형 순회 → 첫 유형만
 * 그림" 같은 회귀가 전혀 포착되지 않는 구조였다. resolveMarketRenderPlan은 마켓 이펙트가
 * "무엇을 그릴지" 결정하는 순수 함수로 추출됐다(이 파일의 관례 — window.L 목업 없이
 * buildOverlayNotes·planSatongLabels와 동일하게 순수 로직만 단위테스트).
 */
import { describe, expect, it } from "vitest";

import { resolveMarketRenderPlan, type SatongMarketPayload } from "@/components/map/SatongMultiMap";

const basePayload: SatongMarketPayload = {
  center: { lat: 37.5, lon: 127.0 },
  categories: {
    apt_trade: { type: "apt", kind: "trade", count: 1, groups: [{ name: "A", lat: 37.5, lon: 127.0, count: 1 }] },
    land_trade: {
      type: "land", kind: "trade", count: 1, capped_count: 3,
      groups: [{ name: "B", lat: 37.51, lon: 127.01, count: 1 }],
    },
    commercial_trade: { type: "commercial", kind: "trade", count: 1, groups: [{ name: "C", lat: 37.52, lon: 127.02, count: 1 }] },
  },
};

describe("resolveMarketRenderPlan — 다중 유형 동시 렌더(POI 패턴) 회귀", () => {
  it("★핵심 회귀: types에 3개 유형을 주면 3개 렌더 엔트리가 생성된다(첫 유형만 그리면 FAIL)", () => {
    const plan = resolveMarketRenderPlan(basePayload, ["apt", "land", "commercial"], "trade");
    expect(plan).toHaveLength(3);
    expect(plan.map((p) => p.type)).toEqual(["apt", "land", "commercial"]);
    expect(plan.every((p) => p.groups.length === 1)).toBe(true);
  });

  it("유형별 색상은 SSOT(MARKET_TYPE_COLORS)를 따른다", () => {
    const plan = resolveMarketRenderPlan(basePayload, ["apt", "land"], "trade");
    expect(plan.find((p) => p.type === "apt")?.color).toBe("#14b8a6");
    expect(plan.find((p) => p.type === "land")?.color).toBe("#65a30d");
  });

  it("capped_count를 유형별로 그대로 전달한다(절단 정직 고지 배선)", () => {
    const plan = resolveMarketRenderPlan(basePayload, ["land"], "trade");
    expect(plan[0].cappedCount).toBe(3);
  });

  it("capped_count 미제공 카테고리는 0으로 취급한다(무날조 — undefined 방치 금지)", () => {
    const plan = resolveMarketRenderPlan(basePayload, ["apt"], "trade");
    expect(plan[0].cappedCount).toBe(0);
  });

  it("좌표 미확보(lat/lon 없음) 그룹은 제외한다", () => {
    const payload: SatongMarketPayload = {
      center: { lat: 37.5, lon: 127.0 },
      categories: {
        apt_trade: {
          groups: [
            { name: "확보", lat: 37.5, lon: 127.0, count: 1 },
            { name: "미확보", lat: undefined as unknown as number, lon: undefined as unknown as number, count: 1 },
          ],
        },
      },
    };
    const plan = resolveMarketRenderPlan(payload, ["apt"], "trade");
    expect(plan[0].groups).toHaveLength(1);
    expect(plan[0].groups[0].name).toBe("확보");
  });

  it("전월세(rent) 미지원 유형은 카테고리 부재로 빈 groups를 반환한다(SatongMapShell의 kind 필터가 이 카테고리를 애초에 요청 리스트에서 빼야 하는 이유)", () => {
    const rentPayload: SatongMarketPayload = {
      center: { lat: 37.5, lon: 127.0 },
      categories: { apt_rent: { groups: [{ name: "R", lat: 37.5, lon: 127.0, count: 1 }] } },
    };
    const plan = resolveMarketRenderPlan(rentPayload, ["apt", "land"], "rent");
    expect(plan.find((p) => p.type === "apt")?.groups).toHaveLength(1);
    expect(plan.find((p) => p.type === "land")?.groups).toHaveLength(0);
  });

  it("center 미확보/조회실패면 빈 배열(무표시)", () => {
    expect(resolveMarketRenderPlan(null, ["apt"], "trade")).toEqual([]);
    expect(resolveMarketRenderPlan({ center: null }, ["apt"], "trade")).toEqual([]);
    expect(
      resolveMarketRenderPlan({ center: { lat: 37.5, lon: 127 }, fetch_failed: true }, ["apt"], "trade"),
    ).toEqual([]);
  });

  it("types가 빈 배열이면 빈 계획(레이어 OFF와 동일 — 무표시)", () => {
    expect(resolveMarketRenderPlan(basePayload, [], "trade")).toEqual([]);
  });
});
