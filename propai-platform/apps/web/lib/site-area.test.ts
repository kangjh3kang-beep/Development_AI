import { describe, it, expect } from "vitest";
import { effectiveLandAreaSqm } from "./site-area";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";

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
