import { describe, expect, it } from "vitest";

import { selectMassTemplate, validMassTemplates, type MassTemplate } from "./mass-template";

const T = (building_type: string, bcr: number | null, far: number | null, n = 1): MassTemplate => ({
  building_type, sample_count: n, median_bcr_pct: bcr, median_far_pct: far, median_floors: 5,
});

describe("validMassTemplates", () => {
  it("건폐·용적 둘 다 유효(>0)한 것만 — 결측/0 제외(가짜 규모 방지)", () => {
    const out = validMassTemplates([
      T("공동주택", null, null),   // 결측 → 제외
      T("업무시설", 60, 600),
      T("창고시설", 13, 0),        // far=0 → 제외
      T("판매시설", 55, 200),
    ]);
    expect(out.map((t) => t.building_type)).toEqual(["업무시설", "판매시설"]);
  });

  it("빈/None 입력은 빈 배열", () => {
    expect(validMassTemplates(null)).toEqual([]);
    expect(validMassTemplates(undefined)).toEqual([]);
    expect(validMassTemplates([])).toEqual([]);
  });
});

describe("selectMassTemplate", () => {
  const valid = [T("업무시설", 60, 600, 72), T("공동주택", 16, 89, 84)];

  it("선택 종류가 있으면 그 템플릿", () => {
    expect(selectMassTemplate(valid, "공동주택")?.building_type).toBe("공동주택");
  });

  it("미선택/미존재 종류면 대표(첫=표본최다)", () => {
    expect(selectMassTemplate(valid, null)?.building_type).toBe("업무시설");
    expect(selectMassTemplate(valid, "없는종류")?.building_type).toBe("업무시설");
  });

  it("유효 템플릿 없으면 null(가짜 생성 금지)", () => {
    expect(selectMassTemplate([], "공동주택")).toBeNull();
  });
});
