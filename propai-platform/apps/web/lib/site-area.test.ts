import { describe, it, expect } from "vitest";
import { effectiveLandAreaSqm, blendedFarPct } from "./site-area";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";

// 테스트는 헬퍼가 읽는 필드(landAreaSqm/landAreaSqmTotal/parcelCount)만 의미가 있다.
// SiteAnalysisData의 나머지 필수 필드는 검증과 무관하므로 부분 객체로 구성한다.
function sa(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return partial as SiteAnalysisData;
}

// getZoningSpec 실측(kr-building-regulations ZONING_DB):
//   제1종일반주거=200 · 제2종일반주거=250 · 제3종일반주거=300 · 일반상업=1300
function parcel(zoneCode: string, areaSqm: number, i = 0) {
  return { pnu: `p${i}`, address: `필지${i}`, areaSqm, landCategory: "대", ownerType: "미확인", zoneCode };
}

describe("effectiveLandAreaSqm — 유효 대지면적(다필지 통합 우선)", () => {
  it("다필지: 통합면적(landAreaSqmTotal)을 우선 반환한다", () => {
    // 상도동 시나리오: 대표 236㎡인데 단일 분석이 landAreaSqm을 236으로 덮어써도
    // parcelCount>1 && landAreaSqmTotal>0 이면 통합 779㎡를 돌려줘야 한다.
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 236, landAreaSqmTotal: 779, parcelCount: 2 }),
    );
    expect(v).toBe(779);
  });

  it("단일필지: landAreaSqm을 그대로 반환한다", () => {
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 540, landAreaSqmTotal: null, parcelCount: 1 }),
    );
    expect(v).toBe(540);
  });

  it("parcelCount 미설정: 단일로 보고 landAreaSqm을 반환한다", () => {
    const v = effectiveLandAreaSqm(sa({ landAreaSqm: 312 }));
    expect(v).toBe(312);
  });

  it("미확보: 면적이 둘 다 없으면 null(0 강제 금지)", () => {
    expect(effectiveLandAreaSqm(sa({ landAreaSqm: null }))).toBeNull();
    expect(effectiveLandAreaSqm(null)).toBeNull();
    expect(effectiveLandAreaSqm(undefined)).toBeNull();
  });

  it("다필지인데 통합면적이 비정상(0/null)이면 단일/대표(landAreaSqm)로 폴백한다", () => {
    // 통합 메타가 아직 안 들어왔거나 0이면 통합을 신뢰하지 않고 landAreaSqm 사용.
    expect(
      effectiveLandAreaSqm(
        sa({ landAreaSqm: 236, landAreaSqmTotal: 0, parcelCount: 2 }),
      ),
    ).toBe(236);
    expect(
      effectiveLandAreaSqm(
        sa({ landAreaSqm: 236, landAreaSqmTotal: null, parcelCount: 2 }),
      ),
    ).toBe(236);
  });

  it("단일필지에서 통합면적이 우연히 있어도(파셀1) 통합을 쓰지 않는다", () => {
    // parcelCount=1이면 다필지가 아니므로 landAreaSqm 우선(통합 메타 잔류 영향 차단).
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 400, landAreaSqmTotal: 779, parcelCount: 1 }),
    );
    expect(v).toBe(400);
  });
});

describe("blendedFarPct — 유효 용적률 상한(다필지=면적가중평균)", () => {
  it("단일필지: 대표 용도지역 상한을 그대로 반환한다", () => {
    expect(blendedFarPct(sa({ zoneCode: "제2종일반주거지역" }))).toBe(250);
  });

  it("다필지: 필지별 용적률을 면적가중평균한다(백엔드 _blended_far 미러)", () => {
    // 1000㎡ 제1종(200) + 1000㎡ 일반상업(1300) → (200*1000+1300*1000)/2000 = 750
    const v = blendedFarPct(
      sa({
        parcelCount: 2,
        parcels: [parcel("제1종일반주거지역", 1000, 1), parcel("일반상업지역", 1000, 2)] as never,
      }),
    );
    expect(v).toBe(750);
  });

  it("★혼합지에서 대표필지값과 확연히 다르다(P0 회귀 방지)", () => {
    // 대표(첫 필지)만 보면 200이지만, 상업이 섞이면 가중평균은 그보다 크다.
    // 통합면적 × 대표FAR(200) 이 아니라 가중FAR 을 써야 함을 못박는다.
    const v = blendedFarPct(
      sa({
        parcelCount: 2,
        parcels: [parcel("제1종일반주거지역", 500, 1), parcel("일반상업지역", 1500, 2)] as never,
      }),
    );
    // (200*500 + 1300*1500)/2000 = (100000+1950000)/2000 = 1025
    expect(v).toBe(1025);
    expect(v).not.toBe(200); // 대표필지값이 아님
  });

  it("면적 일부 누락 시 단순평균으로 폴백한다", () => {
    // 한 필지 면적이 0 → 단순평균 (200+300)/2 = 250
    const v = blendedFarPct(
      sa({
        parcelCount: 2,
        parcels: [parcel("제1종일반주거지역", 0, 1), parcel("제3종일반주거지역", 1000, 2)] as never,
      }),
    );
    expect(v).toBe(250);
  });

  it("용도지역을 하나도 못 읽으면 null(무목업 — 0 강제 금지)", () => {
    expect(blendedFarPct(sa({ parcelCount: 2, parcels: [] as never }))).toBeNull();
    expect(blendedFarPct(sa({}))).toBeNull();
  });

  it("다필지지만 필지 zoneCode 가 전무하면 대표 zoneCode 로 폴백한다", () => {
    const v = blendedFarPct(
      sa({
        zoneCode: "제2종일반주거지역",
        parcelCount: 2,
        parcels: [parcel("", 500, 1), parcel("", 500, 2)] as never,
      }),
    );
    expect(v).toBe(250); // 대표 폴백
  });
});
