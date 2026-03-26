import {
  forwardRef,
  type HTMLAttributes,
  type PropsWithChildren,
} from "react";
import { cn } from "../lib/cn";

type CardProps = PropsWithChildren<HTMLAttributes<HTMLDivElement>>;
type CardHeaderProps = PropsWithChildren<HTMLAttributes<HTMLDivElement>>;
type CardTitleProps = PropsWithChildren<HTMLAttributes<HTMLHeadingElement>>;
type CardDescriptionProps = PropsWithChildren<
  HTMLAttributes<HTMLParagraphElement>
>;
type CardContentProps = PropsWithChildren<HTMLAttributes<HTMLDivElement>>;
type CardFooterProps = PropsWithChildren<HTMLAttributes<HTMLDivElement>>;

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "rounded-[1.75rem] border border-[var(--line)] bg-[var(--surface)] shadow-[0_12px_32px_rgba(19,33,47,0.06)]",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);

Card.displayName = "Card";

export const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div ref={ref} className={cn("p-6 pb-0", className)} {...props}>
        {children}
      </div>
    );
  },
);

CardHeader.displayName = "CardHeader";

export const CardTitle = forwardRef<HTMLHeadingElement, CardTitleProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <h3
        ref={ref}
        className={cn("text-xl font-semibold text-[var(--foreground)]", className)}
        {...props}
      >
        {children}
      </h3>
    );
  },
);

CardTitle.displayName = "CardTitle";

export const CardDescription = forwardRef<
  HTMLParagraphElement,
  CardDescriptionProps
>(({ children, className, ...props }, ref) => {
  return (
    <p
      ref={ref}
      className={cn("text-sm leading-7 text-[rgba(19,33,47,0.72)]", className)}
      {...props}
    >
      {children}
    </p>
  );
});

CardDescription.displayName = "CardDescription";

export const CardContent = forwardRef<HTMLDivElement, CardContentProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div ref={ref} className={cn("p-6", className)} {...props}>
        {children}
      </div>
    );
  },
);

CardContent.displayName = "CardContent";

export const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(
  ({ children, className, ...props }, ref) => {
    return (
      <div ref={ref} className={cn("px-6 pb-6", className)} {...props}>
        {children}
      </div>
    );
  },
);

CardFooter.displayName = "CardFooter";
