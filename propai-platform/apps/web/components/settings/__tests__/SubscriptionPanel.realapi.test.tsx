/**
 * 요금제 화면의 **숫자가 서버에서 오는가.**
 *
 * ★배경(실측 2026-08-27): 이 패널은 `MOCK_PLAN` 을 렌더했고 그 안의 사용량이
 *   `프로젝트 2/3개 · API 호출 347/500회 · AI 분석 18/30회 · 스토리지 156/500MB`
 * 였다. **백엔드에는 그런 건수 쿼터가 없다** — 과금은 **예산(원) 기반**이다
 * (`/billing/status` → `billed_krw` · `budget_krw` · `remaining_krw` · `usage_pct`).
 *
 * ★과금 화면의 숫자가 허구인 것은 특히 나쁘다 — **사용자가 그것으로 판단한다.**
 * 그래서 지어낸 4행은 지웠고, **서버가 준 값이 없으면 행을 만들지 않는다.**
 *
 * ★가짜 데이터와 정적 문구는 다르다: 플랜 **설명·기능 목록**은 서버가 주지 않는
 * 마케팅 문구라 UI 상수로 남는다. 이 파일은 **숫자**만 잠근다.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api-client", () => {
  class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  }
  return { ApiClientError, apiClient: { get: (...a: unknown[]) => get(...a) } };
});

import { ApiClientError as FakeErr } from "@/lib/api-client";
import { SubscriptionPanel } from "@/components/settings/SubscriptionPanel";

/** ★`public_status` 계약 그대로 — 스텁이 실제보다 좁으면 그 필드를 쓰는 코드가 테스트에서만 터진다. */
const STATUS = {
  tier: "pro",
  tier_label: "프로",
  metered: true,
  fee_krw: 99000,
  included_budget_krw: 200000,
  budget_krw: 200000,
  billed_krw: 51234,
  remaining_krw: 148766,
  usage_pct: 25.6,
  blocked: false,
  service_fee_krw: 0,
};

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue(STATUS);
});

describe("요금제 — 숫자는 서버에서 온다", () => {
  it("★`/billing/status` 를 실제로 부른다(목업이 아니다)", async () => {
    render(<SubscriptionPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(get.mock.calls[0][0]).toBe("/billing/status");
  });

  it("★현재 등급을 **서버가 정한다** — 화면이 고르지 않는다", async () => {
    render(<SubscriptionPanel />);
    // tier="pro" 를 주면 프로가 떠야 한다(목업은 항상 free 였다).
    // ★`/프로/` 는 "프로젝트" 에도 걸린다 — 헤딩 문구로 정확히 집는다.
    expect(await screen.findByText("현재 플랜: 프로")).toBeTruthy();
  });

  it("★두 모집단 — tier 가 다르면 화면도 달라진다", async () => {
    const a = render(<SubscriptionPanel />);
    const proText = await waitFor(() => a.container.textContent ?? "");
    a.unmount();

    get.mockResolvedValue({ ...STATUS, tier: "free", tier_label: "무료" });
    const b = render(<SubscriptionPanel />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    const freeText = b.container.textContent ?? "";
    expect(freeText).not.toBe(proText);
  });

  it("★지어낸 건수 쿼터가 **사용량 영역**에 없다", async () => {
    // ★검사 범위를 사용량 영역으로 좁힌다. 플랜 기능 목록의 "API 호출 월 500회" 는
    //   서버가 주지 않는 **정적 마케팅 문구**이고 가짜 데이터가 아니다 —
    //   범위를 안 나누면 락이 정상 문구를 결함으로 신고한다(첫 실행에서 그랬다).
    render(<SubscriptionPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    const usage = screen.getByTestId("billing-usage").textContent ?? "";
    expect(usage.length, "사용량 영역이 비어 공허한 참이 됐다").toBeGreaterThan(0);
    for (const ghost of ["프로젝트", "API 호출", "AI 분석", "스토리지", "MB"]) {
      expect(usage, `목업 쿼터 '${ghost}' 가 사용량 영역에 살아 있다`).not.toContain(ghost);
    }
  });

  it("★서버가 준 예산 숫자를 그린다", async () => {
    const { container } = render(<SubscriptionPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    const t = container.textContent ?? "";
    expect(t).toContain("51,234"); // billed_krw
    expect(t).toContain("200,000"); // budget_krw
  });

  it("★없는 값은 **행을 만들지 않는다**(0 으로 지어내지 않는다)", async () => {
    // ★첫 판에서 이 케이스는 **단언이 아니라 런타임 크래시**로 rc=1 을 냈다
    //   (`Tests 7 passed · Errors 1`). 크래시로 잡힌 것은 락이 번 것이 아니다 —
    //   구현이 크래시만 피하면(0 을 채우면) 통과한다. **사용량 영역 자체**를 단언한다.
    get.mockResolvedValue({ ...STATUS, billed_krw: null, budget_krw: null, included_budget_krw: null, service_fee_krw: null });
    render(<SubscriptionPanel />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    const region = await screen.findByTestId("billing-usage");
    expect(region.textContent?.trim(), "값이 없는데 사용량 행을 그렸다").toBe("");
  });

  it("★오류를 삼키지 않는다", async () => {
    get.mockRejectedValue(new FakeErr("boom", 500, {}));
    render(<SubscriptionPanel />);
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
