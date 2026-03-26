"use client";

import {
  forwardRef,
  useState,
  useRef,
  useEffect,
  type HTMLAttributes,
  type PropsWithChildren,
} from "react";
import { cn } from "../lib/cn";

export type DropdownProps = PropsWithChildren<HTMLAttributes<HTMLDivElement>>;

export const Dropdown = forwardRef<HTMLDivElement, DropdownProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div ref={ref} className={cn("relative inline-block", className)} {...props}>
        {children}
      </div>
    );
  },
);
Dropdown.displayName = "Dropdown";

export type DropdownTriggerProps = PropsWithChildren<
  HTMLAttributes<HTMLButtonElement>
>;

export const DropdownTrigger = forwardRef<HTMLButtonElement, DropdownTriggerProps>(
  ({ children, className, onClick, ...props }, ref) => {
    return (
      <button
        ref={ref}
        type="button"
        className={cn("inline-flex items-center", className)}
        onClick={onClick}
        {...props}
      >
        {children}
      </button>
    );
  },
);
DropdownTrigger.displayName = "DropdownTrigger";

export type DropdownMenuProps = PropsWithChildren<
  HTMLAttributes<HTMLDivElement> & {
    open?: boolean;
    onClose?: () => void;
    align?: "left" | "right";
  }
>;

export const DropdownMenu = forwardRef<HTMLDivElement, DropdownMenuProps>(
  ({ children, className, open, onClose, align = "left", ...props }, ref) => {
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
      if (!open) return;
      const handler = (e: MouseEvent) => {
        if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
          onClose?.();
        }
      };
      document.addEventListener("mousedown", handler);
      return () => document.removeEventListener("mousedown", handler);
    }, [open, onClose]);

    if (!open) return null;

    return (
      <div
        ref={menuRef}
        className={cn(
          "absolute z-50 mt-1 min-w-[160px] rounded-lg border border-[var(--line)] bg-[#ffffff] py-1 shadow-lg",
          align === "right" ? "right-0" : "left-0",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);
DropdownMenu.displayName = "DropdownMenu";

export type DropdownItemProps = PropsWithChildren<
  HTMLAttributes<HTMLButtonElement> & { disabled?: boolean }
>;

export const DropdownItem = forwardRef<HTMLButtonElement, DropdownItemProps>(
  ({ children, className, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        type="button"
        disabled={disabled}
        className={cn(
          "flex w-full items-center px-3 py-2 text-sm text-[var(--foreground)] hover:bg-[var(--surface-soft)] transition",
          disabled && "cursor-not-allowed opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
DropdownItem.displayName = "DropdownItem";
