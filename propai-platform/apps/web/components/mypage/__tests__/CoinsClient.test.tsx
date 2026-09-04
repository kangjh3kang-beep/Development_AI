import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CoinsClient } from "@/components/mypage/CoinsClient";
import { apiClient } from "@/lib/api-client";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ko/mypage/coins",
}));

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
  apiV1BaseUrl: () => "http://test/api/v1",
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

const PACKAGES = {
  packages: [
    { key: "starter", amount_krw: 10000, label: "스타터 1만원" },
    { key: "max", amount_krw: 300000, label: "맥스 30만원" },
  ],
  custom: { min_krw: 1000, max_krw: 1000000, unit_krw: 100 },
};

function mockGets(overrides: Record<string, unknown> = {}) {
  vi.mocked(apiClient.get).mockImplementation(async (path: string) => {
    if (path.startsWith("/billing/packages"))
      return { ...PACKAGES, payment_mode: overrides["payment_mode"] ?? "manual_only" };
    if (path.startsWith("/billing/ledger/verify")) return overrides["verify"] ?? { ok: true, count: 3 };
    if (path.startsWith("/billing/orders")) {
      if (overrides["ordersReject"]) throw new Error("boom");
      return overrides["orders"] ?? { orders: [] };
    }
    if (path.startsWith("/billing/ledger")) {
      if (overrides["ledgerReject"]) throw new Error("boom");
      return overrides["ledger"] ?? { items: [] };
    }
    return {};
  });
}

describe("CoinsClient", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("주문 생성 시 package_key만 보낸다(금액은 서버 결정 — 프리셋에 amount 미포함)", async () => {
    mockGets();
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "o1",
      order_no: "CO20260717-TEST",
      status: "pending",
      payment_mode: "manual_only",
    });

    render(<CoinsClient locale="ko" />);
    await screen.findByText("스타터 1만원");
    await userEvent.click(screen.getByRole("button", { name: "충전 주문 만들기" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/billing/orders",
        expect.objectContaining({ body: { package_key: "starter" }, useMock: false }),
      );
    });
    // PG 미연동(manual_only) 정직 안내 — 계좌이체·관리자 확인 경로 고지.
    expect(await screen.findByText(/계좌이체 후 관리자 확인/)).toBeInTheDocument();
  });

  const PENDING_ORDER = {
    id: "o1",
    order_no: "CO1",
    amount_krw: 10000,
    coin_krw: 10000,
    status: "pending",
    provider: null,
    created_at: "2026-07-17T00:00:00Z",
    paid_at: null,
  };

  it("프로덕션(manual_only)에서는 '결제 완료 처리' 버튼을 감춘다(죽은 버튼 제거)", async () => {
    mockGets({ orders: { orders: [PENDING_ORDER] }, payment_mode: "manual_only" });
    render(<CoinsClient locale="ko" />);
    // 주문번호는 렌더되지만 self-confirm 버튼은 없어야 한다(취소 버튼만).
    await screen.findByText("CO1");
    expect(screen.queryByRole("button", { name: /결제 완료 처리/ })).toBeNull();
    expect(screen.getByRole("button", { name: "취소" })).toBeInTheDocument();
  });

  it("시뮬레이션 모드에서 '(데모) 결제 완료 처리' 확정 실패(501)를 정직하게 보여준다", async () => {
    const { ApiClientError } = await import("@/lib/api-client");
    mockGets({ orders: { orders: [PENDING_ORDER] }, payment_mode: "simulated" });
    vi.mocked(apiClient.post).mockRejectedValue(
      new (ApiClientError as new (m: string, s: number, p: unknown) => Error)(
        "Not Implemented",
        501,
        { detail: "온라인 결제 연동 준비 중입니다." },
      ),
    );

    render(<CoinsClient locale="ko" />);
    await userEvent.click(await screen.findByRole("button", { name: /데모.*결제 완료 처리/ }));
    expect(await screen.findByText(/온라인 결제 연동 준비 중/)).toBeInTheDocument();
  });

  it("조회 실패를 '내역 없음'이 아닌 오류로 표시한다(거짓 성공 위장 방지)", async () => {
    mockGets({ ordersReject: true, ledgerReject: true });
    render(<CoinsClient locale="ko" />);
    expect(await screen.findByText(/결제내역을 불러오지 못했습니다/)).toBeInTheDocument();
    expect(screen.getByText(/코인내역을 불러오지 못했습니다/)).toBeInTheDocument();
    expect(screen.queryByText("결제(주문) 내역이 없습니다.")).toBeNull();
    expect(screen.queryByText("코인내역이 없습니다.")).toBeNull();
  });

  it("'충전' 필터가 charge 그룹으로 조회한다(topup+order_paid 병합)", async () => {
    mockGets();
    render(<CoinsClient locale="ko" />);
    await screen.findByText("스타터 1만원");
    await userEvent.click(screen.getByRole("button", { name: "충전" }));
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith(
        expect.stringContaining("entry_type=charge"),
        expect.objectContaining({ useMock: false }),
      );
    });
  });

  it("무결성 확인 버튼이 해시체인 검증 결과를 표시한다", async () => {
    mockGets({ verify: { ok: true, count: 7 } });
    render(<CoinsClient locale="ko" />);
    await screen.findByText("스타터 1만원");
    await userEvent.click(screen.getByRole("button", { name: "내역 무결성 확인" }));
    expect(await screen.findByText(/위·변조 없음 확인\(기록 7건/)).toBeInTheDocument();
  });
});
