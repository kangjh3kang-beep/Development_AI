"use client";

/**
 * 부동산 규제 연동 — 규제 계층 대시보드.
 *
 * 부지에 적용되는 상위법령 → 도시·군계획/지구단위 → 지자체 조례 → 개별 적용규제를
 * 계층으로 시각화하고, 정량 한도(건폐/용적/높이/주차) 법정·조례·실효 비교와
 * AI 통합 해석, 필지 구획도를 함께 제공한다. (POST /regulation/analyze)
 */

import { useCallback, useState } from "react";
import { Card, CardContent, Input } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { ParcelBoundaryMap } from "@/components/map/ParcelBoundaryMap";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { AnalysisVerdict } from "@/components/analysis/AnalysisVerdict";
import { RegulationHierarchyView, type RegResult } from "@/components/regulation/RegulationHierarchyView";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { Locale } from "@/i18n/config";

export function RegulationsWorkspaceClient({ locale }: { locale: Locale }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const [addr, setAddr] = useState("");
  const [pnu, setPnu] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [llmGated, setLlmGated] = useState(false);
  const [result, setResult] = useState<RegResult | null>(null);

  const run = useCallback(async () => {
    const target = addr || siteAnalysis?.address || "";
    if (!target) { setError("주소를 먼저 선택하거나 입력하세요."); return; }
    const targetPnu = pnu.trim() || siteAnalysis?.pnu || undefined;
    setLoading(true); setError(""); setLlmGated(false); setResult(null);
    try {
      let r: RegResult;
      try {
        r = await apiClient.post<RegResult>("/regulation/analyze", {
          body: { address: target, pnu: targetPnu, use_llm: useLlm },
          useMock: false, timeoutMs: 120000,
        });
      } catch (llmError) {
        // LLM 게이트(402): AI 통합 해석은 잔액/구독 필요. 계층·정량·영향도는 use_llm:false로 표시.
        if (useLlm && llmError instanceof ApiClientError && llmError.status === 402) {
          setLlmGated(true);
          r = await apiClient.post<RegResult>("/regulation/analyze", {
            body: { address: target, pnu: targetPnu, use_llm: false },
            useMock: false, timeoutMs: 120000,
          });
        } else {
          throw llmError;
        }
      }
      setResult(r);
    } catch {
      setError("규제 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [addr, pnu, useLlm, siteAnalysis]);

  return (
    <div className="grid gap-6">
      {/* Hero + 입력 */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🏛️</span>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">부동산 규제 연동</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                해당 토지에 적용되는 상위법령·도시·군계획·지자체 조례·개별 규제를 계층으로 정리하고,
                건폐율·용적률·높이·주차 한도와 AI 통합 해석을 제공합니다.
              </p>
            </div>
          </div>

          <div className="mt-5">
            <ProjectAddressInput
              value={addr}
              onChange={setAddr}
              label="분석 대상지 주소"
              placeholder="프로젝트를 선택하거나 주소를 검색/입력하세요"
              pickerLabel="분석 히스토리"
              disabled={loading}
            />
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <Input value={pnu} onChange={(e) => setPnu(e.target.value)} placeholder="PNU 코드 (선택)" disabled={loading} />
            <label className="flex items-center gap-2 text-xs font-semibold text-[var(--text-secondary)]">
              <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)}
                className="h-4 w-4 accent-[var(--accent-strong)]" disabled={loading} />
              🤖 AI 통합 해석 포함
            </label>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button onClick={run} disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
              {loading ? "규제 분석 중…" : "🔎 규제 분석"}
            </button>
            {error && <span className="text-xs font-semibold text-rose-500">{error}</span>}
            {llmGated && (
              <span className="text-xs font-semibold text-amber-500">
                AI 통합 해석은 잔액/구독 필요 — 계층·정량 한도·영향도는 표시됩니다.
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {result && (
        <>
          {/* 검증 배지 + AI 규제 해석 요약 통합 카드(상세 해석 카드는 아래 유지). */}
          <AnalysisVerdict
            analysisType="regulation"
            context={result as unknown as Record<string, unknown>}
            interpretation={result.ai?.summary}
            interpretationTitle="AI 규제 해석"
          />

          {/* 종합 규제 계층·정량 한도·영향도·LLM 통합 해석 (공용 렌더) */}
          <RegulationHierarchyView result={result} locale={locale} />

          {/* 필지 구획도 */}
          <ParcelBoundaryMap parcels={[result.address]} />

          {/* 전문가 패널 검증 */}
          <ExpertPanelCard
            analysisType="regulation"
            address={result.address}
            context={result as unknown as Record<string, unknown>}
          />
        </>
      )}
    </div>
  );
}
