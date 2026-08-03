/**
 * 분석 대상 전환 가드 회귀락 — "프로젝트를 바꿨는데 옛 분석이 화면에 남는다"의 재발 방지.
 *
 * ★이 파일이 잠그는 것은 **행위**다(합성 픽스처로 순수함수만 부르지 않는다). 2026-08-02
 *   W4에서 "함수를 직접 부르는 회귀락이 죽은 경로를 완벽히 잠근" 사고가 있었기 때문에,
 *   여기서는 실제 훅을 렌더해 이펙트가 도는 경로로만 판정한다. 소비처(패널)가 이 훅을
 *   실제로 거치는지는 별도 배선 불변식(analysis-target.wiring.test.ts)이 잠근다.
 */
import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAnalysisTargetGuard } from "@/hooks/useAnalysisTargetGuard";
import { analysisTargetKey } from "@/lib/analysis-target";

describe("useAnalysisTargetGuard", () => {
  it("붙은 결과가 없으면(첫 진입) 대상이 바뀌어도 비우지 않는다 — 헛발 방지", () => {
    const onStale = vi.fn();
    const { rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale), {
      initialProps: { k: analysisTargetKey("p1", "역삼동 736") },
    });
    rerender({ k: analysisTargetKey("p2", "산1-1") });
    expect(onStale).not.toHaveBeenCalled();
  });

  it("결과가 붙은 뒤 프로젝트가 바뀌면 비운다", () => {
    const onStale = vi.fn();
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale), {
      initialProps: { k: analysisTargetKey("p1", "역삼동 736") },
    });
    act(() => { result.current.begin(); });
    rerender({ k: analysisTargetKey("p2", "역삼동 736") });
    expect(onStale).toHaveBeenCalledTimes(1);
  });

  it("★주소가 없는 프로젝트로 바꿔도 비운다 — 종전 결함의 정확한 재현 케이스", () => {
    // 다필지 프로젝트는 레코드에 대표 주소가 없어 siteAnalysis가 통째로 비는 전환이 된다.
    // 주소 문자열만 비교하던 종전 코드는 이 경로에서 아무것도 지우지 않았다.
    const onStale = vi.fn();
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale), {
      initialProps: { k: analysisTargetKey("p1", "역삼동 736") },
    });
    act(() => { result.current.begin(); });
    rerender({ k: analysisTargetKey("p2", "") });
    expect(onStale).toHaveBeenCalledTimes(1);
  });

  it("대상이 그대로면 다시 렌더해도 비우지 않는다 — 오탐 0", () => {
    const onStale = vi.fn();
    const key = analysisTargetKey("p1", "역삼동 736");
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale), {
      initialProps: { k: key },
    });
    act(() => { result.current.begin(); });
    rerender({ k: key });
    rerender({ k: key });
    expect(onStale).not.toHaveBeenCalled();
  });

  it("onStale이 매 렌더 새 함수여도 대상이 그대로면 비우지 않는다", () => {
    // 콜백을 deps에 넣으면 대상 무관하게 이펙트가 돌아 화면이 멋대로 비워진다.
    const calls: number[] = [];
    const key = analysisTargetKey("p1", "역삼동 736");
    const { result, rerender } = renderHook(
      ({ k, n }) => useAnalysisTargetGuard(k, () => calls.push(n)),
      { initialProps: { k: key, n: 1 } },
    );
    act(() => { result.current.begin(); });
    rerender({ k: key, n: 2 });
    rerender({ k: key, n: 3 });
    expect(calls).toEqual([]);
  });

  it("★분석 중 대상이 바뀌면 뒤늦게 온 응답을 버린다(isCurrent=false)", () => {
    const onStale = vi.fn();
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale), {
      initialProps: { k: analysisTargetKey("p1", "역삼동 736") },
    });
    let runKey = "";
    act(() => { runKey = result.current.begin(); });
    // 응답을 기다리는 사이 사용자가 프로젝트를 바꿨다
    rerender({ k: analysisTargetKey("p2", "산1-1") });
    expect(result.current.isCurrent(runKey)).toBe(false);
  });

  it("대상이 그대로면 응답을 받아들인다(isCurrent=true) — 정상 경로 무회귀", () => {
    const key = analysisTargetKey("p1", "역삼동 736");
    const { result } = renderHook(() => useAnalysisTargetGuard(key, vi.fn()));
    let runKey = "";
    act(() => { runKey = result.current.begin(); });
    expect(result.current.isCurrent(runKey)).toBe(true);
  });
});

describe("analysisTargetKey", () => {
  it("프로젝트가 다르면 주소가 같아도 다른 키", () => {
    expect(analysisTargetKey("p1", "역삼동 736")).not.toBe(analysisTargetKey("p2", "역삼동 736"));
  });

  it("주소가 다르면 프로젝트가 같아도 다른 키", () => {
    expect(analysisTargetKey("p1", "역삼동 736")).not.toBe(analysisTargetKey("p1", "산1-1"));
  });

  it("null·undefined·공백은 같은 '없음'으로 수렴 — 잡음으로 인한 헛 무효화 방지", () => {
    expect(analysisTargetKey(null, null)).toBe(analysisTargetKey(undefined, "  "));
  });

  it("값이 서로 밀려 들어가 우연히 같은 키가 되지 않는다", () => {
    expect(analysisTargetKey("a", "b c")).not.toBe(analysisTargetKey("a b", "c"));
  });
});
