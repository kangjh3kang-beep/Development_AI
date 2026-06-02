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

function hashStr(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

type Issue = { type: string; claim: string; severity: "high" | "medium" | "low" | string; note: string };
type VerifyResult = {
  generated?: boolean;
  verdict: "pass" | "warn" | "fail" | string;
  grounded_score?: number | null;
  issues: Issue[];
  summary: string;
};

const VERDICT_META: Record<string, { label: string; cls: string; icon: string }> = {
  pass: { label: "검증 통과", cls: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400", icon: "✅" },
  warn: { label: "주의", cls: "border-amber-500/30 bg-amber-500/10 text-amber-400", icon: "⚠️" },
  fail: { label: "오류 발견", cls: "border-rose-500/30 bg-rose-500/10 text-rose-400", icon: "❌" },
};
const SEV_CLS: Record<string, string> = {
  high: "text-rose-400", medium: "text-amber-400", low: "text-[var(--text-tertiary)]",
};

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

  const run = useCallback(async () => {
    if (!context) return;
    setLoading(true);
    try {
      const r = await apiClient.post<VerifyResult>("/verify/analysis", {
        body: { analysis_type: analysisType, source: context, output: context },
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
            </span>
          )}
        </div>
        {result && (result.issues.length > 0 || result.summary) && (
          <button onClick={() => setOpen((v) => !v)} className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline">
            {open ? "접기" : "상세"}
          </button>
        )}
      </div>

      {open && result && (
        <div className="mt-2 space-y-1.5 border-t border-[var(--line)] pt-2">
          {result.summary && <p className="text-[11px] text-[var(--text-secondary)]">{result.summary}</p>}
          {result.issues.map((it, i) => (
            <div key={i} className="text-[11px]">
              <span className={`font-bold ${SEV_CLS[it.severity] || ""}`}>[{it.type}]</span>{" "}
              <span className="text-[var(--text-primary)]">{it.claim}</span>
              <span className="text-[var(--text-tertiary)]"> — {it.note}</span>
            </div>
          ))}
          {!result.generated && <p className="text-[10px] text-[var(--text-hint)]">규칙기반 사전검사만 적용됨</p>}
        </div>
      )}
    </div>
  );
}
