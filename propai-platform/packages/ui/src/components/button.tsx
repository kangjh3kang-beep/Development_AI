import {
  forwardRef,
  type ButtonHTMLAttributes,
  type PropsWithChildren,
} from "react";
import { cn } from "../lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

export type ButtonProps = PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    size?: ButtonSize;
  }
>;

const variantClassName: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-xs)] hover:bg-[var(--accent)] hover:shadow-[var(--shadow-sm)] active:scale-[0.98] disabled:bg-[var(--surface-muted)] disabled:text-[var(--text-hint)] disabled:shadow-none",
  secondary:
    "border border-[var(--line-strong)] bg-[var(--surface)] text-[var(--text-primary)] shadow-[var(--shadow-xs)] hover:bg-[var(--surface-soft)] hover:border-[var(--line-strong)] active:scale-[0.98]",
  ghost:
    "bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] hover:text-[var(--text-primary)]",
};

const sizeClassName: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-sm gap-2.5",
};

// ★UX 트랙 D(터치 44px 하한 — 진단G 실측): sm(32px)·md(40px)는 WCAG 2.5.5/모바일 터치
//   타깃 44px에 못 미친다. min-height를 프리미티브 기본값으로 얹어 전역 전파한다 —
//   h-8/h-10 고정 높이 위에 min-h가 바닥으로 얹히므로(min-height가 더 크면 그 값이
//   이김) sm/md 모두 시각 크기(padding·폰트)는 그대로 두고 실제 히트영역만 44px로
//   플로어링된다. lg(48px)는 이미 상회해 무영향.
const TOUCH_TARGET_MIN_HEIGHT = "min-h-11";

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      className,
      type = "button",
      variant = "primary",
      size = "md",
      ...props
    },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        type={type}
        className={cn(
          "inline-flex items-center justify-center rounded-full font-semibold transition-all duration-200 disabled:cursor-not-allowed",
          TOUCH_TARGET_MIN_HEIGHT,
          variantClassName[variant],
          sizeClassName[size],
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);

Button.displayName = "Button";
