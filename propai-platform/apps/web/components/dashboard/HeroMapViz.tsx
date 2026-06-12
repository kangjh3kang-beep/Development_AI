import React from "react";

/**
 * 히어로 배경 — 'AI가 지도를 분석하는' 비주얼(SVG).
 * 추상적인 격자 대신 실제 지도처럼 보이도록 도로(굵은 선)·필지 블록(폴리곤)·위치 핀을 그린다.
 * 한 지점에서 동심원 펄스가 퍼지고(=그 구역을 분석), 가로 스캔 띠가 천천히 지나간다.
 * 색은 단일 파랑(accent)·저채도. 왼쪽 텍스트 가독성은 CSS 마스크(가장자리 페이드)로 보호한다.
 * 모션 최소화 설정(prefers-reduced-motion)에선 애니메이션이 멈춘다.
 */
export function HeroMapViz() {
  return (
    <div className="db-hero__viz" aria-hidden="true">
      {/* 첨부된 실제 지도 이미지를 우측에 은은하게 배치 */}
      <div 
        className="absolute inset-y-0 right-0 w-[80%] md:w-[60%] lg:w-[50%] bg-[url('/images/korea-map.png')] bg-no-repeat bg-right bg-contain opacity-60 mix-blend-screen"
        style={{
          maskImage: 'linear-gradient(to right, transparent, black 40%)',
          WebkitMaskImage: 'linear-gradient(to right, transparent, black 40%)'
        }}
      />
      <svg
        className="db-hero__map"
        viewBox="0 0 480 320"
        fill="none"
        preserveAspectRatio="xMidYMid slice"
      >
        {/* 도로(굵은 선) — 가장 옅게 */}
        <g stroke="var(--accent-strong)" strokeLinecap="round">
          <path d="M-30 96 L510 72" strokeWidth="7" opacity="0.12" />
          <path d="M-30 214 L510 232" strokeWidth="7" opacity="0.12" />
          <path d="M150 -30 L182 350" strokeWidth="6" opacity="0.12" />
          <path d="M348 -30 L322 350" strokeWidth="6" opacity="0.12" />
        </g>

        {/* 필지 블록(가는 외곽선) — 또렷하게 */}
        <g stroke="var(--accent-strong)" strokeWidth="1.1" opacity="0.34">
          <path d="M30 104 L132 86 L168 158 L70 178 Z" />
          <path d="M188 82 L324 62 L336 138 L200 158 Z" />
          <path d="M352 60 L470 50 L470 138 L364 142 Z" />
          <path d="M196 168 L330 148 L346 224 L206 248 Z" />
          <path d="M48 188 L160 170 L172 252 L62 278 Z" />
          <path d="M356 150 L470 144 L470 234 L344 228 Z" />
        </g>

        {/* 필지 미세 채움(아주 옅게) — 분석 대상 강조 */}
        <g fill="var(--accent-strong)" opacity="0.06">
          <path d="M188 82 L324 62 L336 138 L200 158 Z" />
          <path d="M196 168 L330 148 L346 224 L206 248 Z" />
        </g>

        {/* 위치 핀(분석 포인트) */}
        <g fill="var(--accent-strong)">
          <circle cx="262" cy="110" r="4.5" />
          <circle cx="104" cy="142" r="3" opacity="0.75" />
          <circle cx="408" cy="96" r="3" opacity="0.75" />
          <circle cx="266" cy="198" r="3" opacity="0.65" />
          <circle cx="120" cy="232" r="2.6" opacity="0.6" />
        </g>

        {/* 분석 펄스(동심원) — 메인 포인트에서 퍼짐 */}
        <circle className="db-map-pulse" cx="262" cy="110" r="6" stroke="var(--accent-strong)" strokeWidth="1.4" />
        <circle className="db-map-pulse db-map-pulse--2" cx="262" cy="110" r="6" stroke="var(--accent-strong)" strokeWidth="1.4" />

        {/* 가로 스캔 띠(좌우로 천천히) */}
        <rect className="db-map-scan" x="0" y="0" width="84" height="320" fill="url(#db-hero-scan-grad)" />
        <defs>
          <linearGradient id="db-hero-scan-grad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="var(--accent-strong)" stopOpacity="0" />
            <stop offset="0.5" stopColor="var(--accent-strong)" stopOpacity="0.24" />
            <stop offset="1" stopColor="var(--accent-strong)" stopOpacity="0" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}
