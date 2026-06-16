"use client";

/**
 * 분석 검증 배지 — 오류·할루시네이션 가드 (전수 배치).
 *
 * 모든 분석 결과에 자동 배치되어, 분석 출력이 원본 데이터에 근거하는지 검증한다.
 * ✅통과/⚠️주의/❌오류 + 플래그(할루시네이션·수치불일치·내부모순·과장)를 표시.
 * 결과당 1회만 호출(localStorage 캐싱)하여 비용을 통제한다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { FeedbackWidget } from "@/components/growth/FeedbackWidget";

function hashStr(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

type Issue = { type: string; claim: string; severity: "high" | "medium" | "low" | string; note: string };
type CalcCheck = { name: string; formula: string; claimed: number; recomputed: number; diff_pct: number; ok: boolean };
type VerifyResult = {
  generated?: boolean;
  verdict: "pass" | "warn" | "fail" | string;
  grounded_score?: number | null;
  issues: Issue[];
  summary: string;
  calc_checks?: CalcCheck[];
  calc_pass_rate?: number | null;
};

const VERDICT_META: Record<string, { label: string; cls: string; icon: string }> = {
  pass: { label: "검증 통과", cls: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400", icon: "✅" },
  warn: { label: "주의", cls: "border-amber-500/30 bg-amber-500/10 text-amber-400", icon: "⚠️" },
  fail: { label: "오류 발견", cls: "border-rose-500/30 bg-rose-500/10 text-rose-400", icon: "❌" },
};
const SEV_CLS: Record<string, string> = {
  high: "text-rose-400", medium: "text-amber-400", low: "text-[var(--text-tertiary)]",
};

// 검증 플래그 유형 → 일반인이 이해하기 쉬운 한국어 라벨(과거 "할루시네이션" 캐시도 친화 표기)
const TYPE_LABEL: Record<string, string> = {
  "할루시네이션": "데이터 오류 감지",
  "데이터오류감지": "데이터 오류 감지",
  "데이터 오류 감지": "데이터 오류 감지",
  "수치불일치": "수치 불일치",
  "내부모순": "내부 모순",
  "과장": "과장·단정",
};
const typeLabel = (t: string) => TYPE_LABEL[t?.trim?.() ?? t] || t;

export function VerificationBadge({
  analysisType,
  context,
  autoRun = true,
}: {
  analysisType: string;
  context: Record<string, unknown> | null;
  autoRun?: boolean;
}) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [open, setOpen] = useState(false);

  const cacheKey = useMemo(() => {
    try { return `propai_verify_${analysisType}_${hashStr(JSON.stringify(context || {}))}`; }
    catch { return ""; }
  }, [analysisType, context]);

  // 피드백 위젯 조인키 — context 해시(analysis_ledger.content_hash 와 동일 산식은 아니나 분석본 식별에 충분).
  const contentHash = useMemo(() => {
    try { return context ? hashStr(JSON.stringify(context)) : undefined; }
    catch { return undefined; }
  }, [context]);

  const run = useCallback(async () => {
    if (!context) return;
    setLoading(true);
    try {
      // ★source(원천 데이터)와 output(LLM 산출 주장)을 분리해야 교차검증이 성립한다.
      //   과거 source=output=context(동일 객체)라 LLM이 자기 자신과 비교 → 변별력 0이었다.
      //   컨텍스트에서 LLM 산출 키(narrative·*_interpretation 등)를 output으로, 나머지를
      //   원천 source로 가른다. 분리할 LLM 키가 없으면 기존 동작(전체=source=output)으로 폴백.
      const LLM_OUTPUT_KEYS = new Set([
        "narrative", "ai_interpretation", "interpretation", "analysis", "summary",
        "expert_panel", "target_persona", "opportunities", "risks", "price_trend",
        "market_interpretation",
      ]);
      const src: Record<string, unknown> = {};
      const out: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(context)) {
        if (LLM_OUTPUT_KEYS.has(k) || k.endsWith("_interpretation")) out[k] = v;
        else src[k] = v;
      }
      const hasSplit = Object.keys(out).length > 0 && Object.keys(src).length > 0;
      const r = await apiClient.post<VerifyResult>("/verify/analysis", {
        body: {
          analysis_type: analysisType,
          source: hasSplit ? src : context,
          output: hasSplit ? out : context,
        },
        useMock: false, timeoutMs: 80000,
      });
      setResult(r);
      try { if (cacheKey) window.localStorage.setItem(cacheKey, JSON.stringify(r)); } catch { /* quota */ }
    } catch {
      /* 검증 실패는 조용히 무시(분석 자체는 유효) */
    } finally {
      setLoading(false);
    }
  }, [analysisType, context, cacheKey]);

  // 자동 실행(캐시 우선)
  useEffect(() => {
    if (!context || !cacheKey) return;
    try {
      const raw = window.localStorage.getItem(cacheKey);
      if (raw) { setResult(JSON.parse(raw)); return; }
    } catch { /* noop */ }
    setResult(null);
    if (autoRun) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey]);

  if (!context) return null;

  const meta = result ? (VERDICT_META[result.verdict] || VERDICT_META.warn) : null;

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold text-[var(--text-secondary)]">🛡 AI 검증</span>
          {loading && <span className="text-[11px] text-[var(--text-hint)]">검증 중…</span>}
          {meta && (
            <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold ${meta.cls}`}>
              {meta.icon} {meta.label}
              {(result?.issues?.length ?? 0) > 0 && ` · ${result!.issues.length}건`}
              {result?.grounded_score != null && ` · 근거 ${result.grounded_score}%`}
              {(result?.calc_checks?.length ?? 0) > 0 &&
                ` · 계산 ${result!.calc_checks!.filter((c) => c.ok).length}/${result!.calc_checks!.length}`}
            </span>
          )}
        </div>
        {result && ((result.issues?.length ?? 0) > 0 || result.summary || (result.calc_checks?.length ?? 0) > 0) && (
          <button onClick={() => setOpen((v) => !v)} className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline">
            {open ? "접기" : "상세"}
          </button>
        )}
      </div>

      {open && result && (
        <div className="mt-2 space-y-1.5 border-t border-[var(--line)] pt-2">
          {result.summary && <p className="text-[11px] text-[var(--text-secondary)]">{result.summary}</p>}
          {(result.issues ?? []).map((it, i) => (
            <div key={i} className="text-[11px]">
              <span className={`font-bold ${SEV_CLS[it.severity] || ""}`}>[{typeLabel(it.type)}]</span>{" "}
              <span className="text-[var(--text-primary)]">{it.claim}</span>
              <span className="text-[var(--text-tertiary)]"> — {it.note}</span>
            </div>
          ))}
          {(result.calc_checks?.length ?? 0) > 0 && (
            <div className="mt-1.5 border-t border-[var(--line)] pt-1.5">
              <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-hint)]">결정론 계산검증</p>
              {result.calc_checks!.map((c, i) => (
                <div key={i} className="flex items-center justify-between text-[11px]">
                  <span className="text-[var(--text-secondary)]">
                    {c.ok ? "✅" : "❌"} {c.name} <span className="text-[var(--text-tertiary)]">({c.formula})</span>
                  </span>
                  {!c.ok && (
                    <span className="text-red-500">출력 {c.claimed.toLocaleString()} ≠ 계산 {c.recomputed.toLocaleString()}</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {!result.generated && <p className="text-[10px] text-[var(--text-hint)]">규칙기반 사전검사 + 결정론 재계산 적용됨</p>}
        </div>
      )}

      {/* 자가성장 피드백 위젯 — 분석 출력에 대한 👍/👎·교정 수집(익명 허용·실패 무시) */}
      <div className="mt-2 border-t border-[var(--line)] pt-2">
        <FeedbackWidget
          targetType="analysis"
          analysisType={analysisType}
          contentHash={contentHash}
        />
      </div>
    </div>
  );
}
