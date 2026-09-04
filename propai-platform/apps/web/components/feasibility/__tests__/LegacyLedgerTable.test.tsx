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
    // ★문구가 아니라 **존재**를 잠근다 — 산문에 건 락은 다듬을 때마다 깨지는 취약한 락이다
    //   (실제로 이 케이스가 문구 정정 한 번에 빨개졌다).
    expect(screen.queryByTestId("legacy-ledger-drift-warning")).toBeTruthy();
    unmount();
    render(<LegacyLedgerTable ledger={ledger()} />);
    expect(screen.queryByTestId("legacy-ledger-drift-warning")).toBeNull();
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

  // ── 적대 리뷰 중2·중3 — 저자가 고른 5변이가 **가장 무거운 두 배선을 비껴갔다** ──────
  //   리뷰가 실제로 넣어 본 변이 6건이 **전부 SURVIVED** 했다:
  //     소계 금액 배선 절단 · 섹션 합계 배선 절단 · 합계 라벨 뒤집기 ·
  //     커버리지 푸터 숨김 · `(추가)` 배지 제거 · 검산 note 제거.
  //   ★CLAUDE.md §B5 — *"사람이 고른 변이는 사람이 못 본 층을 비껴간다."* 실증이다.
  it("★★소계·섹션 합계 **금액**을 실제로 그린다(배선을 끊으면 빨개진다)", () => {
    render(<LegacyLedgerTable ledger={ledger({
      sections: [{
        key: "cost", label: "매출원가",
        groups: [{ key: "land", label: "택지비", items: [item({ amount_won: 6e10 })],
                   subtotal_won: 6e10, share_pct: 20 }],
        total_won: 6e10,
      }],
    })} />);
    const rows = Array.from(document.querySelectorAll("tbody tr")).map((r) => r.textContent ?? "");
    const sub = rows.find((t) => t.includes("택지비 소계"))!;
    const tot = rows.find((t) => t.includes("매출원가 합계"))!;
    expect(sub).toContain("600억");
    expect(tot).toContain("600억");
    // ★두 모집단 — 값이 없으면 「—」. 상수를 그리는 구현이 통과하지 않게.
    expect(sub).not.toContain("—");
  });

  it("★★3단 계층 — 섹션 합계는 **자기 섹션 뒤**에 온다(표 끝에 몰리지 않는다)", () => {
    render(<LegacyLedgerTable ledger={ledger({
      sections: [
        { key: "revenue", label: "매 출",
          groups: [{ key: "sale", label: "분양", items: [item({ key: "r", label: "분양수입" })],
                     subtotal_won: 1, share_pct: 1 }], total_won: 1 },
        { key: "profit", label: "세 전 이 익",
          groups: [{ key: "p", label: "세전이익", items: [item({ key: "p", label: "세전이익" })],
                     subtotal_won: 1, share_pct: 1 }], total_won: 1 },
      ],
    })} />);
    const rows = Array.from(document.querySelectorAll("tbody tr")).map((r) => r.textContent ?? "");
    const iRevTotal = rows.findIndex((t) => t.includes("매 출 합계"));
    const iProfitRow = rows.findIndex((t) => t.includes("세전이익"));
    expect(iRevTotal).toBeGreaterThanOrEqual(0);
    // ★초안은 합계 3행이 표 **맨 아래에 몰려** 「세전이익」 아래에 「매출 합계」가 왔다.
    expect(iRevTotal).toBeLessThan(iProfitRow);
  });

  it("커버리지 푸터·`(추가)` 배지·검산 note 가 실제로 그려진다", () => {
    render(<LegacyLedgerTable ledger={ledger({
      sections: [{ key: "c", label: "매출원가", groups: [{
        key: "g", label: "그룹", items: [item({ label: "신설항목", added: true })],
        subtotal_won: 1, share_pct: 1 }], total_won: 1 }],
      checks: [{ key: "a", label: "지출 합계", ledger_won: 1, engine_won: 1, diff_won: 0,
                 verdict: "OK", note: "항등식 — 전파 오류만 잡는다" }],
    })} />);
    expect(screen.getByTestId("legacy-ledger-coverage").textContent).toContain("항목 1개");
    expect(screen.getByText("신설항목").closest("tr")!.textContent).toContain("(추가)");
    expect(screen.getByTestId("legacy-ledger-checks").textContent).toContain("항등식");
  });

  it("★소액이 **「0억」으로 뭉개지지 않는다** — 있는 값과 없는 값이 구별된다(중6)", () => {
    render(<LegacyLedgerTable ledger={ledger({
      sections: [{ key: "c", label: "매출원가", groups: [{
        key: "g", label: "그룹",
        items: [item({ key: "s", label: "소액", amount_won: 4_500_000 }),
                item({ key: "z", label: "미부과", amount_won: 0 }),
                item({ key: "n", label: "모름", amount_won: null })],
        subtotal_won: 4_500_000, share_pct: 1 }], total_won: 4_500_000 }],
    })} />);
    const t = (l: string) => screen.getByText(l).closest("tr")!.textContent ?? "";
    expect(t("소액")).toContain("450만원");
    expect(t("소액")).not.toContain("0억");
    // ★세 모집단이 전부 다르게 보여야 한다 — 소액 / 0원 / 모름.
    expect(t("미부과")).toContain("0원");
    expect(t("모름")).toContain("—");
  });

  it("★모르는 verdict 이 와도 패널이 죽지 않는다(TS 유니온은 런타임을 안 막는다)", () => {
    render(<LegacyLedgerTable ledger={ledger({
      checks: [{ key: "x", label: "미지", ledger_won: 1, engine_won: 1, diff_won: 0,
                 verdict: "WAT" as never, note: null }],
    })} />);
    expect(screen.getByTestId("ledger-check-x").textContent).toBe("판정 불가");
  });

  it("★★단위와 라벨을 섞지 않는다 — 숫자에 문장이 달라붙지 않게(라이브 실측 결함)", () => {
    render(<LegacyLedgerTable ledger={ledger({
      sections: [{ key: "c", label: "매출원가", groups: [{
        key: "g", label: "그룹",
        items: [item({ key: "f", label: "금융비용", qty: 19_027_218_768, qty_unit: "원",
                       qty_label: "토지비 + 공사비", unit_price: 0.067, unit_price_unit: "비율" }),
                item({ key: "l", label: "택지비", qty: 506, qty_unit: "㎡",
                       unit_price: 1_676_000, unit_price_unit: "원/㎡" })],
        subtotal_won: 1, share_pct: 1 }], total_won: 1 }],
    })} />);
    const fin = screen.getByText("금융비용").closest("tr")!.textContent ?? "";
    // 라벨은 **괄호로 떼어** 있고, 숫자 바로 뒤에 붙지 않는다.
    expect(fin).toContain("(토지비 + 공사비)");
    expect(fin).not.toMatch(/\d토지비/);
    // ★두 모집단 — 라벨 없는 행은 괄호가 없다(항상 괄호를 다는 구현이 통과하지 않게).
    expect(screen.getByText("택지비").closest("tr")!.textContent).not.toContain("(");
  });

  it("★제원이 표 **위에** 그려진다 — 「어느 사업인가」를 먼저 보인다", () => {
    render(<LegacyLedgerTable ledger={ledger({
      header: [
        { key: "inputs_zone_type", label: "용도지역", value: "일반상업지역", unit: null, is_numeric: false },
        { key: "inputs_land_area_sqm", label: "사업면적", value: 505.6, unit: "㎡", is_numeric: true },
      ],
    })} />);
    const h = screen.getByTestId("legacy-ledger-header");
    expect(h.textContent).toContain("일반상업지역");
    expect(h.textContent).toContain("사업면적 (㎡)");
    expect(h.textContent).toContain("505.6");
  });

  it("★★제원이 없으면 **블록을 그리지 않는다** — 빈 제원표는 「미정」으로 읽힌다(두 모집단)", () => {
    render(<LegacyLedgerTable ledger={ledger()} />);
    expect(screen.queryByTestId("legacy-ledger-header")).toBeNull();
    // 대조군 — 표 본문은 **둘 다** 그려진다(과잉 삭제가 아님).
    expect(screen.getByTestId("legacy-ledger")).toBeTruthy();
  });
});
