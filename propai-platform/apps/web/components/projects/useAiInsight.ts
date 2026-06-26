"use client";

/**
 * useAiInsight — 부지 AI 통합 해석(SiteAnalysisInterpreter/Claude) 공용 훅(SSOT).
 *
 * ★데이터원 = POST /analysis/comprehensive(종합 부지분석 마스터 7섹션) → ai_interpretation
 * {overall_summary, risk_factors, opportunity_factors}. 기존 /zoning/analyze(용도지역 단일)보다 풍부한
 * 통합 해석(실효용적률·시장·입지·개발방식·근거)을 1콜로 surface(P0③ 단일창 데이터원 격상).
 * opt-in(run)+localStorage 캐시(재과금 방지). 다필지면 SSOT 필지목록을 전송해 통합면적 기준 종합 해석.
 * AiInsightCard(통합 탭 풀카드)와 AiInsightStrip(각 탭 경량 스트립)이 동일 캐시키로 단일경유 —
 * 한 곳에서 생성하면 다른 표면이 같은 캐시를 읽는다(중복 호출·과금 0).
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";

export type AiInterp = { overall_summary?: string; risk_factors?: string; opportunity_factors?: string };
// /analysis/comprehensive 응답(AnalysisResult)에서 본 훅은 ai_interpretation만 소비(부분 타입).
type ComprehensiveResp = { ai_interpretation?: AiInterp };

function hash(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export type UseAiInsight = {
  ai: AiInterp | null;
  loading: boolean;
  error: string;
  run: () => Promise<void>;
  isMulti: boolean;
  parcelCount: number;
  integratedArea: number | null;
};

export function useAiInsight(address?: string | null): UseAiInsight {
  const [ai, setAi] = useState<AiInterp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // ★다필지 통합: SSOT 필지목록을 comprehensive에 전달 → AI 해석이 대표번지가 아니라
  //   '통합 N필지' 면적가중 기준으로 종합 판단(통합분석 근본해소).
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const parcelCount = site?.parcelCount ?? 1;
  const integratedArea = effectiveLandAreaSqm(site) ?? null;
  const isMulti = (parcelCount ?? 1) > 1 && !!integratedArea && integratedArea > 0;
  // 캐시 키에 필지수·통합면적 반영(통합/대표 결과 분리 캐시).
  const key = address
    ? `propai_ai_insight_${hash(address.trim())}_${isMulti ? `m${parcelCount}_${Math.round(integratedArea!)}` : "s"}`
    : "";

  // 캐시 복원(재과금 방지).
  useEffect(() => {
    if (!key || typeof window === "undefined") { setAi(null); return; }
    try { const raw = window.localStorage.getItem(key); if (raw) setAi(JSON.parse(raw)); else setAi(null); }
    catch { setAi(null); }
  }, [key]);

  async function run() {
    if (!address?.trim() || loading) return;
    setLoading(true); setError("");
    try {
      const r = await apiClient.post<ComprehensiveResp>("/analysis/comprehensive", {
        body: {
          address: address.trim(),
          // 다필지(2필지↑)면 SSOT 필지목록 전송 → comprehensive가 면적가중 통합집계로 종합 해석
          //   (대표번지 단일 산출 아님). 백엔드 _integrated_context가 camelCase(address/areaSqm/pnu) 수용.
          ...(isMulti && (site?.parcels?.length ?? 0) > 1 ? { parcels: site!.parcels } : {}),
        },
        useMock: false, timeoutMs: 90000,   // 7섹션+LLM 집계 — /zoning/analyze보다 무거워 타임아웃 상향
      });
      const interp = r?.ai_interpretation ?? null;
      if (interp && (interp.overall_summary || interp.risk_factors || interp.opportunity_factors)) {
        setAi(interp);
        try { if (key) window.localStorage.setItem(key, JSON.stringify(interp)); } catch { /* quota */ }
      } else {
        setError("AI 해석을 생성하지 못했습니다(LLM 미응답).");
      }
    } catch {
      setError("AI 해석 생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return { ai, loading, error, run, isMulti, parcelCount, integratedArea };
}
