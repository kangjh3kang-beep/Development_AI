/**
 * 실패 작업목록 패널의 **렌더 락**.
 *
 * 볼트 선례(2026-08-02 W3)를 그대로 검증 항목으로 옮긴다:
 *  · "부실할수록 깨끗해 보이는 역선택" → 조치를 못 고른 건도 **반드시 보인다**
 *  · 빈 컨테이너 착시 → **“실패 0”과 “아직 분석 안 함”이 다른 말을 한다**
 *  · 할 수 없는 일을 버튼으로 만들지 않는다 → 재시도 버튼은 `canRetry` 묶음에만
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RegistryFailureActions } from "../RegistryFailureActions";
import type { BatchOutcome } from "@/lib/registry-analyze";

const 성공: BatchOutcome = { jibun: "가", rowId: "r0", result: { status: "ok", ai: { generated: true } } };
const 해석실패 = (j: string, id: string): BatchOutcome => ({
  jibun: j, rowId: id,
  result: { status: "ok", ai: { generated: false, failure_reason: "JSONDecodeError: Unterminated" } },
});
const 본문미확보: BatchOutcome = {
  jibun: "나", rowId: "r2",
  result: { status: "empty", message: "등기부 본문(갑구·을구)을 확보하지 못했습니다. 발급 PDF가 이미지 형식이면…" },
};
const 사유없음: BatchOutcome = { jibun: "다", rowId: "r3", result: { status: "error" } };

describe("분석되지 않은 필지 — 작업 목록", () => {
  it("★‘아직 분석 안 함’에는 아무 말도 하지 않는다(없는 작업을 만들지 않는다)", () => {
    const { container } = render(<RegistryFailureActions items={[]} />);
    expect(container.textContent).toBe("");
  });

  it("★‘실패 0’은 **다른 말**을 한다 — 빈 목록이라고 같은 화면이면 안 된다", () => {
    render(<RegistryFailureActions items={[성공]} />);
    expect(screen.getByTestId("failures-none").textContent).toContain("모두 분석됐습니다");
    expect(screen.queryByTestId("failure-actions")).toBeNull();
  });

  it("★사유별로 묶고 **어느 필지인지** 말한다(개수만으론 못 고친다)", () => {
    render(<RegistryFailureActions items={[성공, 해석실패("내삼미동 448-2", "r1"), 본문미확보]} />);
    const panel = screen.getByTestId("failure-actions");
    expect(panel.textContent).toContain("분석되지 않은 2필지");
    expect(screen.getByTestId("failure-group-reinterpret").textContent).toContain("내삼미동 448-2");
    expect(screen.getByTestId("failure-group-enter_manually").textContent).toContain("직접 입력");
  });

  it("★★조치를 못 고른 건도 **보인다**(분류 실패가 화면을 깨끗하게 만들면 안 된다)", () => {
    render(<RegistryFailureActions items={[사유없음]} />);
    expect(screen.getByTestId("failure-actions").textContent).toContain("분석되지 않은 1필지");
    expect(screen.getByTestId("failure-group-unknown")).toBeTruthy();
  });

  it("★할 수 없는 일은 버튼으로 만들지 않는다", () => {
    render(<RegistryFailureActions items={[본문미확보]} onRetry={vi.fn()} />);
    expect(screen.queryByTestId("failure-retry-enter_manually")).toBeNull();
  });

  it("★재시도가 그 묶음만 넘긴다(다른 묶음까지 끌고 가지 않는다)", async () => {
    const seen: BatchOutcome[][] = [];
    render(
      <RegistryFailureActions
        items={[해석실패("가", "r1"), 해석실패("나", "r2"), 본문미확보]}
        onRetry={async (g) => { seen.push([...g]); }}
      />,
    );
    fireEvent.click(screen.getByTestId("failure-retry-reinterpret"));
    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0].map((b) => b.rowId)).toEqual(["r1", "r2"]);
  });

  it("onRetry 가 없으면 버튼을 그리지 않는다(죽은 버튼 금지)", () => {
    render(<RegistryFailureActions items={[해석실패("가", "r1")]} />);
    expect(screen.queryByTestId("failure-retry-reinterpret")).toBeNull();
  });

  it("★해석 재시도 안내가 무과금을 단정하지 않는다(보장할 수 없는 것을 보장으로 말하지 않는다)", () => {
    render(<RegistryFailureActions items={[해석실패("가", "r1")]} />);
    const t = screen.getByTestId("failure-group-reinterpret").textContent!;
    expect(t).toContain("남아 있으면");
    expect(t).not.toContain("무과금");
  });
});
