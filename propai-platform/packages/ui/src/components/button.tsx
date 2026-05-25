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
