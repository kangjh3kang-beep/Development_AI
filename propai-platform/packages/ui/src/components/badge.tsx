import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "../lib/cn";

type BadgeVariant = "default" | "success" | "warning" | "error" | "info";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant;
};

const variantClassName: Record<BadgeVariant, string> = {
  default:
    "bg-[var(--surface-soft)] text-[var(--text-secondary)]",
  success:
    "bg-[var(--success-soft)] text-[var(--success)]",
  warning:
    "bg-[var(--warning-soft)] text-[var(--warning)]",
  error:
    "bg-[var(--error-soft)] text-[var(--error)]",
  info:
    "bg-[var(--info-soft)] text-[var(--info)]",
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ children, className, variant = "default", ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
          variantClassName[variant],
          className,
        )}
        {...props}
      >
        {children}
      </span>
    );
  },
);

Badge.displayName = "Badge";
