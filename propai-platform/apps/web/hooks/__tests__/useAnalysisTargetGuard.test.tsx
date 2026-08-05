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
    const { rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale, false), {
      initialProps: { k: analysisTargetKey("p1", "역삼동 736") },
    });
    rerender({ k: analysisTargetKey("p2", "산1-1") });
    expect(onStale).not.toHaveBeenCalled();
  });

  it("결과가 붙은 뒤 프로젝트가 바뀌면 비운다", () => {
    const onStale = vi.fn();
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale, false), {
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
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale, false), {
      initialProps: { k: analysisTargetKey("p1", "역삼동 736") },
    });
    act(() => { result.current.begin(); });
    rerender({ k: analysisTargetKey("p2", "") });
    expect(onStale).toHaveBeenCalledTimes(1);
  });

  it("대상이 그대로면 다시 렌더해도 비우지 않는다 — 오탐 0", () => {
    const onStale = vi.fn();
    const key = analysisTargetKey("p1", "역삼동 736");
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale, false), {
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
      ({ k, n }) => useAnalysisTargetGuard(k, () => calls.push(n), false),
      { initialProps: { k: key, n: 1 } },
    );
    act(() => { result.current.begin(); });
    rerender({ k: key, n: 2 });
    rerender({ k: key, n: 3 });
    expect(calls).toEqual([]);
  });

  it("★분석 중 대상이 바뀌면 뒤늦게 온 응답을 버린다(isCurrent=false)", () => {
    const onStale = vi.fn();
    const { result, rerender } = renderHook(({ k }) => useAnalysisTargetGuard(k, onStale, false), {
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
    const { result } = renderHook(() => useAnalysisTargetGuard(key, vi.fn(), false));
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

// ── R3 MEDIUM 봉합 회귀락 (2026-08-05) ────────────────────────────────────────

describe("★키 충돌 — 구분자 방식이 갖지 못한 보장(R3 M-2)", () => {
  it("값에 개행이 들어와도 서로 다른 대상이 같은 키가 되지 않는다", () => {
    // 종전 주석은 "줄바꿈은 ID·주소에 들어갈 수 없다"고 단언했지만, 주소는 trim만 하므로
    // 내부 개행이 남는다. 그 반증 케이스를 그대로 고정한다.
    expect(analysisTargetKey("p1\nX", "Y")).not.toBe(analysisTargetKey("p1", "X\nY"));
  });

  it("따옴표·역슬래시 같은 문자도 대상을 뒤섞지 않는다", () => {
    expect(analysisTargetKey('p"1', "Y")).not.toBe(analysisTargetKey("p", '"1","Y'));
    expect(analysisTargetKey("p\\", "Y")).not.toBe(analysisTargetKey("p", "\\Y"));
  });
});

describe("★같은 대상 재실행 경합(R3 M-3)", () => {
  it("먼저 시작한 느린 응답이 나중 실행 결과를 덮지 못한다", () => {
    const { result } = renderHook(() =>
      useAnalysisTargetGuard(analysisTargetKey("p1", "역삼동 736"), vi.fn(), false),
    );
    let first = "";
    let second = "";
    act(() => { first = result.current.begin(); });
    act(() => { second = result.current.begin(); });
    expect(first).not.toBe(second);
    expect(result.current.isCurrent(first)).toBe(false); // 낡은 실행
    expect(result.current.isCurrent(second)).toBe(true);
  });
});

describe("★결과 추적이 begin()에만 매달리지 않는다(R3 M-3)", () => {
  it("실행 경로 밖에서 결과가 붙어도 대상 전환 시 비운다", () => {
    const onStale = vi.fn();
    // begin()을 한 번도 부르지 않고 결과만 존재하는 상태(히스토리 복원 등).
    const { rerender } = renderHook(
      ({ k, has }) => useAnalysisTargetGuard(k, onStale, has),
      { initialProps: { k: analysisTargetKey("p1", "역삼동 736"), has: true } },
    );
    rerender({ k: analysisTargetKey("p2", "산1-1"), has: true });
    expect(onStale).toHaveBeenCalledTimes(1);
  });

  it("결과가 없으면 대상이 바뀌어도 헛 무효화하지 않는다 — 오탐 0", () => {
    const onStale = vi.fn();
    const { rerender } = renderHook(
      ({ k, has }) => useAnalysisTargetGuard(k, onStale, has),
      { initialProps: { k: analysisTargetKey("p1", "역삼동 736"), has: false } },
    );
    rerender({ k: analysisTargetKey("p2", "산1-1"), has: false });
    expect(onStale).not.toHaveBeenCalled();
  });
});
