"use client";

import { useParams } from "next/navigation";
import { InvestmentFeasibilityClient } from "@/components/analytics/InvestmentFeasibilityClient";
import { CashflowDcfPanel } from "@/components/analytics/CashflowDcfPanel";
import { InvestmentAnalyticsWorkspaceClient } from "@/components/analytics/InvestmentAnalyticsWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useProjectContextStore } from "@/store/useProjectContextStore";

export default function InvestmentPage() {
  const { locale } = useParams() as { locale: string };
  const projectId = useProjectContextStore((s) => s.projectId);
  const safeLocale: Locale = isValidLocale(locale) ? locale : "ko";

  return (
    <div className="space-y-10">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <span className="cc-meta">INVESTMENT · FEASIBILITY CONSOLE</span>
          <span className="cc-live"><i />LIVE</span>
        </div>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">투자수익성 분석</h1>
      </div>
      {/* 개발사업 수지 기반 투자수익성 분석(프로젝트 연동·자동로드·전문가 검증) */}
      <InvestmentFeasibilityClient />
      {/* 다기간 DCF 월별 현금흐름 + 엑셀 다운로드(은행제출용) */}
      <CashflowDcfPanel />
      {/* 몬테카를로 리스크 시뮬레이션(불확실성 분포·민감도) */}
      <InvestmentAnalyticsWorkspaceClient locale={safeLocale} projectId={projectId ?? "default"} />
    </div>
  );
}
