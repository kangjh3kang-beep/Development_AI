"use client";

import React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

// 기능 카드 데이터(과장 카피 제거 → 사실·가치 중심으로 간결하게)
// large=true 이면 데스크탑에서 2칸을 차지하는 강조 카드.
// href = 클릭 시 이동할 실제 기능 페이지(로케일 접두사는 렌더에서 부여).
const PANELS = [
  {
    eyebrow: "입지 분석",
    title: "AI 입지·상권 분석",
    desc: "전국 필지의 토지대장, 도시계획 조례, 실거래가를 함께 분석해 사업성 높은 부지를 빠르게 찾습니다.",
    href: "market-insights",
    large: true,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>
    ),
  },
  {
    eyebrow: "설계",
    title: "건축 매스 스터디",
    desc: "법규 검토부터 최적 용적률까지, 대지에 맞는 3D 건축 매스를 제안합니다.",
    href: "design-studio",
    large: false,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M2 22h20"/><path d="M17 2v20"/><path d="M7 22V8l10-6"/></svg>
    ),
  },
  {
    eyebrow: "수지",
    title: "투자 수익률 분석",
    desc: "금리·공사비 단가·주변 분양가를 연동해 현실적인 사업수지표를 산출합니다.",
    href: "analytics/investment",
    large: false,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/><path d="M12 14v4"/><path d="M16 10v8"/></svg>
    ),
  },
  {
    eyebrow: "지속가능성",
    title: "ESG 기반 친환경 설계",
    desc: "전과정평가(LCA)로 탄소 배출량을 시뮬레이션하고 녹색건축·제로에너지 기준을 만족하는 안을 제안합니다.",
    href: "analytics/esg",
    large: true,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a10 10 0 1 0 10 10H12V2z"/><path d="M12 12 2.1 7.1"/><path d="m12 12 5-8.7"/></svg>
    ),
  },
];

export function MarketingPanels() {
  // 현재 로케일 추출(경로 [locale]) — 미확정 시 'ko' 폴백
  const params = useParams();
  const locale = (params?.locale as string) || "ko";

  return (
    <section className="relative z-10 w-full">
      {/* 섹션 헤더 — 과장 없는 한 줄 가치제안 */}
      <div className="db-section-head">
        <h2 className="db-section-title">기획부터 준공까지, 하나의 흐름으로</h2>
        <p className="db-section-sub">
          입지 분석, 건축 설계, 사업 수지, ESG까지 — 부동산 개발 전 과정을 데이터 위에서 검증합니다.
        </p>
      </div>

      <div className="grid auto-rows-[220px] grid-cols-1 gap-4 md:grid-cols-3">
        {PANELS.map((p) => (
          // 카드 전체를 링크로 — 클릭 시 해당 기능 페이지로 이동(키보드 포커스·hover 강조 포함)
          <Link
            key={p.title}
            href={`/${locale}/${p.href}`}
            className={`db-card group cursor-pointer transition-transform duration-150 hover:-translate-y-0.5 hover:border-[var(--accent-strong)]/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)]/50 ${p.large ? "md:col-span-2" : ""}`}
            aria-label={`${p.title} 페이지로 이동`}
          >
            <div className="flex items-center gap-3">
              <span className="db-card__icon">{p.icon}</span>
              {/* 한글 카테고리 라벨 — 양수 트래킹 제거(C3) */}
              <span className="db-eyebrow db-eyebrow--ko">{p.eyebrow}</span>
            </div>
            {/* H3: 같은 그리드 내 카드 구조·서체 균일화(제목 크기 동일, baseline 동일) */}
            <div>
              <h3 className="db-card__title mb-2 text-lg">
                {p.title}
              </h3>
              <p className={`db-card__desc ${p.large ? "max-w-md" : ""}`}>{p.desc}</p>
              {/* 클릭 가능 어포던스 — '바로가기' 화살표(hover 시 강조) */}
              <span className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-[var(--accent-strong)] opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                바로가기
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
              </span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
