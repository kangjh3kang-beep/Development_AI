"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { CostEstimationClient } from "@/components/analytics/CostEstimationClient";
import { CostAnalyticsWorkspaceClient } from "@/components/analytics/CostAnalyticsWorkspaceClient";
import { CostAlternativesPanel } from "@/components/cost/CostAlternativesPanel";
import { BoqDetailTable } from "@/components/cost/BoqDetailTable";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const TABS = [
  ["overview", "개요 기반 분석"],
  ["boq", "상세 내역서(BOQ)·단가"],
  ["alternatives", "대안설계 원가비교"],
] as const;
type TabKey = (typeof TABS)[number][0];

export default function CostPage() {
  const { locale } = useParams() as { locale: string };
  const projectId = useProjectContextStore((s) => s.projectId);
  const safeLocale: Locale = isValidLocale(locale) ? locale : "ko";
  const [tab, setTab] = useState<TabKey>("overview");

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap gap-2 border-b border-[var(--line)] pb-1">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`rounded-t-lg px-4 py-2 text-sm font-bold transition-colors ${
              tab === key
                ? "border-b-2 border-[var(--accent-strong)] text-[var(--accent-strong)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="space-y-10">
          {/* 건축개요 기반 공사비 정밀 분석(프로젝트 연동 · 수지·사업성 단일 데이터원) */}
          <CostEstimationClient />
          {/* 정밀 적산(QTO) + 몬테카를로 리스크 라이브 워크스페이스 */}
          <CostAnalyticsWorkspaceClient locale={safeLocale} projectId={projectId ?? "default"} />
        </div>
      )}

      {/* CM Phase1 — 상세 내역서(BOQ)·단가 3중(D4)·AI 해설 */}
      {tab === "boq" && <BoqDetailTable />}

      {/* CM Phase1 — 대안설계 원가비교(D1) */}
      {tab === "alternatives" && <CostAlternativesPanel />}
    </div>
  );
}
