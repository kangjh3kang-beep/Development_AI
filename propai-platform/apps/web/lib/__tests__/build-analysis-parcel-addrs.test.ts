/**
 * buildAnalysisParcelAddrs — 분석 대상 필지 주소 SSOT(다필지 배선 절단 방지).
 *
 * ★배경(2026-07-19 라이브 신고): permits 페이지에서 12필지 선택 시 구획도·개발방식·등기가
 *   1필지만 표시. 원인=분석 호출과 렌더 자식이 서로 다른 목록을 만들어(렌더 자식이 store
 *   다필지 누락) 대표주소만 전파. 이 헬퍼가 유일 SSOT — 두 경로가 동일 목록을 쓴다.
 */
import { describe, expect, it } from "vitest";

import { buildAnalysisParcelAddrs } from "../parcel-rows";

// store 다필지 형태(parcelDataToRows 소비 — address+면적>0). 실제 store siteAnalysis.parcels 형태.
const store12 = Array.from({ length: 12 }, (_, i) => ({
  address: `용인시 수지구 신봉동 56-${16 + i}`,
  areaSqm: 100 + i,
}));

describe("buildAnalysisParcelAddrs", () => {
  it("★extra 없음 → store 다필지 전체 포함(대표 선두) — 12필지 절단 재발 방지", () => {
    const out = buildAnalysisParcelAddrs("용인시 수지구 신봉동 56-16", [], store12);
    expect(out.length).toBe(12);          // 종전 버그: 1
    expect(out[0]).toBe("용인시 수지구 신봉동 56-16"); // 대표 선두
    expect(out).toContain("용인시 수지구 신봉동 56-27");
  });

  it("수동 재검색(extra) 있으면 그것을 다필지로 — store는 폴백이므로 제외", () => {
    const out = buildAnalysisParcelAddrs("A동 1", ["A동 2", "A동 3"], store12);
    expect(out).toEqual(["A동 1", "A동 2", "A동 3"]);
  });

  it("target 공백/빈값 → 빈 배열(분석 대상 없음)", () => {
    expect(buildAnalysisParcelAddrs("", [], store12)).toEqual([]);
    expect(buildAnalysisParcelAddrs("   ", ["x"], store12)).toEqual([]);
  });

  it("중복 제거·순서 보존 — target이 store에도 있으면 한 번만", () => {
    const out = buildAnalysisParcelAddrs("용인시 수지구 신봉동 56-16", [], store12);
    expect(out.filter((a) => a === "용인시 수지구 신봉동 56-16").length).toBe(1);
    expect(new Set(out).size).toBe(out.length); // 전건 유일
  });

  it("store 없음(단일 분석) → 대표 1개만 — 정상 단일 경로 무회귀", () => {
    expect(buildAnalysisParcelAddrs("판교동 400", [], null)).toEqual(["판교동 400"]);
    expect(buildAnalysisParcelAddrs("판교동 400", [], undefined)).toEqual(["판교동 400"]);
  });
});
