"use client";

import { forwardRef, useState, type ImgHTMLAttributes } from "react";
import { cn } from "../lib/cn";

type AvatarSize = "sm" | "md" | "lg";

export type AvatarProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "size"> & {
  size?: AvatarSize;
  fallback?: string;
};

const sizeClassName: Record<AvatarSize, string> = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-14 w-14 text-base",
};

export const Avatar = forwardRef<HTMLSpanElement, AvatarProps>(
  ({ className, size = "md", src, alt, fallback, ...props }, ref) => {
    const [hasError, setHasError] = useState(false);
    const showFallback = !src || hasError;

    const initials =
      fallback ??
      (alt
        ?.split(" ")
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase() || "?");

    return (
      <span
        ref={ref}
        className={cn(
          "relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-[var(--surface-soft)]",
          sizeClassName[size],
          className,
        )}
      >
        {showFallback ? (
          <span className="font-medium text-[var(--text-tertiary)]">{initials}</span>
        ) : (
          <img
            src={src}
            alt={alt}
            onError={() => setHasError(true)}
            className="h-full w-full object-cover"
            {...props}
          />
        )}
      </span>
    );
  },
);

Avatar.displayName = "Avatar";
