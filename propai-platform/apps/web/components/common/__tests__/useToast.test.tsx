/**
 * ToastProvider + useToast() 신규 프리미티브(@propai/ui) 단위 테스트 — UX 트랙 C3.
 *
 * 왜 필요한가: SatongMapShell의 uploadNote·exportNote·connectNotice·searchError 4개
 * 인라인 알림 슬롯을 흡수할 공용 호스트/훅이다. Toast 프리미티브 자체(packages/ui/src/
 * components/toast.tsx)는 있었지만 이를 화면에 올리는 Provider·훅이 없었다 — 이 스위트가
 * 그 신규 부분(표시·자동소멸·수동닫기·aria)을 고정한다.
 *
 * ★R1 후속(2026-07-24, MEDIUM): Provider가 실제로 있을 때 exportNote 성공 경로
 * (useToastOptional().push)가 진짜로 토스트를 띄우는지, 다중 토스트 동시 표시, 언마운트
 * 시 타이머 정리(누수 없음)가 미검증이었다 — 아래 세 케이스로 닫는다. 자동소멸 타이머
 * "제거" 변이는 기존 테스트가 이미 잡으므로, 이번엔 언마운트-클린업 "제거" 변이를 주입해
 * 신규 테스트가 잡는지 확인했다(아래 커밋 메시지 참조).
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

// ★SatongMapShell의 exportSelection과 동일 모양 — useToastOptional()이 Provider 발견 시
//   실제로 push하는지 검증하는 통합형 트리거(레거시 통합 지점 재현).
function OptionalTrigger({ label = "옵셔널 고지" }: { label?: string }) {
  const toast = useToastOptional();
  return (
    <button
      type="button"
      onClick={() => {
        if (toast) {
          toast.push({ variant: "success", description: label });
        }
      }}
    >
      옵셔널 토스트 띄우기
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

  it("aria: 개별 토스트가 role=alert를 갖고, 뷰포트는 라이브 리전을 중복하지 않는다(R1 후속 — 이중 안내 방지)", () => {
    render(
      <ToastProvider>
        <Trigger label="접근성 확인" />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "토스트 띄우기" }));

    // 각 토스트 자체가 role="alert"(assertive 라이브 리전)를 갖는다 — 안내 책임은 이 한 곳.
    expect(screen.getByRole("alert")).toHaveTextContent("접근성 확인");
    // 뷰포트 컨테이너는 별도의 role=status/aria-live를 더 이상 갖지 않는다(이중 안내 방지 —
    // 스크린리더가 부모 polite 변이 + 자식 alert를 두 번 안내하지 않도록 단일화했다).
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
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

  // ★R1 후속(MEDIUM①): Provider가 있을 때 useToastOptional().push가 실제로 화면에
  //   토스트를 띄우는지 — SatongMapShell exportSelection의 성공 경로(C3 적용)를 그대로
  //   재현한다(Provider 없을 때의 인라인 폴백 분기는 SatongMapShell 자체 테스트가 커버).
  it("useToastOptional(): Provider가 있으면 push가 실제로 토스트를 띄운다(exportNote 성공경로 재현)", () => {
    render(
      <ToastProvider>
        <OptionalTrigger label="GeoJSON 3필지 내보냄" />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "옵셔널 토스트 띄우기" }));

    expect(screen.getByText("GeoJSON 3필지 내보냄")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("GeoJSON 3필지 내보냄");
  });

  // ★R1 후속(MEDIUM②-a): 다중 토스트가 동시에 쌓이는지(각 push가 이전 토스트를 밀어내지
  //   않는다).
  it("다중: 여러 토스트가 동시에 화면에 쌓인다", () => {
    render(
      <ToastProvider>
        <Trigger label="첫 번째 고지" />
        <Trigger label="두 번째 고지" />
      </ToastProvider>,
    );

    const buttons = screen.getAllByRole("button", { name: "토스트 띄우기" });
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);

    expect(screen.getByText("첫 번째 고지")).toBeInTheDocument();
    expect(screen.getByText("두 번째 고지")).toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(2);
  });

  // ★R1 후속(MEDIUM②-b): 언마운트 시 대기 중이던 자동소멸 타이머가 실제로 clearTimeout
  //   되는지(누수 방지) — 자동소멸 "타이머 제거" 변이는 기존 테스트가 이미 잡으므로, 이번엔
  //   "언마운트 클린업 제거" 변이를 노린다. clearTimeout 호출 여부로 직접 계측한다(React
  //   18+는 언마운트 후 setState를 더 이상 console 경고로 알리지 않아, 경고 유무로는 이
  //   회귀를 못 잡는다 — 실제 계약은 "타이머가 지워진다"이지 "경고가 없다"가 아니다).
  it("언마운트: 대기 중인 자동소멸 타이머가 clearTimeout으로 정리된다(누수 방지)", () => {
    const clearTimeoutSpy = vi.spyOn(global, "clearTimeout");
    const { unmount } = render(
      <ToastProvider>
        <Trigger label="언마운트 전 고지" durationMs={5000} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "토스트 띄우기" }));
    expect(screen.getByText("언마운트 전 고지")).toBeInTheDocument();

    const callsBeforeUnmount = clearTimeoutSpy.mock.calls.length;
    unmount();

    expect(clearTimeoutSpy.mock.calls.length).toBeGreaterThan(callsBeforeUnmount);
    clearTimeoutSpy.mockRestore();
  });
});
