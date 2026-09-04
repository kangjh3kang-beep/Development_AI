import Link from "next/link";
import { Info } from "lucide-react";
import BimCostDashboard from "@/components/cost/BimCostDashboard";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";

export default async function CostPage({
  params,
}: {
  params: Promise<{ id: string; locale: string }>;
}) {
  const { id, locale } = await params;
  return (
    <div className="grid grid-cols-1 gap-8 min-w-0">
      {/* ⓪ 커맨드센터 HUD 스트립 — 모듈 식별·LIVE(시각 전용) */}
      <ModuleCommandStrip label="COST · BIM 5D 적산" meta="QTO ENGINE" />
      {/* T2: 안내 배너 — 통합 공사비 콘솔(/analytics/cost: 단계별 산정·BOQ·대안비교·기성)로 안내.
          기존 소비자 무파괴를 위해 리다이렉트 강제 대신 링크 안내만 한다(이 페이지는 그대로 동작). */}
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-4 text-sm text-[var(--text-secondary)]">
        <Info className="size-4 shrink-0 text-[var(--accent-strong)]" aria-hidden />
        <span>
          공사비 개략 산정·상세 내역서(BOQ)·대안설계 비교·기성관리를 한 곳에서 다루는{" "}
          <b className="text-[var(--text-primary)]">적산·공사비 관리</b> 콘솔이 별도로 있습니다.
        </span>
        <Link
          href={`/${locale}/analytics/cost`}
          className="ml-auto shrink-0 rounded-lg border border-[var(--accent-strong)]/50 px-4 py-2 text-xs font-black text-[var(--accent-strong)] hover:opacity-90"
        >
          적산·공사비 관리로 이동 →
        </Link>
      </div>
      <BimCostDashboard projectId={id} />
    </div>
  );
}
