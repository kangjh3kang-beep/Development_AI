"use client";

/**
 * AiInsightStrip — SiteCanvas 각 탭 상단의 경량 AI 인사이트(한줄 종합 + 기회/리스크 칩).
 *
 * '통합' 탭의 풀카드(AiInsightCard)와 동일 캐시(useAiInsight 단일경유)를 읽어, 어느 탭에 있어도
 * AI 종합 해석 한줄이 보이게 한다("LLM 미적용 — 각 탭 AI 인사이트 0" 갭 해소). 미생성 시 경량
 * 생성 버튼만 노출(추가 과금 없음·캐시 재사용). 상세는 통합 탭 전체 해석으로 유도.
 */

import { Sparkles, TrendingUp, AlertTriangle } from "lucide-react";
import { useAiInsight } from "@/components/projects/useAiInsight";

export function AiInsightStrip({ address }: { address?: string | null }) {
  const { ai, loading, error, run } = useAiInsight(address);

  if (!address?.trim()) return null;

  return (
    <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 px-3 py-2">
      {ai?.overall_summary ? (
        <div className="flex items-start gap-2" aria-live="polite">
          <Sparkles className="mt-0.5 size-3.5 shrink-0 text-[var(--accent-strong)]" aria-hidden />
          <div className="min-w-0">
            <p className="line-clamp-2 text-[11px] leading-relaxed text-[var(--text-primary)]">{ai.overall_summary}</p>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px]">
              {ai.opportunity_factors && (
                <span className="inline-flex items-center gap-0.5 font-bold text-emerald-500"><TrendingUp className="size-2.5" aria-hidden /> 기회</span>
              )}
              {ai.risk_factors && (
                <span className="inline-flex items-center gap-0.5 font-bold text-amber-500"><AlertTriangle className="size-2.5" aria-hidden /> 리스크</span>
              )}
              <span className="text-[var(--text-hint)]">통합 탭에서 전체 해석</span>
            </div>
          </div>
        </div>
      ) : (
        <button onClick={run} disabled={loading}
          className="inline-flex items-center gap-1.5 text-[11px] font-bold text-[var(--accent-strong)] transition hover:opacity-80 disabled:opacity-50">
          <Sparkles className="size-3.5" aria-hidden /> {loading ? "AI 해석 중…" : error ? "다시 시도" : "AI 통합 해석 생성"}
        </button>
      )}
      {error && <p className="mt-1 text-[10px] text-[var(--status-error)]">{error}</p>}
    </div>
  );
}
