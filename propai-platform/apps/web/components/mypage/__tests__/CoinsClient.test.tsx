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
      return {
        ...PACKAGES,
        payment_mode: overrides["payment_mode"] ?? "manual_only",
        // ★기본은 **주지 않는다** — 구 서버(배포 창)를 재현한다. 그 상태에서도
        //   결제 버튼이 사라지면 안 된다(`methodsFromResponse` 폴백이 그것을 지킨다).
        ...(overrides["payment_methods"]
          ? { payment_methods: overrides["payment_methods"] }
          : {}),
      };
    if (path.startsWith("/billing/payments/bank-transfer/config"))
      return overrides["bank"] ?? { enabled: false, account: null, guide: null, notice: null };
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
    // ★수단이 하나도 없을 때의 정직 안내.
    //   종전 문구는 *"계좌이체 후 관리자 확인"* 이라 말하면서 **어느 계좌인지 말하지 않았다** —
    //   사용자가 그 문장으로 할 수 있는 일이 없었다. 계좌가 없으면 그 사실을 말한다.
    expect(await screen.findByText(/결제 수단이 아직 설정되지 않아/)).toBeInTheDocument();
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

  // ══════════════════════════════════════════════════════════════════════
  // 무통장입금 — ★부분 정보로 안내하면 사용자가 **엉뚱한 곳으로 송금**한다
  // ══════════════════════════════════════════════════════════════════════
  const BANK_ON = {
    enabled: true,
    account: { bank_name: "새마을금고", account_no: "9002148908909", holder: "예금주" },
    guide: "입금자명은 주문에 적은 이름과 같아야 합니다.",
    notice: "관리자 승인 후 충전됩니다.",
  };

  it("무통장입금이 켜지면 은행·계좌·예금주를 **전부** 보여준다", async () => {
    mockGets({ payment_methods: ["bank_transfer"], payment_mode: "bank_transfer", bank: BANK_ON });
    render(<CoinsClient locale="ko" />);
    expect(await screen.findByTestId("bank-account-no")).toHaveTextContent("9002148908909");
    expect(screen.getByTestId("bank-name")).toHaveTextContent("새마을금고");
    expect(screen.getByTestId("bank-holder")).toHaveTextContent("예금주");
    // ★즉시 충전이 아니라는 사실을 **입금 전에** 말한다.
    expect(screen.getByText(/관리자 승인 후 충전/)).toBeInTheDocument();
  });

  it("★계좌가 불완전하면 입금 구역을 아예 그리지 않는다(부분 안내 금지)", async () => {
    // 서버가 `enabled:false` 면 `account` 는 null 이다 — 화면이 그것을 존중해야 한다.
    mockGets({
      payment_methods: ["bank_transfer"],
      payment_mode: "bank_transfer",
      bank: { enabled: false, account: null, guide: null, notice: null },
    });
    render(<CoinsClient locale="ko" />);
    await screen.findByText("스타터 1만원");
    expect(screen.queryByTestId("bank-transfer-pay")).toBeNull();
    expect(screen.queryByTestId("bank-account-no")).toBeNull();
  });

  it("입금자명을 적으면 주문에 실려 간다 · 비우면 보내지 않는다(두 모집단)", async () => {
    mockGets({ payment_methods: ["bank_transfer"], payment_mode: "bank_transfer", bank: BANK_ON });
    vi.mocked(apiClient.post).mockResolvedValue({
      id: "o1", order_no: "CO-1", status: "pending", amount_krw: 10000,
      payment_mode: "bank_transfer", payment_methods: ["bank_transfer"],
    });
    render(<CoinsClient locale="ko" />);
    await screen.findByTestId("bank-transfer-pay");

    // (a) 비운 채 주문 — `depositor_name` 이 **없어야** 한다(서버가 가입자명을 쓴다).
    await userEvent.click(screen.getByRole("button", { name: "무통장입금 주문 만들기" }));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/billing/orders",
        expect.objectContaining({ body: { package_key: "starter" } }),
      );
    });

    // (b) 적고 주문 — 그 값이 실린다.
    await userEvent.type(screen.getByLabelText(/입금자명/), "(주)사통팔땅");
    await userEvent.click(screen.getByRole("button", { name: "무통장입금 주문 만들기" }));
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenLastCalledWith(
        "/billing/orders",
        expect.objectContaining({
          body: { package_key: "starter", depositor_name: "(주)사통팔땅" },
        }),
      );
    });
  });

  it("★병존 — 카드와 무통장입금이 **동시에** 뜬다", async () => {
    mockGets({
      payment_methods: ["toss", "bank_transfer"],
      payment_mode: "toss",
      bank: BANK_ON,
    });
    render(<CoinsClient locale="ko" />);
    expect(await screen.findByTestId("toss-pay")).toBeInTheDocument();
    expect(screen.getByTestId("bank-transfer-pay")).toBeInTheDocument();
    // 종전 「토스 or else」 구조였다면 둘 중 하나만 떴다.
  });

  it("★환불 버튼은 **그 주문의 결제수단**이 정한다(현재 모드가 아니라)", async () => {
    // 모드는 toss 인데 주문은 무통장입금(provider=manual) — 환불 버튼이 뜨면 안 된다.
    mockGets({
      payment_methods: ["toss", "bank_transfer"],
      payment_mode: "toss",
      bank: BANK_ON,
      orders: {
        orders: [
          { id: "o1", order_no: "CO-1", amount_krw: 10000, coin_krw: 10000,
            status: "paid", provider: "manual", created_at: null, paid_at: null },
        ],
      },
    });
    render(<CoinsClient locale="ko" />);
    await screen.findByText("CO-1");
    expect(screen.queryByRole("button", { name: "환불" })).toBeNull();
    // ★대조군 — 처리내역 버튼은 뜬다(행 자체가 안 그려져서 통과한 것이 아니다).
    expect(screen.getByRole("button", { name: "처리내역" })).toBeInTheDocument();
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
