import { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  variant?: "default" | "surface" | "primary" | "warning" | "danger" | "success";
  glassEffect?: boolean;
}

export function GlassCard({
  children,
  className,
  variant = "default",
  glassEffect = true,
  ...props
}: GlassCardProps) {
  const baseClasses = "rounded-xl border overflow-hidden transition-all duration-300";
  
  const glassClasses = glassEffect ? "backdrop-blur-xl bg-opacity-80" : "";
  
  const variantClasses = {
    default: "bg-background-dark/80 border-card-border hover:border-slate-700",
    surface: "bg-surface-dark/90 border-card-border hover:border-slate-700",
    primary: "bg-primary/10 border-primary/30 shadow-[0_0_15px_rgba(19,91,236,0.15)]",
    warning: "bg-amber-500/10 border-amber-500/30",
    danger: "bg-red-500/10 border-red-500/30",
    success: "bg-emerald-500/10 border-emerald-500/30",
  };

  return (
    <div
      className={cn(baseClasses, variantClasses[variant], glassClasses, className)}
      {...props}
    >
      {children}
    </div>
  );
}
