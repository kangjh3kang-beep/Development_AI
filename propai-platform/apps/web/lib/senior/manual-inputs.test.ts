import { describe, expect, it } from "vitest";

import {
  coerceManualInputs,
  hasManualInputs,
  mergeSeniorInputs,
} from "./manual-inputs";

describe("hasManualInputs", () => {
  it("법무사·감정평가사·도시계획은 수동 입력 필드 보유", () => {
    expect(hasManualInputs("senior_legal_scrivener")).toBe(true);
    expect(hasManualInputs("senior_appraiser")).toBe(true);
    expect(hasManualInputs("senior_urban_planner")).toBe(true);
  });
  it("수동 필드 없는 도메인은 false", () => {
    expect(hasManualInputs("senior_financial_advisor")).toBe(false);
    expect(hasManualInputs("unknown")).toBe(false);
  });
});

describe("도시계획 비례율 수동 입력", () => {
  it("종전평가(분모)·권리가액·분담금 필드 → 수치 변환(미입력 생략)", () => {
    const r = coerceManualInputs("senior_urban_planner", {
      prior_appraisal_total: "10000000000",
      prior_appraisal_individual: "500000000",
      member_sale_price: "600000000",
      post_appraisal_total: "",   // 미입력 → 생략(수지 자동값 사용)
      total_project_cost: "",     // 미입력 → 생략
    });
    expect(r).toEqual({
      prior_appraisal_total: 10_000_000_000,
      prior_appraisal_individual: 500_000_000,
      member_sale_price: 600_000_000,
    });
  });

  it("★수지(store) 자동값이 수동 종후/총사업비를 덮어씀(SSOT) — 분모만 수동 보완", () => {
    // 수지 미실행 시: 수동 종후/총사업비 사용. 실행 시: store 우선(자동값)으로 비례율 활성.
    const manual = coerceManualInputs("senior_urban_planner", {
      prior_appraisal_total: "10000000000",
      post_appraisal_total: "1",       // 수지 실행 시 무시될 폴백
      total_project_cost: "1",
    });
    const merged = mergeSeniorInputs(
      { post_appraisal_total: 12_000_000_000, total_project_cost: 9_000_000_000 }, // store(자동)
      manual,
    );
    expect(merged).toEqual({
      prior_appraisal_total: 10_000_000_000,     // 수동(분모 — store 미보유)
      post_appraisal_total: 12_000_000_000,      // store 우선
      total_project_cost: 9_000_000_000,         // store 우선
    });
  });
});

describe("coerceManualInputs", () => {
  it("number: 유한수만 통과·빈값/비수치 생략(미입력)", () => {
    const r = coerceManualInputs("senior_legal_scrivener", {
      senior_liens_total: "300000000",
      consent_owner_count: "",      // 미입력 → 생략
      total_owner_count: "abc",     // 비수치 → 생략
    });
    expect(r).toEqual({ senior_liens_total: 300_000_000 });
  });

  it("number 0도 유효(명시 0 보존)", () => {
    expect(coerceManualInputs("senior_legal_scrivener", { senior_liens_total: "0" })).toEqual({
      senior_liens_total: 0,
    });
  });

  it("select(문자열)·boolean 변환", () => {
    const r = coerceManualInputs("senior_legal_scrivener", {
      redevelopment_type: "재건축",
      building_consent_majority: "true",
    });
    expect(r).toEqual({ redevelopment_type: "재건축", building_consent_majority: true });
  });

  it("boolean 미입력(빈)·false 정확 처리", () => {
    expect(coerceManualInputs("senior_legal_scrivener", { building_consent_majority: "" })).toEqual(
      {},
    );
    expect(
      coerceManualInputs("senior_legal_scrivener", { building_consent_majority: "false" }),
    ).toEqual({ building_consent_majority: false });
  });

  it("raw 전체 미입력 → 빈 객체", () => {
    expect(coerceManualInputs("senior_legal_scrivener", undefined)).toEqual({});
  });
});

describe("mergeSeniorInputs", () => {
  it("store 자동매핑 + 수동 입력 병합", () => {
    const merged = mergeSeniorInputs(
      { appraised_value: 1_000_000_000 },
      { senior_liens_total: 300_000_000, redevelopment_type: "재개발" },
    );
    expect(merged).toEqual({
      appraised_value: 1_000_000_000,
      senior_liens_total: 300_000_000,
      redevelopment_type: "재개발",
    });
  });

  it("★store 값 우선(SSOT) — store가 보유하면 수동을 덮어씀", () => {
    // 합성 충돌(실제 키 네임스페이스는 겹치지 않음 — legal 수동엔 appraised_value 없음).
    //   merge primitive의 우선순위(향후 store 보유 시 자동매핑 우선)만 검증한다.
    const merged = mergeSeniorInputs(
      { appraised_value: 900_000_000 }, // store(자동)
      { appraised_value: 100 },         // 수동(보완)
    );
    expect(merged?.appraised_value).toBe(900_000_000);
  });

  it("둘 다 비면 undefined(프레임워크만)", () => {
    expect(mergeSeniorInputs(undefined, {})).toBeUndefined();
  });

  it("store만 있어도 병합 결과 반환", () => {
    expect(mergeSeniorInputs({ appraised_value: 5 }, {})).toEqual({ appraised_value: 5 });
  });
});
