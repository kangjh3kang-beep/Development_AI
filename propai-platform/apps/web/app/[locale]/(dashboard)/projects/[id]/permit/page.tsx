"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { ProjectPermitWorkspaceClient } from "@/components/projects/ProjectPermitWorkspaceClient";
import { DesignChangePredictPanel } from "@/components/design-risk/DesignChangePredictPanel";
import { EnvironmentSummaryCard } from "@/components/environment/EnvironmentSummaryCard";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { isValidLocale, type Locale } from "@/i18n/config";

export default function PermitPage() {
  const params = useParams();
  const locale = params.locale as string;
  const id = params.id as string;

  const [data, setData] = useState<{ stages: any[], documents: any[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  useEffect(() => {
    async function fetchStatus() {
      try {
        const res = await apiClient.get<any>(`/projects/${id}/permit/status`);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch permit status", err);
      } finally {
        setLoading(false);
      }
    }
    fetchStatus();
  }, [id]);

  const safeLocale = (isValidLocale(locale) ? locale : "ko") as Locale;

  if (loading) return <div className="p-12 text-center animate-pulse font-bold text-[var(--text-tertiary)] uppercase tracking-widest">분석 중...</div>;

  const permitStages = data?.stages || [];
  const documents = data?.documents || [];

  return (
    <div className="grid gap-8 p-6 lg:p-12">
      <div className="flex flex-col gap-2">
        <h2 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">인허가 관리 포털</h2>
        <p className="text-[var(--text-secondary)]">프로젝트 인허가 진행 현황 및 서류 제출 상태를 실시간으로 모니터링합니다.</p>
      </div>

      <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-10 shadow-xl">
        <h3 className="mb-10 text-xl font-bold text-[var(--text-primary)]">인허가 진행 프로세스</h3>
        <div className="flex flex-wrap items-center justify-between gap-6">
          {permitStages.map((stage, i, arr) => (
            <div key={stage.label} className="flex flex-1 items-center gap-4 min-w-[120px]">
              <div className="flex flex-col items-center gap-3 flex-1 text-center">
                <div className={`flex h-12 w-12 items-center justify-center rounded-full border-2 text-sm font-black transition-all ${
                  stage.status === "completed"
                    ? "bg-[var(--accent-strong)] border-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                    : stage.status === "current"
                    ? "border-[var(--accent-strong)] text-[var(--accent-strong)] bg-[var(--accent-soft)] animate-pulse shadow-md"
                    : "border-[var(--line-strong)] text-[var(--text-hint)]"
                }`}>
                  {stage.status === "completed" ? "\u2713" : i + 1}
                </div>
                <span className={`text-sm font-bold ${stage.status === "current" ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]"}`}>
                  {stage.label}
                </span>
              </div>
              {i < arr.length - 1 && (
                <div className={`mb-8 h-0.5 flex-1 ${stage.status === "completed" ? "bg-[var(--accent-strong)]" : "bg-[var(--line)]"}`} />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-8 shadow-lg">
          <h3 className="mb-6 text-xl font-bold text-[var(--text-primary)]">필수 서류 체크리스트</h3>
          <div className="grid gap-4">
            {documents.map((doc) => (
              <div key={doc.label} className="flex items-center justify-between rounded-2xl bg-[var(--surface-soft)] px-6 py-4 transition-all hover:bg-[var(--surface)] hover:shadow-sm">
                <div className="flex items-center gap-4">
                  <span className={`flex h-6 w-6 items-center justify-center rounded-lg border text-xs font-bold transition-all ${
                    doc.submitted
                      ? "border-[var(--success)] bg-[var(--success-soft)] text-[var(--success)]"
                      : "border-[var(--line-strong)] text-transparent"
                  }`}>
                    {doc.submitted ? "\u2713" : ""}
                  </span>
                  <span className={`text-sm font-semibold ${doc.submitted ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                    {doc.label}
                  </span>
                </div>
                <span className={`text-[10px] font-bold uppercase tracking-widest ${doc.submitted ? "text-[var(--success)]" : "text-[var(--text-tertiary)]"}`}>
                  {doc.submitted ? "제출 완료" : "미제출"}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-6 rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-8">
           <div className="flex items-center gap-3">
              <h3 className="text-xl font-bold text-[var(--text-primary)]">AI 규제 검토 알림</h3>
           </div>
           <div className="space-y-4">
              <div className="rounded-2xl border-l-4 border-amber-500 bg-white p-5 shadow-sm">
                 <p className="text-xs font-bold text-amber-600 uppercase tracking-widest mb-1">Warning: 보완 필요</p>
                 <p className="text-sm font-medium">환경영향평가서 내용 중 소음 진동 기준치가 최신 조례와 상이합니다. 보완이 필요합니다.</p>
              </div>
              <div className="rounded-2xl border-l-4 border-emerald-500 bg-white p-5 shadow-sm">
                 <p className="text-xs font-bold text-emerald-600 uppercase tracking-widest mb-1">Optimized: 권장사항</p>
                 <p className="text-sm font-medium">교통영향평가 시 인근 성수역 출구 증설 계획을 반영하면 인허가 승인 확률이 15% 상승합니다.</p>
              </div>
           </div>
           <button className="mt-auto rounded-2xl bg-[var(--accent-strong)] py-4 font-bold text-white shadow-lg transition-transform hover:scale-[1.02] active:scale-[0.98]">
              전체 규제 리포트 다운로드 (PDF)
           </button>
        </div>
      </div>

      {/* ── 일조 환경 보조카드(정북 일조사선·동지 일조시간 = 법정 요건) ── */}
      {(siteAnalysis?.address || siteAnalysis?.pnu) && (
        <EnvironmentSummaryCard
          address={siteAnalysis?.address}
          pnu={siteAnalysis?.pnu}
          focus="solar"
        />
      )}

      {/* ── 설계변경 사전예측 (D3) ── */}
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-black tracking-tight text-[var(--text-primary)]">설계변경 리스크 사전예측</h2>
        <p className="text-[var(--text-secondary)]">착공 전 법규초과·필수요소 누락·정합 모순을 미리 잡아내고 저비용 보완방안을 제시합니다.</p>
      </div>
      <DesignChangePredictPanel projectId={id} />

      {/* ── Live Workspace Client ── */}
      <ProjectPermitWorkspaceClient locale={safeLocale} projectId={id} />
    </div>
  );
}
