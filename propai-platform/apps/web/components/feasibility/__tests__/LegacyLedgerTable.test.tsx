/**
 * 간략 수지 원장 표 — **렌더 결과**를 본다(소스 grep 아님).
 *
 * ★소스 검사는 주석처리+import유지 변이에 뚫린다(이 저장소에서 2회 실증). 그리고
 *   조건부 렌더 요소는 **그 상태를 만들어서** 검사해야 한다 — 안 그러면 "검사는 있는데
 *   대상이 없어" 통과하는 공허한 초록이 된다.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LegacyLedgerTable, { type LegacyLedger } from "../LegacyLedgerTable";

const item = (o: Partial<LegacyLedger["sections"][0]["groups"][0]["items"][0]> = {}) => ({
  key: "x", label: "행", amount_won: 1_000_000_000, qty: 100, qty_unit: "㎡",
  unit_price: 10_000_000, unit_price_unit: "원/㎡", basis: "탁상감정",
  basis_kind: "data" as const, note: null, added: false, share_pct: 10, ...o,
});

const ledger = (o: Partial<LegacyLedger> = {}): LegacyLedger => ({
  sections: [
    {
      key: "cost", label: "매출원가",
      groups: [{ key: "land", label: "택지비", items: [item()], subtotal_won: 1_000_000_000, share_pct: 10 }],
      total_won: 1_000_000_000,
    },
  ],
  checks: [
    { key: "cost_total", label: "지출 합계", ledger_won: 1e9, engine_won: 1e9, diff_won: 0, verdict: "OK", note: null },
  ],
  coverage: { items: 1, with_qty: 1, with_unit_price: 1, with_basis: 1, qty_pct: 100, unit_price_pct: 100, basis_pct: 100 },
  share_basis_won: 1e10,
  share_basis_label: "매출 합계(부가세 미차감)",
  ...o,
});

describe("간략 수지 원장 표", () => {
  it("★전제 — 표가 실제로 그려진다(공허한 초록 방지)", () => {
    render(<LegacyLedgerTable ledger={ledger()} />);
    expect(screen.getByTestId("legacy-ledger")).toBeTruthy();
    expect(screen.getByText("행")).toBeTruthy();
  });

  it("원장이 없으면 아무것도 그리지 않는다", () => {
    const { container } = render(<LegacyLedgerTable ledger={null} />);
    expect(container.querySelector('[data-testid="legacy-ledger"]')).toBeNull();
  });

  it("★★없는 값은 **0 이 아니라 —** 로 그린다(무목업)", () => {
    render(
      <LegacyLedgerTable
        ledger={ledger({
          sections: [{
            key: "cost", label: "매출원가",
            groups: [{
              key: "land", label: "택지비",
              items: [item({ amount_won: null, qty: null, unit_price: null, share_pct: null })],
              subtotal_won: null, share_pct: null,
            }],
            total_won: null,
          }],
        })}
      />,
    );
    const row = screen.getByText("행").closest("tr")!;
    expect(row.textContent).toContain("—");
    expect(row.textContent).not.toContain("0억");
    expect(row.textContent).not.toContain("0.0%");
  });

  it("★수량·단가가 **둘 다** 있어야 산출내역을 그린다(반쪽 산식 금지)", () => {
    render(<LegacyLedgerTable ledger={ledger({
      sections: [{ key: "c", label: "매출원가", groups: [{
        key: "g", label: "그룹",
        items: [item({ key: "a", label: "온전", qty: 100, unit_price: 5 }),
                item({ key: "b", label: "반쪽", qty: 100, unit_price: null })],
        subtotal_won: 1, share_pct: 1 }], total_won: 1 }],
    })} />);
    expect(screen.getByText("온전").closest("tr")!.textContent).toContain("×");
    // ★두 모집단 — 반쪽이 온전과 **다르게** 그려져야 한다. 같으면 분기를 지워도 통과한다.
    expect(screen.getByText("반쪽").closest("tr")!.textContent).not.toContain("×");
  });

  it("★★판정 불가(UNKNOWN)를 OK 로 그리지 않는다", () => {
    render(<LegacyLedgerTable ledger={ledger({
      checks: [
        { key: "a", label: "매출 합계", ledger_won: null, engine_won: null, diff_won: null, verdict: "UNKNOWN", note: null },
        { key: "b", label: "지출 합계", ledger_won: 1, engine_won: 1, diff_won: 0, verdict: "OK", note: null },
      ],
    })} />);
    expect(screen.getByTestId("ledger-check-a").textContent).toBe("판정 불가");
    // 대조군 — OK 는 OK 로 그려진다(전부 "판정 불가"로 칠하는 구현이 통과하지 않게).
    expect(screen.getByTestId("ledger-check-b").textContent).toBe("OK");
  });

  it("★검산 ERROR 면 경고 문구가 함께 뜬다 — OK 만 있으면 안 뜬다(두 모집단)", () => {
    const err = ledger({ checks: [{ key: "a", label: "지출 합계", ledger_won: 2, engine_won: 1, diff_won: 1, verdict: "ERROR", note: null }] });
    const { unmount } = render(<LegacyLedgerTable ledger={err} />);
    expect(screen.getByTestId("ledger-check-a").textContent).toBe("ERROR");
    expect(screen.queryByText(/합계가 어긋납니다/)).toBeTruthy();
    unmount();
    render(<LegacyLedgerTable ledger={ledger()} />);
    expect(screen.queryByText(/합계가 어긋납니다/)).toBeNull();
  });

  it("★근거는 기본 숨김이고, 열면 나온다 — 조건부 렌더는 그 상태를 만들어서 검사한다", () => {
    render(<LegacyLedgerTable ledger={ledger()} />);
    expect(screen.queryByText("탁상감정")).toBeNull();
    fireEvent.click(screen.getByText("근거 보기"));
    expect(screen.getByText(/탁상감정/)).toBeTruthy();
  });

  it("★구조근거는 **데이터근거와 구별해** 표시한다(폴백이 실측처럼 보이지 않게)", () => {
    render(<LegacyLedgerTable ledger={ledger({
      sections: [{ key: "c", label: "매출원가", groups: [{
        key: "g", label: "그룹",
        items: [item({ key: "d", label: "실측", basis: "탁상감정", basis_kind: "data" }),
                item({ key: "s", label: "폴백", basis: "택지비 = 면적 × 단가", basis_kind: "structural" })],
        subtotal_won: 1, share_pct: 1 }], total_won: 1 }],
    })} />);
    fireEvent.click(screen.getByText("근거 보기"));
    expect(screen.getByText("폴백").closest("tr")!.textContent).toContain("데이터 근거 미확보");
    // 두 모집단 — 실측 행에는 그 꼬리표가 없어야 한다.
    expect(screen.getByText("실측").closest("tr")!.textContent).not.toContain("데이터 근거 미확보");
  });

  it("커버리지를 화면에 신고한다", () => {
    render(<LegacyLedgerTable ledger={ledger()} />);
    expect(screen.getByTestId("legacy-ledger-coverage").textContent).toContain("항목 1개");
  });
});
