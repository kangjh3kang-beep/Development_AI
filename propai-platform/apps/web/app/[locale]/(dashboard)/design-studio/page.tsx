"use client";

/**
 * AI 자동설계(CAD) 스튜디오 — 독립 메뉴. 프로젝트 선택 후 한국 건축법 기반 설계+매싱.
 */

import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import { DesignWorkspace } from "@/components/design/DesignWorkspace";
import { ProjectContextBinder } from "@/components/projects/ProjectContextBinder";

export default function DesignStudioPage() {
  const projectId = useProjectContextStore((s) => s.projectId);
  return (
    <div className="grid gap-6 p-1">
      <ProjectSwitcher />
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
        <div className="cc-panel cc-bracketed p-10 text-center">
          <i className="cc-bracket cc-bracket--tl" />
          <i className="cc-bracket cc-bracket--tr" />
          <i className="cc-bracket cc-bracket--bl" />
          <i className="cc-bracket cc-bracket--br" />
          <div className="cc-grid-bg opacity-40" />
          <span className="relative z-10 cc-label text-[var(--text-tertiary)]">NO PROJECT LOADED</span>
          <p className="relative z-10 mt-2 text-sm text-[var(--text-secondary)]">위에서 프로젝트를 선택하면 AI 자동설계가 시작됩니다. (부지분석 데이터가 자동 반영됩니다)</p>
        </div>
      )}
    </div>
  );
}
