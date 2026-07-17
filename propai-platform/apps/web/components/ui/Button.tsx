import { ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "sm" | "md" | "lg" | "icon";
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => {
    const baseClasses = "inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none disabled:opacity-50 disabled:pointer-events-none";
    
    const variantClasses = {
      primary: "bg-primary text-white hover:bg-blue-600 shadow-lg shadow-primary/20",
      secondary: "bg-surface-dark text-white hover:bg-card-border border border-card-border",
      outline: "border border-primary text-primary hover:bg-primary/10",
      ghost: "text-slate-400 hover:text-white hover:bg-surface-dark",
      danger: "bg-[var(--status-error)]/10 text-[var(--status-error)] hover:bg-[var(--status-error)] hover:text-white",
    };
    
    const sizeClasses = {
      sm: "h-8 px-3 text-xs",
      md: "h-10 px-4 text-sm",
      lg: "h-12 px-6 text-base",
      icon: "h-10 w-10",
    };

    return (
      <button
        ref={ref}
        className={cn(baseClasses, variantClasses[variant], sizeClasses[size], className)}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
