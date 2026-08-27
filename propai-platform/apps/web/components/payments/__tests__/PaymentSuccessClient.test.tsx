/**
 * 결제 승인 화면 — ★**세 결과를 다르게 말하는가.**
 *
 * 가장 위험한 결함: **미확정을 「실패」로 말하는 것**. 사용자가 다시 결제해서
 * **이중 결제**가 된다. 그래서 이 파일의 핵심 단언은 "오류가 보인다"가 아니라
 * **"세 경우가 서로 다른 화면을 낸다"** 이다(한 모집단 단언은 아무것도 잠그지 않는다).
 *
 * 모킹 관례는 `components/mypage/__tests__/CoinsClient.test.tsx` 를 따른다.
 */

import { StrictMode } from "react";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("@/lib/api-client", () => {
  class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.name = "ApiClientError";
      this.status = status;
      this.payload = payload;
    }
  }
  return { ApiClientError, apiClient: { post: (...a: unknown[]) => post(...a) } };
});

import { ApiClientError as FakeErr } from "@/lib/api-client";
import { PaymentSuccessClient } from "@/components/payments/PaymentSuccessClient";

const PROPS = {
  locale: "ko" as const,
  orderId: "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
  paymentKey: "pk_test_abc123",
  amount: "50000",
};

/** 서버가 돌려주는 구조화 오류(우리 계약 그대로 — 스텁이 좁으면 테스트에서만 통과한다). */
const detailErr = (outcome: string, extra: Record<string, unknown> = {}) =>
  new FakeErr("API 요청 처리에 실패했습니다.", 409, {
    detail: {
      code: outcome === "pending" ? "WAITING_FOR_DEPOSIT" : "PAYMENT_UNRESOLVED",
      message: `${outcome} 상태 메시지`,
      remediation: `${outcome} 상태 조치`,
      outcome,
      ...extra,
    },
  });

beforeEach(() => {
  post.mockReset();
  window.history.replaceState(null, "", "/ko/mypage/coins/success?orderId=x&paymentKey=y");
});

describe("결제 승인 화면", () => {
  it("★서버에 승인을 **한 번만** 요청한다(중복 승인 유도 금지)", async () => {
    post.mockResolvedValue({ order_no: "CO20260827-AAAA", coin_krw: 50000 });
    // ★**StrictMode 로 렌더한다.** 기본 `render` 는 effect 를 한 번만 돌려서
    //   `sent.current` 가드를 지우는 변이가 **SURVIVED** 했다(실측 2026-08-27).
    //   Next.js 개발 모드는 StrictMode 라 실제로는 두 번 돈다 — 그 조건을 만들어서 잰다.
    render(
      <StrictMode>
        <PaymentSuccessClient {...PROPS} />
      </StrictMode>,
    );
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][0]).toBe("/billing/payments/toss/confirm");
    expect(post.mock.calls[0][1]).toMatchObject({
      body: { order_id: PROPS.orderId, payment_key: PROPS.paymentKey, amount: 50000 },
    });
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("★결제 식별자를 URL 에서 **즉시 지운다**", async () => {
    post.mockResolvedValue({ order_no: "CO1", coin_krw: 1000 });
    render(<PaymentSuccessClient {...PROPS} />);
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(window.location.search, "★paymentKey 가 URL 에 남았다").toBe("");
  });

  it("승인되면 금액과 주문번호를 보여 준다", async () => {
    post.mockResolvedValue({ order_no: "CO20260827-BBBB", coin_krw: 50000 });
    render(<PaymentSuccessClient {...PROPS} />);
    expect(await screen.findByTestId("payment-done")).toBeTruthy();
    expect(screen.getByText("CO20260827-BBBB")).toBeTruthy();
    expect(screen.getByText(/50,000원/)).toBeTruthy();
  });

  it("★세 결과가 **서로 다른 화면**을 낸다(뭉치면 이중결제를 부른다)", async () => {
    // ① 거절
    post.mockRejectedValue(detailErr("rejected"));
    const a = render(<PaymentSuccessClient {...PROPS} />);
    await screen.findByTestId("payment-error");
    const rejectedText = a.container.textContent ?? "";
    a.unmount();

    // ② 보류(가상계좌)
    post.mockRejectedValue(detailErr("pending"));
    const b = render(<PaymentSuccessClient {...PROPS} />);
    await screen.findByTestId("payment-error");
    const pendingText = b.container.textContent ?? "";
    b.unmount();

    // ③ 미확정
    post.mockRejectedValue(detailErr("unresolved"));
    const c = render(<PaymentSuccessClient {...PROPS} />);
    await screen.findByTestId("payment-error");
    const unresolvedText = c.container.textContent ?? "";

    expect(rejectedText).not.toBe(pendingText);
    expect(pendingText).not.toBe(unresolvedText);
    expect(rejectedText).not.toBe(unresolvedText);
    // ★미확정에서는 **중복 결제 경고**가 반드시 있어야 한다.
    expect(unresolvedText).toContain("중복 결제하지 마세요");
    expect(rejectedText).not.toContain("중복 결제하지 마세요");
  });

  it("★조치가 화면에 **실제로 렌더**된다(사유만 있고 조치가 없으면 반쪽)", async () => {
    post.mockRejectedValue(detailErr("rejected"));
    render(<PaymentSuccessClient {...PROPS} />);
    const el = await screen.findByTestId("payment-remediation");
    expect(el.textContent).toBe("rejected 상태 조치");
  });

  it("파라미터가 없으면 승인을 **보내지 않고** 안내한다", async () => {
    render(<PaymentSuccessClient {...PROPS} paymentKey={null} />);
    expect(await screen.findByTestId("payment-error")).toBeTruthy();
    expect(post).not.toHaveBeenCalled();
  });

  it("이미 처리된 결제는 **중복 충전이 아니라고** 말한다", async () => {
    post.mockResolvedValue({ order_no: "CO1", coin_krw: 1000, already_applied: true });
    render(<PaymentSuccessClient {...PROPS} />);
    expect(await screen.findByText(/중복 충전되지 않았습니다/)).toBeTruthy();
  });
});
