"use client";

/**
 * AI 통합 해석 카드 — SiteAnalysisInterpreter(Claude) 자연어 해석을 surface.
 * POST /zoning/analyze → ai_interpretation{overall_summary, risk_factors, opportunity_factors}.
 * SiteCanvas '통합' 탭의 LLM 해석(기존 규칙기반 rollup 보완). opt-in(버튼)+localStorage 캐시(재과금 방지).
 * jootek 미보유 PropAI 차별 — 비전문가 대행(전문가 수준 종합 판단·기회·리스크).
 */

import { useEffect, useState } from "react";
import { Sparkles, TrendingUp, AlertTriangle } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";

type AiInterp = { overall_summary?: string; risk_factors?: string; opportunity_factors?: string };
type ZoningResp = { ai_interpretation?: AiInterp };

function hash(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

export function AiInsightCard({ address }: { address?: string | null }) {
  const [ai, setAi] = useState<AiInterp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // ★다필지 통합: SSOT 통합값을 읽어 /zoning/analyze에 전달 → AI 해석이 대표번지가 아니라
  //   '통합 N필지' 기준으로 종합 판단(통합분석 근본해소).
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const parcelCount = site?.parcelCount ?? 1;
  const integratedArea = effectiveLandAreaSqm(site) ?? null;
  const isMulti = (parcelCount ?? 1) > 1 && !!integratedArea && integratedArea > 0;
  // 캐시 키에 필지수·통합면적 반영(통합/대표 결과 분리 캐시).
  const key = address ? `propai_ai_insight_${hash(address.trim())}_${isMulti ? `m${parcelCount}_${Math.round(integratedArea!)}` : "s"}` : "";

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
      const r = await apiClient.post<ZoningResp>("/zoning/analyze", {
        body: {
          address: address.trim(),
          // 다필지면 통합 컨텍스트 전달(대표번지 아닌 통합 N필지 기준 해석).
          ...(isMulti ? {
            parcel_count: parcelCount,
            integrated_area_sqm: integratedArea,
            integrated_far_pct: site?.effectiveFarPct ?? undefined,
            integrated_bcr_pct: site?.effectiveBcrPct ?? undefined,
          } : {}),
        },
        useMock: false, timeoutMs: 60000,
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

  if (!address?.trim()) return null;

  return (
    <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]">
          <Sparkles className="size-4" aria-hidden /> AI 통합 해석
          {isMulti && (
            <span className="rounded-md bg-[var(--accent-strong)]/15 px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
              통합 {parcelCount}필지 · {Math.round(integratedArea!).toLocaleString()}㎡
            </span>
          )}
        </p>
        <button onClick={run} disabled={loading}
          className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-black text-white hover:opacity-90 disabled:opacity-50">
          {loading ? "해석 중…" : ai ? "다시 해석" : "AI 해석 생성"}
        </button>
      </div>
      {error && <p className="mt-2 text-[11px] text-[var(--danger,#dc2626)]">{error}</p>}
      {ai && (
        <div className="mt-2.5 space-y-2.5">
          {ai.overall_summary && (
            <div>
              <p className="text-[11px] font-bold text-[var(--text-secondary)]">종합 평가</p>
              <p className="mt-0.5 text-xs leading-relaxed text-[var(--text-primary)] whitespace-pre-line">{ai.overall_summary}</p>
            </div>
          )}
          {ai.opportunity_factors && (
            <div>
              <p className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-500"><TrendingUp className="size-3" aria-hidden /> 개발 기회</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--text-secondary)] whitespace-pre-line">{ai.opportunity_factors}</p>
            </div>
          )}
          {ai.risk_factors && (
            <div>
              <p className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-500"><AlertTriangle className="size-3" aria-hidden /> 리스크</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--text-secondary)] whitespace-pre-line">{ai.risk_factors}</p>
            </div>
          )}
          <p className="text-[10px] text-[var(--text-hint)]">Claude 기반 종합 해석 · 근거는 각 탭의 산출값 참조.</p>
        </div>
      )}
      {!ai && !error && (
        <p className="mt-2 text-[11px] text-[var(--text-hint)]">버튼을 눌러 이 부지의 종합 평가·기회·리스크를 AI로 해석합니다.</p>
      )}
    </div>
  );
}
