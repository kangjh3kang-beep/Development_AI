"use client";

/**
 * AI 자동설계(CAD) 스튜디오 — 독립 메뉴. 프로젝트 선택 후 한국 건축법 기반 설계+매싱.
 */

import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import { DesignStudio } from "@/components/design/DesignStudio";
import { CadBimIntegrationPanel } from "@/components/design/CadBimIntegrationPanel";

export default function DesignStudioPage() {
  const projectId = useProjectContextStore((s) => s.projectId);
  return (
    <div className="grid gap-6 p-1">
      <ProjectSwitcher />
      {projectId ? (
        <>
          {/* 1) AI 자동설계(매싱·법규) */}
          <DesignStudio projectId={projectId} />
          {/* 2) 실 CAD/BIM 설계·작성·편집 스튜디오(2D 도면·3D 조감·생성·수정·저장) */}
          <CadBimIntegrationPanel projectId={projectId} dictionary={{}} />
        </>
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
