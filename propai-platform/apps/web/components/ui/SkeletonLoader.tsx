import { Skeleton } from "@propai/ui";

type SkeletonLoaderProps = {
  count?: number;
  className?: string;
  itemClassName?: string;
};

export function SkeletonLoader({
  count = 3,
  className,
  itemClassName = "h-24",
}: SkeletonLoaderProps) {
  return (
    <div className={`grid gap-3 ${className ?? ""}`}>
      {Array.from({ length: count }).map((_, index) => (
        <Skeleton key={index} className={itemClassName} />
      ))}
    </div>
  );
}
