"use client";

import { useState } from "react";
import { CostEstimationClient } from "@/components/analytics/CostEstimationClient";
import { CostAlternativesPanel } from "@/components/cost/CostAlternativesPanel";
import { BoqDetailTable } from "@/components/cost/BoqDetailTable";
import { BillingDashboard } from "@/components/cost/BillingDashboard";

const TABS = [
  ["overview", "단계별 분석"],
  ["boq", "상세 내역서(BOQ)"],
  ["alternatives", "대안 설계 원가비교"],
  ["billing", "기성·실적관리(EVM)"],
] as const;
type TabKey = (typeof TABS)[number][0];

export default function CostPage() {
  const [tab, setTab] = useState<TabKey>("overview");

  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center gap-3 mb-2">
          <span className="cc-meta">COST · ESTIMATION CONSOLE</span>
          <span className="cc-live"><i />LIVE</span>
        </div>
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">공사비 분석</h1>
      </div>

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
        /* 5단계 통합 허브: 기준정보→물량·개산→적산리스트→AI분석→보고서·수지반영(타 탭 이동 콜백 주입) */
        <CostEstimationClient onNavigateTab={setTab} />
      )}

      {/* CM Phase1 — 상세 내역서(BOQ)·단가 3중(D4)·AI 해설 */}
      {tab === "boq" && <BoqDetailTable />}

      {/* CM Phase1 — 대안설계 원가비교(D1) */}
      {tab === "alternatives" && <CostAlternativesPanel />}

      {/* CM — D2 기성고 EVM + 과다청구 이상탐지 */}
      {tab === "billing" && <BillingDashboard />}
    </div>
  );
}
