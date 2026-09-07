/**
 * 「수정 → 입력 → 저장」 타일 — 행위 락.
 *
 * ★단언은 «렌더됐는가» 가 아니라 **«무엇이 저장되는가»** 를 본다.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EditableTile } from "../EditableTile";

function setup(props: Partial<React.ComponentProps<typeof EditableTile>> = {}) {
  const onSave = vi.fn();
  render(
    <EditableTile label="연면적" autoText="25,412㎡" value={null} onSave={onSave} unit="㎡" {...props} />,
  );
  return { onSave };
}

describe("EditableTile", () => {
  it("기본은 **읽기 상태** — 입력창이 없다", () => {
    setup();
    expect(screen.getByText("25,412㎡")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("수정 → 입력 → 저장 으로만 값이 나간다", () => {
    const { onSave } = setup();
    fireEvent.click(screen.getByRole("button", { name: "연면적 수정" }));
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "30000" } });
    // ★저장 전에는 아무것도 나가지 않는다(항상 열린 입력창과의 차이).
    expect(onSave).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "연면적 저장" }));
    expect(onSave).toHaveBeenCalledWith(30000);
  });

  it("취소하면 저장되지 않는다", () => {
    const { onSave } = setup();
    fireEvent.click(screen.getByRole("button", { name: "연면적 수정" }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "999" } });
    fireEvent.click(screen.getByRole("button", { name: "연면적 취소" }));
    expect(onSave).not.toHaveBeenCalled();
  });

  it("★빈 값 저장은 0이 아니라 **자동값 되돌리기**(null)다", () => {
    // 「없음」을 0 으로 표현하면 0㎡ 가 확정치처럼 계산에 들어간다.
    const { onSave } = setup({ value: 30000 });
    fireEvent.click(screen.getByRole("button", { name: "연면적 수정" }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "연면적 저장" }));
    expect(onSave).toHaveBeenCalledWith(null);
  });

  it("★0 이하는 거부하고 **사유를 말한다** — 조용히 안 받지 않는다", () => {
    const { onSave } = setup();
    fireEvent.click(screen.getByRole("button", { name: "연면적 수정" }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "연면적 저장" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText(/0보다 큰 숫자/)).toBeInTheDocument();
  });

  it("★저장된 칸은 **출처를 계속 말한다** — 자동값과 같은 얼굴이면 안 된다", () => {
    setup({ value: 30000 });
    expect(screen.getByText("직접입력")).toBeInTheDocument();
    // 되돌리기 경로가 **존재**해야 한다(갇히지 않게).
    expect(screen.getByRole("button", { name: "연면적 자동값으로 되돌리기" })).toBeInTheDocument();
  });

  it("★자동 상태에는 되돌리기 버튼이 없다(위양성 축)", () => {
    setup({ value: null });
    expect(screen.queryByRole("button", { name: "연면적 자동값으로 되돌리기" })).toBeNull();
  });
});
