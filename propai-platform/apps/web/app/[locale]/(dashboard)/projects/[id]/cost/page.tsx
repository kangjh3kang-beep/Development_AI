import BimCostDashboard from "@/components/cost/BimCostDashboard";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";

export default async function CostPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="grid grid-cols-1 gap-8 min-w-0">
      {/* ⓪ 커맨드센터 HUD 스트립 — 모듈 식별·LIVE(시각 전용) */}
      <ModuleCommandStrip label="COST · BIM 5D 적산" meta="QTO ENGINE" />
      <BimCostDashboard projectId={id} />
    </div>
  );
}
