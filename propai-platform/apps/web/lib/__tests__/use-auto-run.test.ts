/**
 * useAutoRun 계약 잠금 — 파이프라인 자동실행의 트리거 의미론.
 *
 * 두 카드(POI·개발방식 시뮬)가 각자 useEffect를 쓰면 "언제 실행하는가"가 조용히 갈라진다.
 * 여기서 세 가드를 고정한다: 마운트 미실행 / 변화 1회당 1실행 / 미충족 시 토큰 미소비.
 */

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useAutoRun } from "@/lib/use-auto-run";

describe("useAutoRun", () => {
  it("★마운트만으로는 실행하지 않는다(요청하지 않은 API 호출·과금 방지)", () => {
    const run = vi.fn();
    renderHook(() => useAutoRun(1, run));
    expect(run).not.toHaveBeenCalled();
  });

  it("토큰이 바뀌면 실행한다", () => {
    const run = vi.fn();
    const { rerender } = renderHook(({ t }) => useAutoRun(t, run), {
      initialProps: { t: 0 },
    });
    expect(run).not.toHaveBeenCalled();

    rerender({ t: 1 });
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("★같은 토큰으로 리렌더돼도 재실행하지 않는다(중복 호출 방지)", () => {
    const run = vi.fn();
    const { rerender } = renderHook(({ t }) => useAutoRun(t, run), {
      initialProps: { t: 0 },
    });
    rerender({ t: 1 });
    rerender({ t: 1 });
    rerender({ t: 1 });
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("토큰이 여러 번 바뀌면 그만큼 실행한다", () => {
    const run = vi.fn();
    const { rerender } = renderHook(({ t }) => useAutoRun(t, run), {
      initialProps: { t: 0 },
    });
    rerender({ t: 1 });
    rerender({ t: 2 });
    expect(run).toHaveBeenCalledTimes(2);
  });

  it("★enabled=false면 실행하지 않고 **토큰도 소비하지 않는다**", () => {
    // 주소 미선택 상태에서 토큰이 지나가버리면, 주소가 채워져도 그 회차는 영영 실행되지 않는다.
    const run = vi.fn();
    const { rerender } = renderHook(
      ({ t, on }) => useAutoRun(t, run, { enabled: on }),
      { initialProps: { t: 0, on: false } },
    );
    rerender({ t: 1, on: false });
    expect(run).not.toHaveBeenCalled();

    // 조건이 갖춰지면 같은 토큰으로 실행된다.
    rerender({ t: 1, on: true });
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("token이 undefined면 아무 것도 하지 않는다(부모가 미배선인 경우)", () => {
    const run = vi.fn();
    const { rerender } = renderHook(({ t }) => useAutoRun(t, run), {
      initialProps: { t: undefined as number | undefined },
    });
    rerender({ t: undefined });
    expect(run).not.toHaveBeenCalled();
  });

  it("run이 매 렌더 새 함수여도 재실행을 유발하지 않는다", () => {
    const spy = vi.fn();
    const { rerender } = renderHook(({ t }) => useAutoRun(t, () => spy()), {
      initialProps: { t: 0 },
    });
    rerender({ t: 1 });
    rerender({ t: 1 });
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
