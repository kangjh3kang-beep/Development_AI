import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  toConstructionCostAreas,
  toEsgGrossFloorAreaSqm,
  toFeasibilityModuleInput,
} from "@/lib/building-overview-adapters";
import {
  type BuildingOverview,
  deriveBcrPct,
  deriveFarPct,
  deriveTotalGfaSqm,
  emptyBuildingOverview,
  sumGfaByUse,
  makeUseLine,
  validateBuildingOverview,
} from "@/lib/building-overview";

const base = (p: Partial<BuildingOverview> = {}): BuildingOverview => ({
  ...emptyBuildingOverview(),
  ...p,
});

describe("정본 스키마", () => {
  it("★용적률·건폐율은 **필드가 아니다**(저장하면 원본과 갈린다)", () => {
    const keys = Object.keys(emptyBuildingOverview());
    for (const forbidden of ["farPct", "bcrPct", "far", "bcr", "totalGfaSqm"]) {
      expect(keys, `${forbidden} 가 필드로 있다`).not.toContain(forbidden);
    }
    // ★대조군 — 있어야 할 필드는 있다(위 단언이 「필드가 없다」로 공허해지지 않게)
    expect(keys).toEqual(
      expect.arrayContaining(["landAreaSqm", "aboveGroundGfaSqm", "basementGfaSqm", "uses"]),
    );
  });

  it("★지상/지하가 **나뉘어 있다** — 이 구분이 이 작업의 출발점이다", () => {
    const keys = Object.keys(emptyBuildingOverview());
    expect(keys).toContain("aboveGroundGfaSqm");
    expect(keys).toContain("basementGfaSqm");
  });
});

describe("파생 계산 — 두 모집단", () => {
  it("★용적률은 **지상만** 센다(지하 제외 · 건축법 시행령 §119)", () => {
    // 유일하게 가르는 입력: 지하만 다른 두 개요
    const a = base({ landAreaSqm: 1000, aboveGroundGfaSqm: 2000, basementGfaSqm: 0 });
    const b = base({ landAreaSqm: 1000, aboveGroundGfaSqm: 2000, basementGfaSqm: 5000 });
    expect(deriveFarPct(a)).toBe(200);
    expect(deriveFarPct(b)).toBe(200); // ★지하가 5000 늘어도 용적률은 불변
    // 대조군 — 지상이 바뀌면 값이 바뀐다(위 단언이 「항상 200」으로 공허하지 않게)
    expect(deriveFarPct(base({ landAreaSqm: 1000, aboveGroundGfaSqm: 3000 }))).toBe(300);
  });

  it("★못 재면 null — 0 이 아니다", () => {
    expect(deriveFarPct(base({ landAreaSqm: 1000 }))).toBeNull(); // 지상 모름
    expect(deriveFarPct(base({ aboveGroundGfaSqm: 2000 }))).toBeNull(); // 대지 모름
    expect(deriveFarPct(base({ landAreaSqm: 0, aboveGroundGfaSqm: 2000 }))).toBeNull(); // 0 대지
    expect(deriveBcrPct(base({ landAreaSqm: 1000 }))).toBeNull();
    expect(deriveTotalGfaSqm(base())).toBeNull();
    expect(sumGfaByUse(base())).toBeNull(); // ★빈 구성은 0 이 아니라 null
  });

  it("건폐율", () => {
    expect(deriveBcrPct(base({ landAreaSqm: 1000, buildingAreaSqm: 400 }))).toBe(40);
  });

  it("★전체 연면적 — 하나만 알면 아는 쪽만 더한다", () => {
    expect(deriveTotalGfaSqm(base({ aboveGroundGfaSqm: 2000 }))).toBe(2000);
    expect(deriveTotalGfaSqm(base({ basementGfaSqm: 500 }))).toBe(500);
    expect(deriveTotalGfaSqm(base({ aboveGroundGfaSqm: 2000, basementGfaSqm: 500 }))).toBe(2500);
  });
});

describe("용도 줄 — 원본 보존", () => {
  it("★정규화 전 문자열을 남긴다(정규화가 차이를 지우지 않게)", () => {
    const line = makeUseLine("아파트", 1200, { unitCount: 20 });
    expect(line).not.toBeNull();
    expect(line!.use).toBe("apartment");
    expect(line!.rawUse).toBe("아파트"); // ★원본
    expect(line!.avgExclusiveSqm).toBeNull(); // 미입력은 null
  });

  it("★모르는 용도는 줄을 만들지 않는다(임의 코드로 떨어뜨리지 않는다)", () => {
    expect(makeUseLine("토지", 100)).toBeNull();
    expect(makeUseLine("기타", 100)).toBeNull();
  });
});

describe("검증 — 모순만 신고한다", () => {
  it("부분 입력은 문제가 아니다", () => {
    expect(validateBuildingOverview(base({ landAreaSqm: 1000 }))).toEqual([]);
  });

  it("★용도별 합이 전체를 넘으면 신고", () => {
    const o = base({
      aboveGroundGfaSqm: 1000,
      uses: [makeUseLine("공동주택", 900)!, makeUseLine("상가", 300)!],
    });
    expect(validateBuildingOverview(o).map((i) => i.field)).toContain("uses");
  });

  it("★부동소수 오차를 위반으로 신고하지 않는다", () => {
    const o = base({
      aboveGroundGfaSqm: 1000,
      uses: [makeUseLine("공동주택", 1000.2)!],
    });
    expect(validateBuildingOverview(o)).toEqual([]);
  });

  it("건축면적 > 대지면적 이면 신고", () => {
    const o = base({ landAreaSqm: 500, buildingAreaSqm: 600 });
    expect(validateBuildingOverview(o).map((i) => i.field)).toContain("buildingAreaSqm");
  });
});

describe("어댑터 — 소비처 규약을 지킨다", () => {
  it("★공사비: 모르면 **null**(0 을 채우면 공사비가 0원으로 조용히 틀린다)", () => {
    expect(toConstructionCostAreas(base())).toBeNull();
    const got = toConstructionCostAreas(
      base({ aboveGroundGfaSqm: 2000, uses: [makeUseLine("공동주택", 2000)!] }),
    );
    // ★★2026-09-12 정정 — 종전 이 줄은 `buildingUse: "공동주택"` 을 단언해 **틀린 값을 잠갔다**.
    //   소비처(`kr-construction-cost.BASE_COST_PER_SQM`)의 키는 **영문**이라 한국어 라벨은
    //   조회에 **HIT 0/11** 이었고 전 용도가 아파트 단가로 접혔다. 단언이 결함을 보호한 셈이다.
    //   ★도메인 자체의 잠금은 `building-use-roundtrip.contract.test.ts` 가 **소비처 파일에서
    //     키를 파생해** 대조한다 — 여기서 문자열을 한 번 더 적으면 그것이 또 상한이 된다.
    expect(got).toEqual({ totalFloorArea: 2000, buildingUse: "apartment" });
  });

  it("★ESG: 그쪽은 **문자열**이고 빈 문자열이 미입력이다", () => {
    expect(toEsgGrossFloorAreaSqm(base())).toBe("");
    expect(toEsgGrossFloorAreaSqm(base({ aboveGroundGfaSqm: 1500 }))).toBe("1500");
  });

  it("★수지 폼: 모름을 null 로 넘겨 0 과 구별한다", () => {
    expect(toFeasibilityModuleInput(base())).toEqual({
      total_land_area_sqm: null,
      total_gfa_sqm: null,
    });
    expect(
      toFeasibilityModuleInput(base({ landAreaSqm: 800, aboveGroundGfaSqm: 1600 })),
    ).toEqual({ total_land_area_sqm: 800, total_gfa_sqm: 1600 });
  });

  it("★어댑터가 소비처의 **실제 필드명**을 쓰는지 원천 파일로 확인한다", () => {
    const web = path.resolve(__dirname, "..", "..");
    const cost = fs.readFileSync(path.join(web, "lib/kr-construction-cost.ts"), "utf-8");
    expect(cost, "소비처가 totalFloorArea 를 안 쓴다 — 어댑터 이름이 낡았다").toContain(
      "totalFloorArea: number;",
    );
    const esg = fs.readFileSync(path.join(web, "lib/esg-extended-panels.ts"), "utf-8");
    expect(esg).toContain("grossFloorAreaSqm: string;");
  });
});
