import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "../lib/cn";

type ToastVariant = "default" | "success" | "error" | "warning";

export type ToastProps = HTMLAttributes<HTMLDivElement> & {
  variant?: ToastVariant;
  title?: string;
  description?: string;
  onClose?: () => void;
};

const variantClassName: Record<ToastVariant, string> = {
  default: "border-[var(--line)] bg-[#ffffff]",
  success: "border-[rgb(34,197,94)] bg-[rgba(34,197,94,0.05)]",
  error: "border-[rgb(239,68,68)] bg-[rgba(239,68,68,0.05)]",
  warning: "border-[rgb(234,179,8)] bg-[rgba(234,179,8,0.05)]",
};

export const Toast = forwardRef<HTMLDivElement, ToastProps>(
  ({ className, variant = "default", title, description, onClose, ...props }, ref) => {
    return (
      <div
        ref={ref}
        role="alert"
        className={cn(
          "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-4 shadow-lg",
          variantClassName[variant],
          className,
        )}
        {...props}
      >
        <div className="flex-1">
          {title && (
            <p className="text-sm font-semibold text-[var(--foreground)]">
              {title}
            </p>
          )}
          {description && (
            <p className="mt-1 text-sm text-[var(--muted)]">{description}</p>
          )}
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--muted)] hover:text-[var(--foreground)] transition"
            aria-label="닫기"
          >
            ✕
          </button>
        )}
      </div>
    );
  },
);

Toast.displayName = "Toast";
