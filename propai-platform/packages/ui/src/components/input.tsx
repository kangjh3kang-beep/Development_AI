import {
  forwardRef,
  type InputHTMLAttributes,
  type PropsWithChildren,
} from "react";
import { cn } from "../lib/cn";

export type InputProps = PropsWithChildren<
  InputHTMLAttributes<HTMLInputElement> & {
    invalid?: boolean;
  }
>;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, invalid = false, ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={cn(
          "w-full rounded-[1rem] border bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition placeholder:text-[rgba(19,33,47,0.4)] focus:border-[var(--accent)]",
          invalid
            ? "border-[rgba(217,119,6,0.65)]"
            : "border-[var(--line)]",
          className,
        )}
        {...props}
      />
    );
  },
);

Input.displayName = "Input";
