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
    success: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    warning: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
    danger: "bg-red-500/20 text-red-400 border border-red-500/30",
    outline: "border border-slate-700 text-slate-300",
  };

  return (
    <span
      className={cn(baseClasses, variantClasses[variant], className)}
      {...props}
    />
  );
}
