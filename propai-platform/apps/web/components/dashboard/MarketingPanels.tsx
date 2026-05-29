import React from "react";

export function MarketingPanels() {
  return (
    <section className="w-full mb-16 relative z-10">
      <div className="flex flex-col gap-3 mb-8">
        <h2 className="text-2xl md:text-3xl font-[900] tracking-tighter text-[var(--text-primary)]">
          압도적인 <span className="bg-gradient-to-r from-[var(--accent-strong)] to-[var(--accent)] bg-clip-text text-transparent">AI 기술력</span>으로 시장을 선도하세요
        </h2>
        <p className="text-[var(--text-secondary)] font-medium max-w-2xl">
          사통팔땅 플랫폼은 단순한 데이터 조회를 넘어, 최신 인공지능 트렌드를 융합하여 당신의 부동산 개발 비즈니스를 완전히 새로운 차원으로 끌어올립니다.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 auto-rows-[240px]">
        
        {/* Panel 1: Large Featured (spans 2 columns on desktop) */}
        <div className="md:col-span-2 relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-gradient-to-br from-[var(--surface-soft)] to-[var(--surface)] p-8 shadow-sm hover:shadow-[var(--shadow-glow)] hover:border-[var(--accent)]/50 transition-all duration-500 group">
          <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--accent-strong)]/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4 group-hover:bg-[var(--accent-strong)]/20 transition-all duration-700"></div>
          <div className="relative z-10 h-full flex flex-col justify-between">
            <div className="flex items-center gap-3">
              <span className="flex items-center justify-center h-10 w-10 rounded-full bg-[var(--accent)]/10 text-[var(--accent-strong)] border border-[var(--accent)]/20">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>
              </span>
              <span className="text-sm font-bold tracking-widest text-[var(--text-tertiary)] uppercase">Core Engine</span>
            </div>
            <div>
              <h3 className="text-2xl md:text-3xl font-extrabold text-[var(--text-primary)] mb-3 tracking-tight group-hover:text-[var(--accent-strong)] transition-colors">초고속 AI 입지 및 상권 분석</h3>
              <p className="text-[var(--text-secondary)] font-medium leading-relaxed max-w-md">
                전국 수백만 필지의 토지 대장, 도시계획 조례, 실거래가 빅데이터를 실시간으로 융합 분석하여 단 10초 만에 숨겨진 진흙 속의 진주를 찾아냅니다.
              </p>
            </div>
          </div>
        </div>

        {/* Panel 2: Standard */}
        <div className="relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-gradient-to-bl from-[var(--surface-soft)] to-[var(--surface)] p-8 shadow-sm hover:shadow-[var(--shadow-glow)] hover:-translate-y-1 transition-all duration-500 group">
          <div className="relative z-10 h-full flex flex-col justify-between">
            <div className="flex items-center gap-3">
              <span className="flex items-center justify-center h-10 w-10 rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 22h20"/><path d="M17 2v20"/><path d="M7 22V8l10-6"/></svg>
              </span>
            </div>
            <div>
              <h3 className="text-xl font-extrabold text-[var(--text-primary)] mb-2 tracking-tight">건축 매스 스터디 자동화</h3>
              <p className="text-[var(--text-secondary)] text-sm font-medium leading-relaxed">
                법규 검토부터 최적 용적률 도출까지, AI가 대지에 맞는 최적의 3D 건축 매스를 즉각적으로 제안합니다.
              </p>
            </div>
          </div>
        </div>

        {/* Panel 3: Standard */}
        <div className="relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-gradient-to-tr from-[var(--surface-soft)] to-[var(--surface)] p-8 shadow-sm hover:shadow-[var(--shadow-glow)] hover:-translate-y-1 transition-all duration-500 group">
          <div className="relative z-10 h-full flex flex-col justify-between">
            <div className="flex items-center gap-3">
              <span className="flex items-center justify-center h-10 w-10 rounded-full bg-purple-500/10 text-purple-500 border border-purple-500/20">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/><path d="M12 14v4"/><path d="M16 10v8"/></svg>
              </span>
            </div>
            <div>
              <h3 className="text-xl font-extrabold text-[var(--text-primary)] mb-2 tracking-tight">실시간 투자 수익률(ROI)</h3>
              <p className="text-[var(--text-secondary)] text-sm font-medium leading-relaxed">
                최신 금융 금리, 공사비 단가, 주변 분양가를 연동하여 오차율을 최소화한 완벽한 사업수지표를 제공합니다.
              </p>
            </div>
          </div>
        </div>

        {/* Panel 4: Large Featured (spans 2 columns on desktop) */}
        <div className="md:col-span-2 relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-gradient-to-tl from-[var(--surface-soft)] to-[var(--surface)] p-8 shadow-sm hover:shadow-[var(--shadow-glow)] hover:border-[var(--accent)]/50 transition-all duration-500 group">
          <div className="absolute bottom-0 left-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl translate-y-1/2 -translate-x-1/4 group-hover:bg-emerald-500/20 transition-all duration-700"></div>
          <div className="relative z-10 h-full flex flex-col justify-between">
            <div className="flex items-center gap-3">
              <span className="flex items-center justify-center h-10 w-10 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><path d="M12 12 2.1 7.1"/><path d="m12 12 5-8.7"/></svg>
              </span>
              <span className="text-sm font-bold tracking-widest text-[var(--text-tertiary)] uppercase">Sustainable Future</span>
            </div>
            <div>
              <h3 className="text-2xl md:text-3xl font-extrabold text-[var(--text-primary)] mb-3 tracking-tight group-hover:text-emerald-500 transition-colors">ESG 기반 친환경 탄소중립 설계</h3>
              <p className="text-[var(--text-secondary)] font-medium leading-relaxed max-w-md">
                건축물의 전과정평가(LCA) 데이터를 기반으로 탄소 배출량을 시뮬레이션하고, 녹색건축인증 및 제로에너지 기준을 만족하는 최적의 솔루션을 제공합니다.
              </p>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
