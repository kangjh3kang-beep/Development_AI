import React from "react";
import Image from "next/image";

export function PromoBanner() {
  return (
    <section className="relative z-10 w-full">
      {/* 외부 분양광고 템플릿 사이트 안내 — 중립 표면 한 줄 배너(강조는 우측 행동 1곳) */}
      <a
        href="http://www.4t8t.app"
        target="_blank"
        rel="noopener noreferrer"
        className="db-promo group flex-col text-center sm:flex-row sm:text-left"
      >
        {/* 로고 (확대) */}
        <div className="flex w-44 shrink-0 items-center justify-center md:w-52">
          <Image
            src="/images/promo-logo.png"
            alt="사통팔땅"
            width={168}
            height={49}
            className="object-contain"
          />
        </div>

        {/* 텍스트 */}
        <div className="flex flex-1 flex-col items-center sm:items-start">
          <span className="db-eyebrow db-eyebrow--ko mb-1">분양광고 마케팅 템플릿</span>
          <h3 className="text-sm font-semibold tracking-tight text-[var(--text-primary)] md:text-base">
            3분 만에 완성하는 분양광고 홈페이지
          </h3>
          <p className="mt-0.5 max-w-2xl text-[13px] leading-snug text-[var(--text-secondary)]">
            분양 마케팅에 특화된 세련된 홈페이지를 누구나 쉽게 만듭니다.
          </p>
        </div>

        {/* 행동 — 텍스트 링크 1곳(강조 색) */}
        <div className="mt-1 flex shrink-0 items-center gap-1.5 text-[13px] font-semibold text-[var(--accent-strong)] transition-transform duration-200 group-hover:translate-x-0.5 sm:mt-0">
          <span>바로가기</span>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
          </svg>
        </div>
      </a>
    </section>
  );
}
