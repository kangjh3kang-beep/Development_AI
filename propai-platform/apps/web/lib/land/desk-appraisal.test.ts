import { describe, it, expect } from "vitest";
import {
  deskToSiteSummary,
  eok,
  won,
  type DeskAppraisalResult,
} from "@/lib/land/desk-appraisal";

/**
 * 탁상감정 → 부지분석 요약 어댑터(deskToSiteSummary) 계약 고정.
 *
 * 핵심 회귀 앵커: 추정 토지가치는 반드시 `appraised_total_won` 에서 온다.
 * (구 land_price 라우터의 잠복 결함 = 존재하지 않는 `final_value_won` 키를 읽어 None 적재.)
 */

/** DeskAppraisalResult 최소 성공 픽스처 + 부분 오버라이드. */
function result(partial: Partial<DeskAppraisalResult> = {}): DeskAppraisalResult {
  return {
    ok: true,
    appraised_price_per_sqm: 3_000_000,
    appraised_total_won: 1_500_000_000,
    area_sqm: 500,
    confidence: 0.82,
    range_per_sqm: { low: 2_700_000, high: 3_300_000 },
    methods: [
      { method: "공시지가 기준 추정", unit_price: 2_900_000, rationale: "개별공시지가×보정" },
      { method: "실거래 비교 추정", unit_price: 3_100_000, rationale: "주변 실거래 평균단가" },
    ],
    weight_note: "공시지가기준·거래사례 가중 채택",
    disclaimer: "참고용 추정(감정평가 아님)",
    ...partial,
  };
}

describe("deskToSiteSummary — 매핑 계약", () => {
  it("추정 토지가치는 appraised_total_won 에서 온다 (★final_value_won 오키 회귀 앵커)", () => {
    const r = result({ appraised_total_won: 2_100_000_000 });
    const s = deskToSiteSummary(r);
    expect(s.estimatedTotalWon).toBe(2_100_000_000);
    // 응답에 존재하지 않는 final_value_won 키에 의존하지 않음을 명시적으로 고정.
    expect((r as unknown as Record<string, unknown>).final_value_won).toBeUndefined();
  });

  it("단가·신뢰도·범위·교차검증·출처·면책을 그대로 매핑", () => {
    const cross = { firms: [2_800_000, 3_000_000, 3_200_000], mean: 3_000_000, cv_pct: 6.7, min: 2_800_000, max: 3_200_000, note: "3시나리오" };
    const s = deskToSiteSummary(result({ cross_check: cross, source: "공개데이터" }));
    expect(s.pricePerSqm).toBe(3_000_000);
    expect(s.confidence).toBe(0.82);
    expect(s.rangePerSqm).toEqual({ low: 2_700_000, high: 3_300_000 });
    expect(s.crossCheck).toEqual(cross);
    expect(s.source).toBe("공개데이터");
    expect(s.disclaimer).toBe("참고용 추정(감정평가 아님)");
    expect(s.methods).toHaveLength(2);
    expect(s.methods[0].method).toBe("공시지가 기준 추정");
  });
});

describe("deskToSiteSummary — null 가드(무목업·0 강제 금지)", () => {
  it("appraised_total_won 이 null 이면 estimatedTotalWon 도 null (0 강제 금지)", () => {
    const s = deskToSiteSummary(result({ appraised_total_won: null }));
    expect(s.estimatedTotalWon).toBeNull();
  });

  it("cross_check 부재 시 crossCheck=null", () => {
    const r = result();
    delete (r as Partial<DeskAppraisalResult>).cross_check;
    expect(deskToSiteSummary(r).crossCheck).toBeNull();
  });

  it("source 부재 시 source=null", () => {
    const r = result();
    delete (r as Partial<DeskAppraisalResult>).source;
    expect(deskToSiteSummary(r).source).toBeNull();
  });

  it("methods 가 배열이 아니면 빈 배열로 정규화", () => {
    const r = result();
    (r as unknown as { methods: unknown }).methods = undefined;
    expect(deskToSiteSummary(r).methods).toEqual([]);
  });
});

describe("금액 포매터 — 로케일 고정(프론트 변이 감사 적발)", () => {
  // ★`eok`/`won` 은 로케일만 고치고 **동작 테스트가 없었다** — 변이로 지워도 통과했다.
  //   화면 헤드라인 금액이라 표기가 깨지면 바로 보인다.
  it("억 단위는 ko-KR 서식으로 소수 2자리까지", () => {
    expect(eok(1_234_567_890)).toBe("12.35억");
    expect(eok(100_000_000)).toBe("1억");
    // ★두 모집단을 가른다 — null 은 값이 아니라 "모른다"다.
    expect(eok(null)).toBe("—");
    expect(eok(undefined)).toBe("—");
  });

  it("원 단위는 천단위 구분자와 함께", () => {
    expect(won(1_234_567)).toBe("1,234,567원");
    expect(won(0)).toBe("0원");
    expect(won(null)).toBe("—");
  });
});
