import { isValidLocale } from "@/i18n/config";
import { LifecycleNavigator } from "@/components/projects/LifecycleNavigator";
import { ProjectAddressBar } from "@/components/projects/ProjectAddressBar";
import { LifecycleProgressRail } from "@/components/lifecycle/LifecycleProgressRail";
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
      <LifecycleNavigator locale={locale} projectId={id} />
      {/* 라이프사이클 진행 레일 — 활성 프로젝트 컨텍스트가 있을 때만 렌더(다음 단계 유도).
          P1: 컴팩트 파이프라인(ProjectLifecyclePipelineWrapper)은 진행바와 100% 중복이라 제거. */}
      <LifecycleProgressRail locale={locale} projectId={id} />
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
