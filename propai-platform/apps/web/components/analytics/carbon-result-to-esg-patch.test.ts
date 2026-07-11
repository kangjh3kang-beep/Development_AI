// carbonResultToEsgPatch 단위테스트 — 자재 탄소발자국(EPD) 결과 → 모세혈관(esgData) 매핑.
import { describe, it, expect } from "vitest";
import { carbonResultToEsgPatch } from "./carbon-result-to-esg-patch";
import type { EsgData } from "@/store/useProjectContextStore";

describe("carbonResultToEsgPatch", () => {
  it("정상 매핑: 총 탄소발자국을 embodiedCarbonKg로 옮기고 기존 esgData(다른 슬롯)는 보존한다", () => {
    const prev: EsgData = {
      embodiedCarbonKg: 100,
      operationalCarbonKg: 500,
      totalCarbonPerSqm: 10,
    };
    const patch = carbonResultToEsgPatch(
      { total_carbon_footprint_kgco2e: 12345 },
      prev,
    );
    expect(patch).toEqual({
      embodiedCarbonKg: 12345, // ★새 계산값으로 갱신
      operationalCarbonKg: 500, // ★full-replace 계약이므로 기존값을 스프레드로 보존해야 함
      totalCarbonPerSqm: 10,
    });
  });

  it("음수/0 생략: 총 탄소발자국이 0이거나 음수/비숫자면 null(SSOT 커밋 안 함, 기존값 오염 방지)", () => {
    const prev: EsgData = { embodiedCarbonKg: 100, operationalCarbonKg: 500, totalCarbonPerSqm: 10 };
    expect(carbonResultToEsgPatch({ total_carbon_footprint_kgco2e: 0 }, prev)).toBeNull();
    expect(carbonResultToEsgPatch({ total_carbon_footprint_kgco2e: -5 }, prev)).toBeNull();
    expect(
      carbonResultToEsgPatch(
        { total_carbon_footprint_kgco2e: Number.NaN },
        prev,
      ),
    ).toBeNull();
    expect(carbonResultToEsgPatch(null, prev)).toBeNull();
    expect(carbonResultToEsgPatch(undefined, prev)).toBeNull();
    expect(carbonResultToEsgPatch({}, prev)).toBeNull();
  });

  it("부분 결측: 기존 esgData가 없으면(null) 나머지 슬롯은 정직하게 null로 채운다(가짜값 날조 금지)", () => {
    const patch = carbonResultToEsgPatch(
      { total_carbon_footprint_kgco2e: 8000 },
      null,
    );
    expect(patch).toEqual({
      embodiedCarbonKg: 8000,
      operationalCarbonKg: null,
      totalCarbonPerSqm: null,
    });
  });
});
