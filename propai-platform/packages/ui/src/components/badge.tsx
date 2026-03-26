import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "../lib/cn";

type BadgeVariant = "default" | "success" | "warning" | "error" | "info";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant;
};

const variantClassName: Record<BadgeVariant, string> = {
  default:
    "bg-[var(--surface-soft)] text-[var(--foreground)]",
  success:
    "bg-[rgba(34,197,94,0.15)] text-[rgb(22,163,74)]",
  warning:
    "bg-[rgba(234,179,8,0.15)] text-[rgb(161,98,7)]",
  error:
    "bg-[rgba(239,68,68,0.15)] text-[rgb(220,38,38)]",
  info:
    "bg-[rgba(59,130,246,0.15)] text-[rgb(37,99,235)]",
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ children, className, variant = "default", ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
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
