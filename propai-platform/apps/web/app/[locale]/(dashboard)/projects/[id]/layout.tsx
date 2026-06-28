import { isValidLocale } from "@/i18n/config";
import Link from "next/link";
import { ProjectAddressBar } from "@/components/projects/ProjectAddressBar";
import { LifecycleProgressRail } from "@/components/lifecycle/LifecycleProgressRail";
import { ProjectToolIndex } from "@/components/projects/ProjectToolIndex";
import { ProjectContextBinder } from "@/components/projects/ProjectContextBinder";
import { ProjectExistenceGuard } from "@/components/projects/ProjectExistenceGuard";
import React from "react";

export const dynamicParams = true;

type ProjectLayoutProps = {
  children: React.ReactNode;
  params: Promise<{
    locale: string;
    id: string;
  }>;
};

export default async function ProjectLayout({
  children,
  params,
}: ProjectLayoutProps) {
  const { locale, id } = await params;

  if (!isValidLocale(locale)) {
    return children;
  }

  return (
    <div className="flex flex-col gap-8">
      {/* 컨텍스트 단일 writer — 모든 서브라우트에서 URL projectId를 store에 바인딩(SSOT). */}
      <ProjectContextBinder projectId={id} />
      {/* 라이프사이클 진행 레일 = 단일 네비게이션(클릭 이동 + 진행률).
          탑네비(LifecycleNavigator)는 진행바와 중복·라벨불일치로 제거(사장님 결정).
          개요는 아래 링크, 보고서·수지/금융/ESG는 진행바 단계로 접근. */}
      <div className="flex items-center gap-3 px-1">
        {/* ★중앙분석센터(SiteCanvas) = 1차 진입 동선(P0① 발견성). 지도 한 화면에서 전 항목 요약 + Go/NoGo.
            기존 '개요'는 보조로 유지(additive·무손상). 페이지홉핑 대신 중앙분석센터를 디폴트 동선으로. */}
        <Link
          href={`/${locale}/projects/${id}/canvas`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--accent-strong)] bg-[var(--accent-strong)] px-3 py-1.5 text-xs font-bold text-white transition hover:opacity-90"
        >
          <svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21" /><line x1="9" y1="3" x2="9" y2="18" /><line x1="15" y1="6" x2="15" y2="21" /></svg>
          중앙분석센터
        </Link>
        <Link
          href={`/${locale}/projects/${id}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
        >
          <svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></svg>
          개요
        </Link>
      </div>
      <LifecycleProgressRail locale={locale} projectId={id} />
      {/* 진행레일(11단계)에 없는 독립 도구(CAD·회의방·공사비·BOQ·다필지·블록체인·에이전트)를
          접이식 인덱스로 surface. 레일·STAGE_GROUPS 무수정(additive). IA §5.5 동일 NavNode 개념 재사용. */}
      <ProjectToolIndex locale={locale} projectId={id} />
      <ProjectAddressBar />
      <div className="min-w-0 transition-all duration-500 animate-in fade-in slide-in-from-bottom-4">
        {/* 존재하지 않는(404) 프로젝트 직접진입 시 graceful not-found(크래시·무한스피너 방지). */}
        <ProjectExistenceGuard projectId={id} locale={locale}>
          {children}
        </ProjectExistenceGuard>
      </div>
    </div>
  );
}
