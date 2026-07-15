import { describe, it, expect } from "vitest";
import { effectiveLandAreaSqm, parcelAreaSqmSum } from "./site-area";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";

type Parcel = { pnu: string; address: string; areaSqm: number; landCategory: string; ownerType: string };
function parcel(areaSqm: number, i = 0): Parcel {
  return { pnu: `p${i}`, address: `필지${i}`, areaSqm, landCategory: "대", ownerType: "미확인" };
}

// 테스트는 헬퍼가 읽는 필드(landAreaSqm/landAreaSqmTotal/parcelCount)만 의미가 있다.
// SiteAnalysisData의 나머지 필수 필드는 검증과 무관하므로 부분 객체로 구성한다.
function sa(partial: Partial<SiteAnalysisData>): SiteAnalysisData {
  return partial as SiteAnalysisData;
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

describe("effectiveLandAreaSqm — 필지 합 교차검증(오염된 스칼라 면적 방어)", () => {
  // ★라이브 상도동 211-376 재현: 스칼라가 11,465(법정동 단위 추정)로 오염됐으나
  //   실제 5필지 합은 3,059㎡. 필지 합이 권위 출처이므로 그쪽을 신뢰해야 한다.
  const FIVE = [parcel(1474, 1), parcel(420, 2), parcel(385, 3), parcel(410, 4), parcel(370, 5)]; // 합 3059

  it("스칼라 total 이 필지 합과 5% 넘게 어긋나면 필지 합을 신뢰한다", () => {
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 1474, landAreaSqmTotal: 11465, parcelCount: 5, parcels: FIVE }),
    );
    expect(v).toBe(3059); // 11,465(오염) 아님
  });

  it("landAreaSqm 만 오염되고 total 이 없어도 필지 합을 신뢰한다", () => {
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 11465, landAreaSqmTotal: null, parcelCount: 5, parcels: FIVE }),
    );
    expect(v).toBe(3059);
  });

  it("스칼라가 필지 합과 5% 이내면 정상값을 그대로 둔다(굳이 흔들지 않음)", () => {
    // total 3050 vs 필지합 3059 → 0.3% 차이(반올림 오차) → total 유지.
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 1474, landAreaSqmTotal: 3050, parcelCount: 5, parcels: FIVE }),
    );
    expect(v).toBe(3050);
  });

  it("필지가 1개면 교차검증하지 않는다(단일필지 기존 동작 보존)", () => {
    const v = effectiveLandAreaSqm(
      sa({ landAreaSqm: 1474, landAreaSqmTotal: null, parcelCount: 1, parcels: [parcel(1474, 1)] }),
    );
    expect(v).toBe(1474);
  });

  it("면적 미확보 필지(0/null)는 합에서 빠진다 — 무목업", () => {
    const parcels = [parcel(1474, 1), { ...parcel(0, 2), areaSqm: 0 }, parcel(385, 3)];
    expect(parcelAreaSqmSum(sa({ parcels }))).toBe(1859); // 1474+385, 0필지 제외
  });

  it("parcels 부재 시 스칼라를 그대로 쓴다(구 스냅샷 하위호환)", () => {
    const v = effectiveLandAreaSqm(sa({ landAreaSqm: 540, parcelCount: 2 }));
    expect(v).toBe(540);
  });
});
