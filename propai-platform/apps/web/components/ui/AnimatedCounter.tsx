"use client";

import { useEffect, useRef, useState } from "react";

interface AnimatedCounterProps {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  className?: string;
}

function easeOutExpo(t: number): number {
  return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
}

export function AnimatedCounter({
  value,
  duration = 1200,
  prefix = "",
  suffix = "",
  decimals = 0,
  className,
}: AnimatedCounterProps) {
  // NaN/undefined 방어 — 비유한 값은 0으로(대시보드 'NaN' 표기 차단)
  const safeValue = Number.isFinite(value) ? value : 0;
  const [display, setDisplay] = useState("0");
  const rafRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const prefersReducedMotion = useRef(false);

  useEffect(() => {
    prefersReducedMotion.current = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
  }, []);

  useEffect(() => {
    if (prefersReducedMotion.current) {
      setDisplay(safeValue.toLocaleString("ko-KR", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }));
      return;
    }

    startTimeRef.current = null;

    const animate = (timestamp: number) => {
      if (!startTimeRef.current) startTimeRef.current = timestamp;
      const elapsed = timestamp - startTimeRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const easedProgress = easeOutExpo(progress);
      const current = easedProgress * safeValue;

      setDisplay(
        current.toLocaleString("ko-KR", {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })
      );

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };

    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [safeValue, duration, decimals]);

  return (
    <span className={className}>
      {prefix}
      {display}
      {suffix}
    </span>
  );
}
