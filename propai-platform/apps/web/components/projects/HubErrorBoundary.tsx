"use client";

/**
 * HubErrorBoundary — 프로젝트 허브 영역용 React 에러 바운더리(class).
 *
 * 자식 렌더 중 발생하는 오류(특히 React #185 "Maximum update depth exceeded" 무한 루프 등)가
 * 페이지 전체를 사망(흰 화면)시키지 않도록, 해당 영역만 컴팩트한 인라인 폴백으로 격리한다.
 *  · getDerivedStateFromError: 오류 발생 시 상태를 폴백으로 전환.
 *  · componentDidCatch: error.message·componentStack을 console.error로 남겨 진단 가능하게.
 *  · ★1회 자동복구: 첫 오류면 짧은 지연 뒤 자식을 자동 재마운트한다. persist hydration/바인딩
 *    경합 같은 '일시' 오류("새로고침하면 정상")를 사용자 클릭 없이 자가치유한다.
 *  · 재시도 버튼: 상태를 리셋해 자식을 1회 다시 마운트(일시 오류 회복).
 *  · 무한 재마운트 방지: 같은 영역에서 2회 이상 터지면 자동복구·재시도 버튼을 모두 차단한다(루프 차단).
 *
 * 디자인 토큰만 사용(다크 기본). hooks 미사용(에러 바운더리는 class만 가능).
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface HubErrorBoundaryProps {
  children: ReactNode;
  /** 폴백에 표시할 영역명(선택). 예: "분석 요약". */
  label?: string;
}

interface HubErrorBoundaryState {
  hasError: boolean;
  /** 같은 바운더리에서 오류가 몇 번 터졌는지 — 2회 이상이면 재시도 숨김(무한 재마운트 차단). */
  errorCount: number;
}

export class HubErrorBoundary extends Component<HubErrorBoundaryProps, HubErrorBoundaryState> {
  /** 1회 자동복구 타이머(언마운트 시 정리). */
  private autoRetryTimer: ReturnType<typeof setTimeout> | null = null;
  /** 자동복구를 이미 1회 시도했는지 — 자동 재마운트 무한루프 방지. */
  private autoRetried = false;

  constructor(props: HubErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, errorCount: 0 };
  }

  static getDerivedStateFromError(): Partial<HubErrorBoundaryState> {
    // 렌더 오류 발생 → 폴백으로 전환(errorCount는 didCatch에서 누적).
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // 진단용 로그 — 메시지와 컴포넌트 스택을 남긴다(무한 루프 추적에 필수).
    console.error(
      `[HubErrorBoundary${this.props.label ? ` · ${this.props.label}` : ""}] 렌더 오류:`,
      error?.message,
      errorInfo?.componentStack,
    );
    this.setState((prev) => ({ errorCount: prev.errorCount + 1 }));
    // ★1회 자동복구: 첫 오류면 짧은 지연(hydration/바인딩 경합 진정) 뒤 자식을 자동 재마운트.
    //   '일시' 오류는 사용자 클릭 없이 자가치유하고, 재차 터지면 errorCount≥2로 영구 차단(폭주 방지).
    if (!this.autoRetried) {
      this.autoRetried = true;
      this.autoRetryTimer = setTimeout(() => {
        this.autoRetryTimer = null;
        this.setState({ hasError: false });
      }, 280);
    }
  }

  componentWillUnmount(): void {
    if (this.autoRetryTimer) clearTimeout(this.autoRetryTimer);
  }

  handleRetry = (): void => {
    // 상태 리셋 → 자식 1회 재마운트(일시 오류 회복 시도). errorCount는 유지해 반복 폭주를 막는다.
    this.setState({ hasError: false });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      // 같은 영역에서 2회 이상 터지면 재시도 버튼 숨김(동일 오류 무한 재마운트 차단).
      const canRetry = this.state.errorCount < 2;
      return (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-muted)] text-[var(--text-hint)]">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <path d="M12 9v4M12 17h.01" />
              </svg>
            </span>
            <span className="text-[var(--text-secondary)]">
              {this.props.label ? `${this.props.label} 영역` : "이 영역"} 표시 중 일시 오류 ·
              새로고침하면 정상 표시될 수 있습니다.
            </span>
          </div>
          {canRetry && (
            <button
              type="button"
              onClick={this.handleRetry}
              className="inline-flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-[11px] font-black uppercase tracking-[0.15em] text-[var(--text-primary)] transition-all hover:scale-105"
            >
              다시 시도
            </button>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
