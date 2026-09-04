import { describe, it, expect } from "vitest";
import { hasSiteBasis } from "@/lib/design-ssot";

// M2(PR#316 리뷰) — 레일(DesignWorkspace)·콘솔(DesignStudio)이 공유하는 "부지 기준 준비됨" 단일
// 진실원천. DesignWorkspace의 기존 판정 알고리즘(주소 addressTokenMismatch·면적>0·용도지역 확보)을
// 그대로 이 함수로 옮겼으므로, 여기 스냅샷 테스트가 곧 그 기존 동작의 회귀 방지 계약이다.
describe("hasSiteBasis — 부지 기준 준비상태 공용 판정(레일↔콘솔 단일 술어)", () => {
  it("siteAnalysis 없음: false", () => {
    expect(hasSiteBasis(null, "서울 강남구 역삼동 737")).toBe(false);
    expect(hasSiteBasis(undefined, null)).toBe(false);
  });

  it("주소·PNU 둘 다 없음: false(수집 대상 식별 불가)", () => {
    expect(
      hasSiteBasis({ landAreaSqm: 500, zoneCode: "제2종일반주거지역" }, null),
    ).toBe(false);
  });

  it("면적 미확보(0/null): false", () => {
    expect(
      hasSiteBasis(
        { address: "서울 강남구 역삼동 737", landAreaSqm: 0, zoneCode: "제2종일반주거지역" },
        null,
      ),
    ).toBe(false);
    expect(
      hasSiteBasis(
        { address: "서울 강남구 역삼동 737", landAreaSqm: null, zoneCode: "제2종일반주거지역" },
        null,
      ),
    ).toBe(false);
  });

  it("용도지역 미확보: false(결함#4 핵심 케이스 — 면적만 있고 용도지역 없음)", () => {
    expect(
      hasSiteBasis({ address: "서울 강남구 역삼동 737", landAreaSqm: 500 }, null),
    ).toBe(false);
  });

  it("주소+면적+용도지역 모두 확보(프로젝트 주소 미지정): true", () => {
    expect(
      hasSiteBasis(
        { address: "서울 강남구 역삼동 737", landAreaSqm: 500, zoneCode: "제2종일반주거지역" },
        null,
      ),
    ).toBe(true);
  });

  it("프로젝트 주소와 명백히 불일치(다른 시군구): false", () => {
    expect(
      hasSiteBasis(
        { address: "경기도 성남시 분당구 정자동 178-1", landAreaSqm: 500, zoneCode: "제2종일반주거지역" },
        "서울특별시 강남구 역삼동 737",
      ),
    ).toBe(false);
  });

  it("프로젝트 주소와 일치: true", () => {
    expect(
      hasSiteBasis(
        { address: "서울특별시 강남구 역삼동 737", landAreaSqm: 500, zoneCode: "제2종일반주거지역" },
        "서울특별시 강남구 역삼동 737",
      ),
    ).toBe(true);
  });

  it("다필지 통합면적(landAreaSqmTotal) 우선 — 대표필지 면적이 0이어도 통합면적으로 true", () => {
    expect(
      hasSiteBasis(
        {
          address: "서울 강남구 역삼동 737",
          landAreaSqm: 0,
          landAreaSqmTotal: 779,
          parcelCount: 2,
          dominantZoneCode: "제2종일반주거지역",
        },
        null,
      ),
    ).toBe(true);
  });

  it("PNU만 있고 주소가 없어도 true(주소 또는 PNU 확보 조건)", () => {
    expect(
      hasSiteBasis(
        { pnu: "1168010100107370000", landAreaSqm: 500, zoneCode: "제2종일반주거지역" },
        null,
      ),
    ).toBe(true);
  });
});
