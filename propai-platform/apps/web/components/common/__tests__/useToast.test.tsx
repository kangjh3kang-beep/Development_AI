/**
 * ToastProvider + useToast() 신규 프리미티브(@propai/ui) 단위 테스트 — UX 트랙 C3.
 *
 * 왜 필요한가: SatongMapShell의 uploadNote·exportNote·connectNotice·searchError 4개
 * 인라인 알림 슬롯을 흡수할 공용 호스트/훅이다. Toast 프리미티브 자체(packages/ui/src/
 * components/toast.tsx)는 있었지만 이를 화면에 올리는 Provider·훅이 없었다 — 이 스위트가
 * 그 신규 부분(표시·자동소멸·수동닫기·aria-live)을 고정한다.
 *
 * 배치 위치: packages/ui에는 테스트 러너가 없어(devDependency 부재), 실제로 vitest가
 * 도는 apps/web에 둔다 — vitest.config.ts가 "@propai/ui"를 packages/ui/src/index.ts로
 * 직접 alias하므로 실제 소스를 그대로 검증한다(별도 빌드 스텁 아님).
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast, useToastOptional } from "@propai/ui";

function Trigger({ label = "고지", durationMs }: { label?: string; durationMs?: number }) {
  const toast = useToast();
  return (
    <button type="button" onClick={() => toast.push({ description: label, durationMs })}>
      토스트 띄우기
    </button>
  );
}

describe("ToastProvider + useToast()", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("표시: push()가 화면에 알림 카드를 올린다", () => {
    render(
      <ToastProvider>
        <Trigger label="3필지 내보냄" />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "토스트 띄우기" }));

    expect(screen.getByText("3필지 내보냄")).toBeInTheDocument();
  });

  it("aria-live: 뷰포트가 role=status + aria-live=polite를 갖는다(접근성)", () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );

    const viewport = screen.getByRole("status");
    expect(viewport).toHaveAttribute("aria-live", "polite");
  });

  it("자동소멸: 기본 유예(4000ms) 경과 후 알림이 사라진다", () => {
    render(
      <ToastProvider>
        <Trigger label="자동소멸 확인" />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "토스트 띄우기" }));
    expect(screen.getByText("자동소멸 확인")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(4000);
    });

    expect(screen.queryByText("자동소멸 확인")).not.toBeInTheDocument();
  });

  it("자동소멸 없음: durationMs<=0이면 시간이 지나도 유지된다(수동 닫기 전까지)", () => {
    render(
      <ToastProvider>
        <Trigger label="영구 고지" durationMs={0} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "토스트 띄우기" }));
    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    expect(screen.getByText("영구 고지")).toBeInTheDocument();
  });

  it("수동 닫기: ✕ 버튼 클릭 시 자동소멸 유예 전에도 즉시 제거된다", () => {
    render(
      <ToastProvider>
        <Trigger label="수동 닫기 확인" />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "토스트 띄우기" }));
    const toastCard = screen.getByText("수동 닫기 확인").closest('[role="alert"]');
    expect(toastCard).not.toBeNull();

    fireEvent.click(within(toastCard as HTMLElement).getByRole("button", { name: "닫기" }));

    expect(screen.queryByText("수동 닫기 확인")).not.toBeInTheDocument();
  });

  it("useToast()는 ToastProvider 밖에서 호출하면 즉시 에러를 던진다(엄격 계약)", () => {
    const { result } = renderHook(() => {
      try {
        useToast();
        return null;
      } catch (error) {
        return error instanceof Error ? error.message : String(error);
      }
    });

    expect(result.current).toBe("useToast()는 ToastProvider 내부에서만 사용할 수 있습니다.");
  });

  it("useToastOptional()은 ToastProvider 밖에서 null을 반환한다(레거시 통합 지점용 관대한 변형)", () => {
    const { result } = renderHook(() => useToastOptional());
    expect(result.current).toBeNull();
  });

  it("useToastOptional()은 ToastProvider 안에서 push/dismiss를 제공한다", () => {
    const { result } = renderHook(() => useToastOptional(), {
      wrapper: ({ children }) => <ToastProvider>{children}</ToastProvider>,
    });
    expect(result.current).not.toBeNull();
    expect(typeof result.current?.push).toBe("function");
  });
});
