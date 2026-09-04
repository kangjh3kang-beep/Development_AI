/**
 * 기성 청구기간 파생 헬퍼 테스트 — 백엔드 계약(period_from/period_to, DATE) 폐루프 고정.
 * 월 입력("2026-06") → "2026-06-01" ~ "2026-06-30" 파생이 핵심 회귀 지점이다.
 */
import { describe, expect, it } from "vitest";
import { deriveBillingPeriod } from "./billing-period";

describe("deriveBillingPeriod — 기성 청구기간 파생", () => {
  it("월 입력(2026-06) → 해당 월 1일~말일", () => {
    expect(deriveBillingPeriod("2026-06")).toEqual({
      period_from: "2026-06-01",
      period_to: "2026-06-30",
    });
  });

  it("31일 달·2월·윤년 말일을 정확히 계산한다", () => {
    expect(deriveBillingPeriod("2026-07")?.period_to).toBe("2026-07-31");
    expect(deriveBillingPeriod("2026-02")?.period_to).toBe("2026-02-28");
    expect(deriveBillingPeriod("2028-02")?.period_to).toBe("2028-02-29");
  });

  it("한 자리 월(2026-6)·공백 입력도 0채움으로 정규화한다", () => {
    expect(deriveBillingPeriod(" 2026-6 ")).toEqual({
      period_from: "2026-06-01",
      period_to: "2026-06-30",
    });
  });

  it("일 단위 입력(2026-06-15) → 하루 범위", () => {
    expect(deriveBillingPeriod("2026-06-15")).toEqual({
      period_from: "2026-06-15",
      period_to: "2026-06-15",
    });
  });

  it("명시 범위(목록 표시 형식 'A ~ B') 재입력을 지원한다", () => {
    expect(deriveBillingPeriod("2026-06-01 ~ 2026-06-30")).toEqual({
      period_from: "2026-06-01",
      period_to: "2026-06-30",
    });
    expect(deriveBillingPeriod("2026-06 ~ 2026-08")).toEqual({
      period_from: "2026-06-01",
      period_to: "2026-08-31",
    });
  });

  it("형식 오류·빈 값·존재하지 않는 날짜·역순 범위는 null", () => {
    expect(deriveBillingPeriod("")).toBeNull();
    expect(deriveBillingPeriod("2026")).toBeNull();
    expect(deriveBillingPeriod("2026-13")).toBeNull();
    expect(deriveBillingPeriod("2026-06-31")).toBeNull();
    expect(deriveBillingPeriod("06-2026")).toBeNull();
    expect(deriveBillingPeriod("2026-08 ~ 2026-06")).toBeNull();
    expect(deriveBillingPeriod("~ 2026-06")).toBeNull();
  });
});
