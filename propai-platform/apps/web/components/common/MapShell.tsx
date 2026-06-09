"use client";

/**
 * 지도·3D 뷰어 표준 래퍼(견고성 전용).
 *
 * 지도/뷰어 컴포넌트가 렌더 중 에러를 던져도 이 래퍼 "안"에서만 잡아
 * "지도를 표시할 수 없습니다 · 다시 시도" 폴백으로 바꾼다.
 * 덕분에 라우트 전체(사이드바·다른 메뉴)는 영향받지 않고 이동도 막히지 않는다.
 *
 * - MapErrorBoundary: 자체 구현 React 에러 경계(클래스). 부모 라우팅 불간섭.
 * - MapShell: 에러 경계 + Suspense fallback 을 묶은 래퍼.
 * - dynamicMap(): dynamic(ssr:false) 로딩 스켈레톤 헬퍼(SSR throw 차단).
 *
 * ※ 데이터/props/동작은 일절 바꾸지 않는다. 견고성 래핑만 담당.
 */

import { Component, Suspense, type ReactNode } from "react";
import dynamic from "next/dynamic";

/* ── 공용 폴백 UI ── */
function MapFallback({
  message,
  onRetry,
  height,
}: {
  message: string;
  onRetry?: () => void;
  height?: number | string;
}) {
  return (
    <div
      className="flex w-full flex-col items-center justify-center gap-3 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-muted)] p-6 text-center"
      style={{ minHeight: height ?? 320 }}
    >
      <span className="text-sm font-bold text-[var(--text-secondary)]">{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg bg-[var(--accent-strong)] px-4 py-1.5 text-xs font-bold text-white transition-all hover:brightness-110"
        >
          다시 시도
        </button>
      )}
    </div>
  );
}

/* ── 자체 구현 에러 경계(클래스) ── */
class MapErrorBoundary extends Component<
  { children: ReactNode; height?: number | string; label?: string },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode; height?: number | string; label?: string }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  // 에러를 이 경계 안에 가둔다(라우트 error.tsx로 전파 안 됨 = 네비 멈춤 없음).
  componentDidCatch() {
    /* 콘솔 노이즈 방지: 폴백 렌더로 충분. 필요 시 로깅 훅 추가 지점. */
  }

  // 재시도 = 이 경계만 다시 마운트(부모 라우팅 불간섭).
  reset = () => this.setState({ hasError: false });

  render() {
    if (this.state.hasError) {
      return (
        <MapFallback
          message={this.props.label ?? "지도를 표시할 수 없습니다"}
          onRetry={this.reset}
          height={this.props.height}
        />
      );
    }
    return this.props.children;
  }
}

/* ── 표준 래퍼 ── */
export function MapShell({
  children,
  height,
  label,
  loadingMessage = "지도 로딩…",
}: {
  children: ReactNode;
  /** 폴백/스켈레톤 최소 높이(px 또는 CSS 길이). */
  height?: number | string;
  /** 에러 폴백 문구(지도/3D 등 맥락별). */
  label?: string;
  /** Suspense 로딩 문구. */
  loadingMessage?: string;
}) {
  return (
    <MapErrorBoundary height={height} label={label}>
      <Suspense fallback={<MapFallback message={loadingMessage} height={height} />}>
        {children}
      </Suspense>
    </MapErrorBoundary>
  );
}

/**
 * 지도/뷰어 컴포넌트를 SSR 없이 동적 로드한다(SSR 단계 throw 차단).
 * named export 모듈은 pick 으로 선택.
 *
 * @example const Map = dynamicMap(() => import("@/components/map/Foo"), { pick: "Foo" });
 */
export function dynamicMap<P>(
  loader: () => Promise<{ default: React.ComponentType<P> } | Record<string, React.ComponentType<P>>>,
  opts: { pick?: string; height?: number | string; loadingMessage?: string } = {},
) {
  const { pick, height, loadingMessage = "지도 로딩…" } = opts;
  return dynamic<P>(
    async () => {
      const mod = await loader();
      const comp = pick
        ? (mod as Record<string, React.ComponentType<P>>)[pick]
        : (mod as { default: React.ComponentType<P> }).default;
      return { default: comp };
    },
    {
      ssr: false,
      loading: () => <MapFallback message={loadingMessage} height={height} />,
    },
  );
}

export { MapErrorBoundary };
