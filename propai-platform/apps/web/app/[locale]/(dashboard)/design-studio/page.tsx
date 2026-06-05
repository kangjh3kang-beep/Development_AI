"use client";

/**
 * AI 자동설계(CAD) 스튜디오 — 독립 메뉴. 프로젝트 선택 후 한국 건축법 기반 설계+매싱.
 */

import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import { DesignStudio } from "@/components/design/DesignStudio";

export default function DesignStudioPage() {
  const projectId = useProjectContextStore((s) => s.projectId);
  return (
    <div className="grid gap-6 p-1">
      <ProjectSwitcher />
      {projectId ? (
        <DesignStudio projectId={projectId} />
      ) : (
        <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center text-sm text-[var(--text-secondary)]">
          위에서 프로젝트를 선택하면 AI 자동설계가 시작됩니다. (부지분석 데이터가 자동 반영됩니다)
        </div>
      )}
    </div>
  );
}
