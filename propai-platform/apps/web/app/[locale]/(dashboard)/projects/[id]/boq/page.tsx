import BoqAutoWorkspace from "@/components/cost/BoqAutoWorkspace";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";

/**
 * 공내역서(BOQ) 자동작성 페이지 — 기존 cost 페이지 라우팅 패턴 미러(locale·params).
 * 기존 /cost 페이지는 무수정(하위호환) — 본 페이지는 additive 신규 라우트.
 */
export default async function BoqAutoPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="grid grid-cols-1 gap-8 min-w-0">
      {/* ⓪ 커맨드센터 HUD 스트립 — 모듈 식별·LIVE(시각 전용) */}
      <ModuleCommandStrip label="BOQ · 공내역 자동작성" meta="PARAMETRIC ENGINE" />
      <BoqAutoWorkspace projectId={id} />
    </div>
  );
}
