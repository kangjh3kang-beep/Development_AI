import {
  forwardRef,
  type ButtonHTMLAttributes,
  type PropsWithChildren,
} from "react";
import { cn } from "../lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost";
type ButtonSize = "sm" | "md";

export type ButtonProps = PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    size?: ButtonSize;
  }
>;

const variantClassName: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--accent-strong)] text-[#ffffff] hover:opacity-90 disabled:bg-[rgba(19,33,47,0.3)]",
  secondary:
    "border border-[var(--line)] bg-[var(--surface-soft)] text-[var(--foreground)] hover:bg-[#ffffff]",
  ghost: "bg-transparent text-[var(--foreground)] hover:bg-[var(--surface-soft)]",
};

const sizeClassName: Record<ButtonSize, string> = {
  sm: "px-3 py-2 text-sm",
  md: "px-4 py-2.5 text-sm",
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
          "inline-flex items-center justify-center rounded-full font-semibold transition disabled:cursor-not-allowed",
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
