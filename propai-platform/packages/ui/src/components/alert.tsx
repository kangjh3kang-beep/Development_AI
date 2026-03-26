import { forwardRef, type HTMLAttributes, type PropsWithChildren } from "react";
import { cn } from "../lib/cn";

type AlertVariant = "info" | "success" | "warning" | "error";

export type AlertProps = PropsWithChildren<
  HTMLAttributes<HTMLDivElement> & {
    variant?: AlertVariant;
    title?: string;
  }
>;

const variantClassName: Record<AlertVariant, string> = {
  info: "border-[rgb(59,130,246)] bg-[rgba(59,130,246,0.05)] text-[rgb(37,99,235)]",
  success: "border-[rgb(34,197,94)] bg-[rgba(34,197,94,0.05)] text-[rgb(22,163,74)]",
  warning: "border-[rgb(234,179,8)] bg-[rgba(234,179,8,0.05)] text-[rgb(161,98,7)]",
  error: "border-[rgb(239,68,68)] bg-[rgba(239,68,68,0.05)] text-[rgb(220,38,38)]",
};

export const Alert = forwardRef<HTMLDivElement, AlertProps>(
  ({ children, className, variant = "info", title, ...props }, ref) => {
    return (
      <div
        ref={ref}
        role="alert"
        className={cn(
          "rounded-lg border-l-4 p-4",
          variantClassName[variant],
          className,
        )}
        {...props}
      >
        {title && (
          <p className="mb-1 text-sm font-semibold">{title}</p>
        )}
        <div className="text-sm">{children}</div>
      </div>
    );
  },
);

Alert.displayName = "Alert";
