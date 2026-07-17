import { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "primary" | "success" | "warning" | "danger" | "outline";
}

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  const baseClasses = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors";
  
  const variantClasses = {
    default: "bg-surface-dark text-slate-300 border border-card-border",
    primary: "bg-primary/20 text-blue-400 border border-primary/30",
    success: "bg-[var(--status-success)]/20 text-[var(--status-success)] border border-[var(--status-success)]/30",
    warning: "bg-[var(--status-warning)]/20 text-[var(--status-warning)] border border-[var(--status-warning)]/30",
    danger: "bg-[var(--status-error)]/20 text-[var(--status-error)] border border-[var(--status-error)]/30",
    outline: "border border-slate-700 text-slate-300",
  };

  return (
    <span
      className={cn(baseClasses, variantClasses[variant], className)}
      {...props}
    />
  );
}
