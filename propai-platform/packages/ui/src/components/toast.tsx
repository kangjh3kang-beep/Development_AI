"use client";

import {
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type HTMLAttributes,
  type PropsWithChildren,
} from "react";
import { cn } from "../lib/cn";

type ToastVariant = "default" | "success" | "error" | "warning";

export type ToastProps = HTMLAttributes<HTMLDivElement> & {
  variant?: ToastVariant;
  title?: string;
  description?: string;
  onClose?: () => void;
};

const variantClassName: Record<ToastVariant, string> = {
  default: "border-[var(--line)] bg-[#ffffff]",
  success: "border-[rgb(34,197,94)] bg-[rgba(34,197,94,0.05)]",
  error: "border-[rgb(239,68,68)] bg-[rgba(239,68,68,0.05)]",
  warning: "border-[rgb(234,179,8)] bg-[rgba(234,179,8,0.05)]",
};

export const Toast = forwardRef<HTMLDivElement, ToastProps>(
  ({ className, variant = "default", title, description, onClose, ...props }, ref) => {
    return (
      <div
        ref={ref}
        role="alert"
        className={cn(
          "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-4 shadow-lg",
          variantClassName[variant],
          className,
        )}
        {...props}
      >
        <div className="flex-1">
          {title && (
            <p className="text-sm font-semibold text-[var(--foreground)]">
              {title}
            </p>
          )}
          {description && (
            <p className="mt-1 text-sm text-[var(--text-tertiary)]">{description}</p>
          )}
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition"
            aria-label="닫기"
          >
            ✕
          </button>
        )}
      </div>
    );
  },
);

Toast.displayName = "Toast";

// ── ToastProvider + useToast — 호스트/훅 신설(PropAI UX 트랙 C3) ──────────────────────
// 종전엔 이 파일에 Toast 프리미티브(단일 알림 카드)만 있고, 이를 화면에 실제로 올리는
// 호스트(Provider+Viewport)·훅이 없어 각 페이지가 저마다 인라인 <p> 슬롯으로 알림을
// 흩뿌렸다(사통맵만 4곳: uploadNote·exportNote·connectNotice·searchError). 앱 셸
// 최상위에 <ToastProvider>를 한 번 마운트하면 어느 컴포넌트에서든 useToast().push(...)
// 로 동일한 자리·스타일의 알림을 띄울 수 있다(21개 탭 공용 자산 — 분양앱 UX 트랙 B가
// 같은 자산을 기대 중이므로 신규 구현은 이 한 곳만 유지한다).

export type ToastInput = {
  title?: string;
  description?: string;
  variant?: ToastVariant;
  /** 자동 소멸까지 유예(ms). 0 이하로 주면 자동 소멸하지 않고 수동 닫기만 남는다. 기본 4000ms. */
  durationMs?: number;
};

type ToastEntry = ToastInput & { id: string };

type ToastContextValue = {
  /** 토스트를 큐에 추가하고 id를 반환한다(필요 시 수동 dismiss(id)에 사용). */
  push: (toast: ToastInput) => string;
  /** 토스트를 즉시 제거한다(자동 소멸 타이머도 함께 정리). */
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_TOAST_DURATION_MS = 4000;

let toastIdSeq = 0;
function nextToastId() {
  toastIdSeq += 1;
  return `toast-${toastIdSeq}`;
}

/**
 * 앱 셸 최상위(레이아웃)에 한 번만 마운트한다. children 아래 어디서든 useToast()로
 * 접근 가능 — 이 Provider 없이 useToast()를 호출하면 명시적으로 에러를 던진다
 * (AccessibilityProvider·Tabs와 동일한 기존 컨벤션).
 */
export function ToastProvider({ children }: PropsWithChildren) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const timersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((entry) => entry.id !== id));
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (toast: ToastInput) => {
      const id = nextToastId();
      setToasts((prev) => [...prev, { ...toast, id }]);
      const duration = toast.durationMs ?? DEFAULT_TOAST_DURATION_MS;
      if (duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration);
        timersRef.current.set(id, timer);
      }
      return id;
    },
    [dismiss],
  );

  // 언마운트 시 잔여 타이머 정리(메모리 누수 방지).
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const value = useMemo(() => ({ push, dismiss }), [push, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* aria-live="polite" — 개별 Toast의 role="alert"(assertive)와 별개로, 뷰포트
          자체도 살아있는 영역임을 보조기술에 알린다(AccessibilityProvider 안내자와
          동일한 role="status" 컨벤션). 화면 우하단 고정 — 다른 패널과 겹치지 않게
          z-index를 넉넉히 높인다. */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[1000] flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:right-4 sm:items-end"
      >
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            variant={toast.variant}
            title={toast.title}
            description={toast.description}
            onClose={() => dismiss(toast.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/** ToastProvider 내부에서만 사용할 수 있다(미마운트 시 조용히 무시되지 않고 즉시 에러). */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast()는 ToastProvider 내부에서만 사용할 수 있습니다.");
  }
  return ctx;
}

/**
 * useToast()의 관대한(non-throwing) 변형 — Provider가 없으면 null을 반환한다.
 *
 * 왜 필요한가: 앱 전체는 레이아웃에서 <ToastProvider>를 한 번만 마운트하므로 실사용
 * 경로에서는 항상 값이 채워진다. 다만 기존 컴포넌트(예: SatongMapShell)는 Provider
 * 없이 단독 렌더하는 계약 테스트를 다수 보유하고 있어(무회귀 원칙상 그 테스트들을
 * 건드리지 않는다), 그런 레거시 통합 지점에서는 이 변형으로 "Provider가 있으면
 * 토스트, 없으면 기존 인라인 폴백"을 안전하게 분기한다. 신규 코드는 특별한 이유가
 * 없다면 엄격한 useToast()를 우선 사용할 것.
 */
export function useToastOptional() {
  return useContext(ToastContext);
}
