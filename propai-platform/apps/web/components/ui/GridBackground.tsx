"use client";

import { useEffect, useRef, useState } from "react";

interface GridBackgroundProps {
  className?: string;
}

export function GridBackground({ className = "" }: GridBackgroundProps) {
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    setReduceMotion(
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }, []);

  // Use a unique ID suffix to avoid SVG ID collisions when multiple instances exist
  const idRef = useRef(Math.random().toString(36).slice(2, 8));
  const id = idRef.current;

  return (
    <div
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden="true"
    >
      <svg
        className="absolute inset-0 h-full w-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern
            id={`grid-pattern-${id}`}
            width="40"
            height="40"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 40 0 L 0 0 0 40"
              fill="none"
              stroke="var(--line-subtle)"
              strokeWidth="0.5"
            />
          </pattern>
          <radialGradient id={`grid-fade-${id}`} cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="white" stopOpacity="1" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
          <mask id={`grid-mask-${id}`}>
            <rect width="100%" height="100%" fill={`url(#grid-fade-${id})`} />
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill={`url(#grid-pattern-${id})`}
          mask={`url(#grid-mask-${id})`}
          opacity="0.4"
        />
        {/* Intersection dots with subtle pulse */}
        <g mask={`url(#grid-mask-${id})`}>
          {Array.from({ length: 5 }).map((_, row) =>
            Array.from({ length: 8 }).map((_, col) => (
              <circle
                key={`${row}-${col}`}
                cx={col * 120 + 80}
                cy={row * 120 + 80}
                r="1.5"
                fill="var(--accent-strong)"
                opacity={reduceMotion ? "0.25" : "0.3"}
              >
                {!reduceMotion && (
                  <animate
                    attributeName="opacity"
                    values="0.15;0.5;0.15"
                    dur={`${3 + ((row + col) % 3)}s`}
                    repeatCount="indefinite"
                    begin={`${(row * 0.5 + col * 0.3).toFixed(1)}s`}
                  />
                )}
              </circle>
            ))
          )}
        </g>
      </svg>
    </div>
  );
}
