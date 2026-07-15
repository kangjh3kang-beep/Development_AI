/**
 * P4②(2026-07-15 감사) 회귀 테스트 — with_senior(K-IFRS 자문) opt-in 배선.
 *
 * 배경: 백엔드 /feasibility/calculate가 senior_accountant_review를 채우지만
 * 프론트가 with_senior를 어디서도 보내지 않아(적산 엔드포인트만 전송) K-IFRS·세무
 * 자문이 화면에 영원히 도달 불가한 완전 고아였다.
 *
 * 계약:
 * 1. 기본값 false(LLM 비용 opt-in — 과금 정책: 선택분만 실행·과금).
 * 2. setWithSenior(true) 후 calculate → 요청 바디에 with_senior: true.
 * 3. 기본 상태 calculate → with_senior: false (무회귀: 비용 미발생).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    postV2: vi.fn(),
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import { apiClient } from "@/lib/api-client";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";

const FAKE_RESULT = {
  development_type: "M06",
  module_name: "일반분양",
  total_revenue_won: 1,
  total_cost_won: 1,
  net_profit_won: 0,
  profit_rate_pct: 0,
  roi_pct: 0,
  npv_won: 0,
  grade: "C",
  cost_breakdown_won: {},
  tax_detail: {},
  special_detail: {},
  senior_accountant_review: { verdict: "PASS", consultations: [{ agent_key: "senior_accountant" }] },
};

describe("with_senior opt-in 배선 (P4②)", () => {
  beforeEach(() => {
    vi.mocked(apiClient.postV2).mockReset();
    vi.mocked(apiClient.postV2).mockResolvedValue(FAKE_RESULT);
    useFeasibilityV2Store.getState().reset();
  });

  it("기본값은 false — 과금 opt-in 정책(무회귀: 미체크 시 비용 미발생)", () => {
    expect(useFeasibilityV2Store.getState().withSenior).toBe(false);
  });

  it("기본 상태 calculate는 with_senior: false 전송", async () => {
    await useFeasibilityV2Store.getState().calculate();
    const [, opts] = vi.mocked(apiClient.postV2).mock.calls[0];
    expect((opts as { body: Record<string, unknown> }).body.with_senior).toBe(false);
  });

  it("★R1-P1: 토글 true여도 자동 경로 override(withSenior:false)가 우선 — 무동의 반복 과금 차단", async () => {
    useFeasibilityV2Store.getState().setWithSenior(true);
    await useFeasibilityV2Store.getState().calculate({ withSenior: false });
    const [, opts] = vi.mocked(apiClient.postV2).mock.calls[0];
    expect((opts as { body: Record<string, unknown> }).body.with_senior).toBe(false);
  });

  it("reset()은 withSenior도 초기화(false) — 테스트 격리·초기 복귀 일관성", () => {
    useFeasibilityV2Store.getState().setWithSenior(true);
    useFeasibilityV2Store.getState().reset();
    expect(useFeasibilityV2Store.getState().withSenior).toBe(false);
  });

  it("setWithSenior(true) 후 calculate는 with_senior: true 전송 + 자문이 result에 적재", async () => {
    useFeasibilityV2Store.getState().setWithSenior(true);
    await useFeasibilityV2Store.getState().calculate();
    const [path, opts] = vi.mocked(apiClient.postV2).mock.calls[0];
    expect(path).toBe("/feasibility/calculate");
    expect((opts as { body: Record<string, unknown> }).body.with_senior).toBe(true);
    // 응답의 자문이 store.result까지 도달(최종 표면 SeniorVerdictCard가 이 필드를 소비).
    const review = useFeasibilityV2Store.getState().result?.senior_accountant_review as
      | { verdict?: string }
      | undefined;
    expect(review?.verdict).toBe("PASS");
  });
});
