import React from "react";
import Image from "next/image";

export function PromoBanner() {
  return (
    <section className="w-full mb-12 relative z-10 group">
      <a
        href="http://www.4t8t.app"
        target="_blank"
        rel="noopener noreferrer"
        className="block relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-gradient-to-r from-[var(--surface-soft)] via-[#131b2c] to-[var(--surface-soft)] p-1 shadow-lg hover:shadow-[var(--shadow-glow)] hover:-translate-y-1 transition-all duration-500"
      >
        {/* Animated background glowing effect */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[var(--accent)]/10 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000"></div>
        <div className="absolute top-0 right-1/4 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl group-hover:bg-amber-500/20 transition-all duration-700"></div>
        <div className="absolute bottom-0 left-1/4 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl group-hover:bg-blue-500/20 transition-all duration-700"></div>

        <div className="relative z-10 flex flex-col md:flex-row items-center gap-8 px-8 py-10 md:py-12 bg-[#0c1220]/80 backdrop-blur-xl rounded-[1.8rem] h-full">
          {/* Logo Section */}
          <div className="flex-shrink-0 w-48 md:w-56 flex items-center justify-center">
            <Image 
              src="/images/promo-logo.png" 
              alt="사통팔땅" 
              width={220} 
              height={80} 
              className="object-contain drop-shadow-2xl hover:scale-105 transition-transform duration-500"
            />
          </div>

          {/* Text Content */}
          <div className="flex-1 flex flex-col items-center md:items-start text-center md:text-left">
            <div className="inline-block px-3 py-1 mb-3 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 text-[11px] font-bold tracking-widest uppercase">
              분양광고 마케팅사이트 템플릿 제공
            </div>
            
            <h3 className="text-2xl md:text-3xl lg:text-4xl font-[900] text-white tracking-tight mb-4">
              <span className="bg-gradient-to-r from-amber-200 to-amber-500 bg-clip-text text-transparent">3분 만에</span> 완성하는<br className="hidden md:block" />
              분양광고 홈페이지!
            </h3>
            
            <p className="text-base md:text-lg text-slate-300 font-medium leading-relaxed max-w-2xl">
              누구나 쉽게 분양광고 마케팅에 특화된 나만의 세련된 홈페이지를 만듭니다.<br className="hidden md:block" />
              <strong className="text-amber-300 font-bold">고객이 찾는 홈페이지</strong>, 사통팔땅과 함께 지금 시작하세요.
            </p>
          </div>

          {/* Call to Action Button */}
          <div className="flex-shrink-0 mt-6 md:mt-0">
            <div className="flex h-14 items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-amber-500 to-amber-600 px-8 text-sm font-bold text-white shadow-lg shadow-amber-500/30 transition-all group-hover:scale-105 group-hover:shadow-amber-500/50">
              <span>바로가기</span>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="transition-transform group-hover:translate-x-1">
                <path d="M5 12h14"></path>
                <path d="m12 5 7 7-7 7"></path>
              </svg>
            </div>
          </div>
        </div>
      </a>
    </section>
  );
}
