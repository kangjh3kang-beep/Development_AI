"use client";

/**
 * AI 자동설계(CAD) 스튜디오 — 독립 메뉴. 프로젝트 선택 후 한국 건축법 기반 설계+매싱.
 */

import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import {
  DesignCenterEmptyState,
  DesignCenterPageFrame,
} from "@/components/design-center/DesignCenterPageFrame";
import { DesignWorkspace } from "@/components/design/DesignWorkspace";
import { ProjectContextBinder } from "@/components/projects/ProjectContextBinder";
import { defaultLocale, isValidLocale } from "@/i18n/config";
import { useParams } from "next/navigation";

export default function DesignStudioPage() {
  const projectId = useProjectContextStore((s) => s.projectId);
  const params = useParams() as { locale?: string };
  const locale = isValidLocale(params.locale || "") ? params.locale! : defaultLocale;

  return (
    <DesignCenterPageFrame
      locale={locale}
      activeId="design-studio"
      title="AI 설계도면(CAD)"
      description="부지 조건과 법규 검토를 기준으로 설계안 생성, CAD 도면, BIM 편집실을 한 흐름으로 연결합니다."
      status="live"
      statusLabel={projectId ? "프로젝트 연결" : "프로젝트 선택 필요"}
      actions={<ProjectSwitcher />}
      metrics={[
        { label: "워크플로우", value: "3단계", description: "부지 · 생성 · CAD/BIM" },
        { label: "주요 산출", value: "설계안 Top-N", description: "도면·매스·근거" },
        { label: "연동", value: projectId ? "활성" : "대기", description: "프로젝트 컨텍스트" },
      ]}
    >
      {/* 2차-B: design-studio 직접 진입 시에도 designData/siteAnalysis를 백엔드 스냅샷에서 복원한다.
          이 라우트는 projects/[id] 트리 밖이라 layout의 ProjectContextBinder가 마운트되지 않아,
          store에 projectId만 있고 designData가 null이면 CAD/BIM 패널이 "먼저 설계 생성" 게이트에
          부당하게 막혔다. projectId가 있으면 동일 바인더를 마운트해 분석 컨텍스트를 복원한다
          (같은 projectId 재바인딩은 리셋하지 않으므로 무회귀). */}
      {projectId && <ProjectContextBinder projectId={projectId} />}
      {projectId ? (
        // 단계별 워크스페이스 셸 — 부지·법규 → 설계생성·도면 → CAD·BIM 순차 진행.
        //  한 페이지 세로 나열(정보 과부하)을 단계 분리로 해소하고, 무거운 CAD/BIM은 lazy 마운트.
        <DesignWorkspace projectId={projectId} />
      ) : (
        <DesignCenterEmptyState
          title="프로젝트를 선택하면 AI 자동설계가 시작됩니다."
          description="상단 프로젝트 선택기에서 대상 프로젝트를 고르면 부지분석 스냅샷이 복원되고 설계 생성·도면·BIM 편집 흐름이 열립니다."
          actionHref={`/${locale}/projects`}
        />
      )}
    </DesignCenterPageFrame>
  );
}
