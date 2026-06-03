import React from "react";

export function LogoSymbol({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none" className={className}>
      <defs>
        <linearGradient id="grad-main" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="var(--accent-strong, #0d9488)" />
          <stop offset="100%" stopColor="var(--accent, #14b8a6)" />
        </linearGradient>
        <linearGradient id="grad-sub" x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="var(--accent-strong, #0d9488)" stopOpacity="0.8" />
          <stop offset="100%" stopColor="var(--text-primary, #ffffff)" stopOpacity="0.2" />
        </linearGradient>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Outer connecting rings */}
      <circle cx="24" cy="24" r="21" stroke="url(#grad-sub)" strokeWidth="1" strokeDasharray="4 4" className="origin-center animate-[spin_30s_linear_infinite]" />
      
      {/* Hexagon Base */}
      <path d="M24 6L39.588 15V33L24 42L8.412 33V15L24 6Z" fill="url(#grad-sub)" opacity="0.1" />
      <path d="M24 6L39.588 15V33L24 42L8.412 33V15L24 6Z" stroke="url(#grad-main)" strokeWidth="1.5" />
      
      {/* Inner Geometry / Nodes */}
      <path d="M24 6V24L39.588 33" stroke="url(#grad-main)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" filter="url(#glow)" />
      <path d="M8.412 33L24 24" stroke="url(#grad-main)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" filter="url(#glow)" />
      
      {/* Node Dots */}
      <circle cx="24" cy="24" r="3.5" fill="var(--glass-bg, #ffffff)" className="dark:fill-gray-900" />
      <circle cx="24" cy="24" r="1.5" fill="url(#grad-main)" />
      
      {[
        [24, 6], [39.588, 15], [39.588, 33], [24, 42], [8.412, 33], [8.412, 15]
      ].map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r="2.5" fill="url(#grad-main)" />
      ))}
    </svg>
  );
}

export function Logo({ className = "", size = "md", showText = true }: { className?: string; size?: "sm" | "md" | "lg" | "xl"; showText?: boolean }) {
  const sizeMap = {
    sm: { symbol: "h-6 w-6", text: "text-lg", sub: "text-[0.55rem]" },
    md: { symbol: "h-8 md:h-10 w-8 md:w-10", text: "text-2xl md:text-3xl", sub: "text-[0.65rem] md:text-xs" },
    lg: { symbol: "h-12 md:h-16 w-12 md:w-16", text: "text-4xl md:text-5xl", sub: "text-xs md:text-sm" },
    xl: { symbol: "h-16 md:h-20 w-16 md:w-20", text: "text-5xl md:text-6xl", sub: "text-sm md:text-base" },
  };
  
  const current = sizeMap[size];

  return (
    <div className={`flex items-center gap-3 md:gap-4 ${className}`}>
      <LogoSymbol className={`${current.symbol} drop-shadow-lg shrink-0`} />
      {showText && (
        <div className="flex flex-col justify-center whitespace-nowrap min-w-0">
          <span className={`${current.text} font-[900] tracking-tighter text-[var(--text-primary)] leading-none`}>
            <span className="bg-gradient-to-r from-[var(--text-primary)] to-[var(--accent-strong)] bg-clip-text text-transparent">사통</span>팔땅
            <span className="text-[var(--accent-strong)] ml-px">.</span>
          </span>
          <span className={`${current.sub} font-bold tracking-[0.25em] text-[var(--text-tertiary)] uppercase mt-1 opacity-80 leading-none`}>
            AI 부동산 분석
          </span>
        </div>
      )}
    </div>
  );
}
