"use client";

import { useEffect, useState } from "react";

type StreamingTextProps = {
  text: string;
  className?: string;
  stepMs?: number;
};

export function StreamingText({
  text,
  className,
  stepMs = 14,
}: StreamingTextProps) {
  const [visibleLength, setVisibleLength] = useState(0);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

    if (mediaQuery.matches) {
      const timeout = window.setTimeout(() => {
        setVisibleLength(text.length);
      }, 0);

      return () => {
        window.clearTimeout(timeout);
      };
    }

    const interval = window.setInterval(() => {
      setVisibleLength((current) => {
        if (current >= text.length) {
          window.clearInterval(interval);
          return text.length;
        }

        return Math.min(current + 3, text.length);
      });
    }, stepMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [stepMs, text]);

  return (
    <p aria-live="polite" className={className}>
      {text.slice(0, visibleLength)}
    </p>
  );
}
