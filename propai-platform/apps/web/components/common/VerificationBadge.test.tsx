/**
 * 검증 배지 — **무엇을 검증하는가**를 잠근다 (2026-09-05).
 *
 * ★발단: 성장루프 `recurring_verify_error` 가 `desk_appraisal` 의 '수치불일치'·'내부모순' 을
 *   시간당 5건씩(심각 0) 신고했다. 파고드니 **검증기가 분석을 자기 자신과 대조**하고 있었다 —
 *   이 배지는 `LLM_OUTPUT_KEYS`(손목록 12키)로 source/output 을 가르는데,
 *   `desk_appraisal` 응답은 **최상위 30키 중 그 목록에 걸리는 것이 0개**라
 *   `hasSplit=false` → `source === output` 으로 호출됐다(ast 파생 실측).
 *
 * ★그 결과 두 가지가 났다:
 *   ① `grounded_score`(원본 근거 충실도)가 **구조적으로 공허**한데 화면엔 「근거 N%」로 나갔다
 *   ② 정작 **LLM 서술은 검증 밖**이었다(같은 절 바로 아래 렌더되는데 context 에 없었다)
 *
 * ★이 파일이 잠그는 것: **가를 수 없으면 부르지 않는다**, **생산자가 선언하면 그것을 쓴다**,
 *   그리고 **공허한 수를 화면에 내보내지 않는다**.
 *
 * ★한계(정직 바운딩): 검증 **품질**이 나아지는지는 잠그지 않는다 — LLM 판정이라 라이브
 *   호출이 필요하고 그것은 비용이다. 여기서 잠그는 것은 **무엇이 검증기에 실려 가는가**뿐이다.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();
vi.mock("@/lib/api-client", () => ({ apiClient: { post: (...a: unknown[]) => post(...a) } }));
vi.mock("@/components/growth/FeedbackWidget", () => ({
  FeedbackWidget: () => <div data-testid="feedback-widget" />,
}));

import { VerificationBadge } from "./VerificationBadge";

const OK = { verdict: "pass", grounded_score: 91, issues: [], summary: "", calc_checks: [] };

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue(OK);
  try { window.localStorage.clear(); } catch { /* jsdom */ }
});

/** 계산 전용 — 손목록에 걸리는 키가 하나도 없다(desk_appraisal 의 실제 형태). */
const COMPUTED_ONLY = { appraised_total_won: 1234, official_price_per_sqm: 56, pnu: "11" };
/** 손목록에 걸리는 키를 가진 형태(레거시 폴백이 갈라 주는 경우). */
const WITH_LLM_KEY = { ...COMPUTED_ONLY, ai_interpretation: "이 토지는 …" };

describe("★가를 수 없으면 부르지 않는다", () => {
  it("계산 전용 context 는 검증을 호출하지 않는다 (source===output 방지)", async () => {
    render(<VerificationBadge analysisType="desk_appraisal" context={COMPUTED_ONLY} />);
    await screen.findByTestId("verify-undecidable");
    expect(post).not.toHaveBeenCalled();          // ★호출 0
  });

  it("★음성 대조군 — 목록에 걸리는 키가 있으면 **부른다**(공허한 통과 방지)", async () => {
    render(<VerificationBadge analysisType="desk_appraisal" context={WITH_LLM_KEY} />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const body = (post.mock.calls[0][1] as { body: Record<string, never> }).body as unknown as {
      source: Record<string, unknown>; output: Record<string, unknown>;
    };
    expect(Object.keys(body.output)).toEqual(["ai_interpretation"]);
    expect(body.source).not.toHaveProperty("ai_interpretation");
    expect(body.source).toHaveProperty("appraised_total_won");   // ★두 모집단이 갈렸다
  });
});

describe("★생산자가 선언하면 그것을 쓴다", () => {
  it("output prop 이 있으면 키 이름으로 추측하지 않는다", async () => {
    const narr = { valuation_narrative: "추정 평가 서술", market_position: "시장 포지션 서술" };
    render(<VerificationBadge analysisType="desk_appraisal" context={COMPUTED_ONLY} output={narr} />);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const body = (post.mock.calls[0][1] as { body: unknown }).body as {
      source: Record<string, unknown>; output: Record<string, unknown>;
    };
    expect(body.output).toEqual(narr);                    // ★선언한 것이 실려 나간다
    expect(body.source).toEqual(COMPUTED_ONLY);
    expect(body.source).not.toEqual(body.output);         // ★자기대조가 아니다
  });

  it("빈 output 은 선언으로 치지 않는다 — 폴백으로 내려가고, 갈릴 게 없으면 안 부른다", async () => {
    render(<VerificationBadge analysisType="desk_appraisal" context={COMPUTED_ONLY} output={{}} />);
    await screen.findByTestId("verify-undecidable");
    expect(post).not.toHaveBeenCalled();
  });
});

describe("★공허한 수를 화면에 내보내지 않는다", () => {
  it("판정 불가일 때 「근거 N%」가 렌더되지 않는다", async () => {
    render(<VerificationBadge analysisType="desk_appraisal" context={COMPUTED_ONLY} />);
    await screen.findByTestId("verify-undecidable");
    expect(document.body.textContent || "").not.toMatch(/근거\s*\d+%/);
  });

  it("★라벨 락 — 점수를 보여 줄 때는 **무엇의 비율인지** 말한다", async () => {
    render(<VerificationBadge analysisType="desk_appraisal" context={WITH_LLM_KEY} />);
    await waitFor(() => expect(post).toHaveBeenCalled());
    await waitFor(() => expect(document.body.textContent || "").toContain("AI 서술의 원본 근거"));
    // ★「근거 N%」 단독 표기(무엇의 비율인지 말하지 않는 형태)는 남아 있으면 안 된다.
    expect(document.body.textContent || "").not.toMatch(/(?<!서술의 원본 )근거 \d+%/);
  });
});

describe("★피드백 유입은 줄지 않는다 (§0 이 찾은 회귀 위험)", () => {
  it("판정 불가여도 FeedbackWidget 은 렌더된다", async () => {
    render(<VerificationBadge analysisType="desk_appraisal" context={COMPUTED_ONLY} />);
    await screen.findByTestId("verify-undecidable");
    expect(screen.getByTestId("feedback-widget")).toBeTruthy();
  });
});

// ── ★부채(초록 안에 보이게) ────────────────────────────────────────────────
it.todo("다른 마운트 5곳(report·feasibility·cost·pipeline_report·market)의 실제 분리 여부 — 미측정");
