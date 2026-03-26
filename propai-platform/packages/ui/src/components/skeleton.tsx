import { type HTMLAttributes } from "react";
import { cn } from "../lib/cn";

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-[1.25rem] bg-[rgba(19,33,47,0.08)]",
        className,
      )}
      {...props}
    />
  );
}
