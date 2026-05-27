import { forwardRef, type SelectHTMLAttributes } from "react";
import { cn } from "../lib/cn";

export type SelectOption = {
  label: string;
  value: string;
  disabled?: boolean;
};

export type SelectProps = Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "children"
> & {
  label?: string;
  options: SelectOption[];
  onValueChange?: (value: string) => void;
};

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, onChange, onValueChange, options, ...props }, ref) => {
    return (
      <label className="flex items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-sm font-medium text-[var(--foreground)]">
        {label ? <span>{label}</span> : null}
        <select
          ref={ref}
          className={cn(
            "rounded-full bg-transparent px-2 py-1 outline-none",
            className,
          )}
          onChange={(event) => {
            onChange?.(event);
            onValueChange?.(event.target.value);
          }}
          {...props}
        >
          {options.map((option) => (
            <option
              key={option.value}
              value={option.value}
              disabled={option.disabled}
              className="bg-[var(--surface-soft)] text-[var(--foreground)]"
            >
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  },
);

Select.displayName = "Select";
