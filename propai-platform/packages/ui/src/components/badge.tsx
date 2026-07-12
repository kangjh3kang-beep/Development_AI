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
    "bg-[color-mix(in_srgb,var(--status-success)_14%,transparent)] text-[var(--status-success)]",
  warning:
    "bg-[color-mix(in_srgb,var(--status-warning)_14%,transparent)] text-[var(--status-warning)]",
  error:
    "bg-[color-mix(in_srgb,var(--status-error)_14%,transparent)] text-[var(--status-error)]",
  info:
    "bg-[color-mix(in_srgb,var(--status-info)_14%,transparent)] text-[var(--status-info)]",
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
