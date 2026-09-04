/**
 * ★사용자 신고 회귀 잠금(2026-08-25) — *"매입전략 분석 시작 버튼이 활성화되지 않고
 * 기능을 사용할 수 없다"*.
 *
 * ## 조건은 옳았다 — 말하지 않은 것이 결함이었다
 *
 * `disabled={!scheme || overCap}` 는 의도된 설계다(*"방식이 없으면 판정이 성립하지
 * 않는다"* — 사업방식에 따라 협의매수·매도청구·수용·제척 기준이 달라진다).
 * 실측으로 대안 차단 경로는 없었고(`STRATEGY_SCHEMES` 9종 정상 · 바인딩 정상 ·
 * `overCap` 은 77 < 100 이라 거짓), 사용자 화면의 사업방식이 `선택하세요`(빈 값)였다.
 *
 * 그런데 화면에는 라벨 옆 빨간 `*` 하나뿐이라, **회색 버튼과 연결되지 않았다.**
 * 사용자는 *"기능을 못 쓴다"* 로 읽었다 — 비활성의 **사유 부재**가 곧 결함이다.
 *
 * ★이 락이 보는 것: 못 누르는 상태에서 **왜 못 누르는지**가 화면에 있는가.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  MAX_STRATEGY_PARCELS,
  ParcelPurchaseStrategyPanel,
  type StrategyParcelInput,
} from "@/components/operations/ParcelPurchaseStrategyPanel";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  const pending = () => new Promise<never>(() => {});
  return {
    ...actual,
    apiClient: { ...actual.apiClient, post: vi.fn(pending), get: vi.fn(pending) },
  };
});

function parcels(n: number): StrategyParcelInput[] {
  // ★계약을 좁혀 잡지 않는다 — 스텁이 실제 타입보다 좁으면 그 필드를 쓰는 코드가
  //   테스트에서만 통과한다(규율 §33). 필수 필드를 전부 채운다.
  return Array.from({ length: n }, (_, i) => ({
    address: `경기도 오산시 내삼미동 ${i + 1}`,
  }));
}

const START = "매입전략 분석 시작";

describe("매입전략 — 비활성 사유를 말한다", () => {
  it("★사업방식 미선택이면 **사유가 화면에 있다**", () => {
    render(<ParcelPurchaseStrategyPanel parcels={parcels(77)} />);
    // 대조군: 버튼이 실제로 렌더됐고 실제로 비활성이다 —
    //   "사유가 있다" 가 '버튼이 아예 없어서' 참이 되는 것을 막는다(§A-2).
    const btn = screen.getByRole("button", { name: START }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);

    const reason = screen.getByTestId("strategy-disabled-reason");
    expect(reason.textContent ?? "").toContain("사업방식");
  });

  it("★특이도 — 방식을 고르면 사유가 사라지고 버튼이 살아난다", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    render(<ParcelPurchaseStrategyPanel parcels={parcels(3)} />);
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    // 첫 실제 옵션(빈 값 '선택하세요' 다음)을 고른다 — 목록을 손으로 적지 않는다.
    const first = Array.from(select.options).find((o) => o.value !== "");
    expect(first, "선택 가능한 사업방식이 하나도 없다 — 목록이 비었다").toBeTruthy();
    await userEvent.selectOptions(select, (first as HTMLOptionElement).value);

    expect(screen.queryByTestId("strategy-disabled-reason")).toBeNull();
    const btn = screen.getByRole("button", { name: START }) as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("★상한 초과일 때는 이 사유를 **중복해서 말하지 않는다**(위쪽 경고가 이미 있다)", () => {
    render(<ParcelPurchaseStrategyPanel parcels={parcels(MAX_STRATEGY_PARCELS + 1)} />);
    expect(screen.queryByTestId("strategy-disabled-reason")).toBeNull();
  });
});
