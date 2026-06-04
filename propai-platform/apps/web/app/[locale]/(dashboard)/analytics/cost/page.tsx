"use client";

import { useParams } from "next/navigation";
import { CostEstimationClient } from "@/components/analytics/CostEstimationClient";
import { CostAnalyticsWorkspaceClient } from "@/components/analytics/CostAnalyticsWorkspaceClient";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useProjectContextStore } from "@/store/useProjectContextStore";

export default function CostPage() {
  const { locale } = useParams() as { locale: string };
  const projectId = useProjectContextStore((s) => s.projectId);
  const safeLocale: Locale = isValidLocale(locale) ? locale : "ko";

  return (
    <div className="space-y-10">
      {/* 건축개요 기반 공사비 정밀 분석(프로젝트 연동 · 수지·사업성 단일 데이터원) */}
      <CostEstimationClient />
      {/* 정밀 적산(QTO) + 몬테카를로 리스크 라이브 워크스페이스 */}
      <CostAnalyticsWorkspaceClient locale={safeLocale} projectId={projectId ?? "default"} />
    </div>
  );
}
