import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";
import { OrchestrateWorkspaceClient } from "@/components/orchestration/OrchestrateWorkspaceClient";

/**
 * 「통합 분석」 서브라우트(B6-2) — 9노드 오케스트레이터 진입.
 *
 * 서버 페이지 → 클라이언트 컴포넌트 분리(feasibility/cost 서브라우트와 동일 패턴).
 * projectId 컨텍스트는 프로젝트 layout의 ProjectContextBinder가 단일 writer로 바인딩하므로
 * 여기서는 projectId만 클라이언트에 전달한다(신규 컨텍스트 패턴 발명 금지·계정격리 보존).
 */
export default async function OrchestratePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="grid grid-cols-1 gap-8 min-w-0">
      {/* ⓪ 커맨드센터 HUD 스트립 — 모듈 식별·LIVE(시각 전용) */}
      <ModuleCommandStrip label="ORCHESTRATE · 통합 분석" meta="9-NODE" />
      <OrchestrateWorkspaceClient projectId={id} />
    </div>
  );
}
