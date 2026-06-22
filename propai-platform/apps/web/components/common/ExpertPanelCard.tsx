"use client";

/**
 * 전문가 패널 검증 카드 — 모든 분석 작업 공간 공통.
 *
 * 분석 결과(context)를 분석유형별 전문가 패널에 보내 다관점 분석·토론·통합·검증을 받는다.
 * 토글(opt-in)로 실행해 비용·속도를 통제하고, '정밀 모드'(deep)는 다중 에이전트 토론.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertTriangle, Check, ClipboardList, Gavel, Handshake, MessagesSquare, Search, User } from "lucide-react";
import { apiClient } from "@/lib/api-client";

/** 안정적 캐시키용 경량 해시 */
function hashStr(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

type Expert = { role: string; opinion: string; key_points?: string[]; concerns?: string[] };
type Debate = { issue: string; positions: string; resolution: string };
type Verification = { confidence?: number | null; risks?: string[]; counterpoints?: string[]; data_gaps?: string[] };
type PanelResult = {
  generated?: boolean;
  roster?: string[];
  experts: Expert[];
  debate: Debate[];
  consensus: string;
  recommended_actions?: string[];
  verification?: Verification;
};

export function ExpertPanelCard({
  analysisType,
  address,
  context,
  className = "",
}: {
  analysisType: "permit" | "regulation" | "market" | "feasibility" | "site" | "cost" | "tax" | "esg" | "design";
  address?: string;
  context: Record<string, unknown> | null;
  className?: string;
}) {
  const [deep, setDeep] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PanelResult | null>(null);
  const [cached, setCached] = useState(false);

  // 캐시키: 유형+주소+모드+맥락 해시 (single/deep 별도 저장)
  const cacheKey = useMemo(() => {
    try {
      return `propai_panel_${analysisType}_${deep ? "deep" : "single"}_${hashStr((address || "") + JSON.stringify(context || {}))}`;
    } catch { return ""; }
  }, [analysisType, address, context, deep]);

  // 저장된 패널 결과 자동 복원 (재실행·재방문 시 비용 절감)
  useEffect(() => {
    if (!cacheKey || typeof window === "undefined") { setResult(null); setCached(false); return; }
    try {
      const raw = window.localStorage.getItem(cacheKey);
      if (raw) { setResult(JSON.parse(raw)); setCached(true); return; }
    } catch { /* noop */ }
    setResult(null); setCached(false);
  }, [cacheKey]);

  const run = useCallback(async () => {
    if (!context) { setError("먼저 분석을 실행하세요."); return; }
    setLoading(true); setError(""); setResult(null); setCached(false);
    try {
      const r = await apiClient.post<PanelResult>("/expert-panel/analyze", {
        body: { analysis_type: analysisType, address: address || "", context, mode: deep ? "deep" : "single" },
        useMock: false, timeoutMs: deep ? 180000 : 120000,
      });
      setResult(r);
      try { if (cacheKey) window.localStorage.setItem(cacheKey, JSON.stringify(r)); } catch { /* quota */ }
    } catch {
      setError("전문가 패널 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [analysisType, address, context, deep, cacheKey]);

  const conf = result?.verification?.confidence;

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
            <Gavel className="size-4" aria-hidden /> 전문가 검토 패널
            {cached && <span className="ml-2 rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">저장된 결과</span>}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            관련 전문가(설계사·디벨로퍼·공무원·법률가·도시계획 등)가 다관점에서 분석·토론하고 통합 의견·검증을 제시합니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
            <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)}
              className="h-4 w-4 accent-[var(--accent-strong)]" disabled={loading} />
            정밀 모드 <span className="font-normal text-[var(--text-hint)]">(약 3분, 여러 전문가 토론)</span>
          </label>
          <button onClick={run} disabled={loading || !context}
            className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50">
            {loading ? (deep ? "패널 토론 중… (최대 3분)" : "패널 분석 중…") : result ? "다시 분석" : "패널 검증 실행"}
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs font-semibold text-rose-500">{error}</p>}

      {result && (
        <div className="mt-4 space-y-4">
          {/* 통합 결론 + 신뢰도 */}
          <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
            <div className="flex items-center justify-between">
              <p className="inline-flex items-center gap-1.5 text-xs font-black text-[var(--accent-strong)]"><Handshake className="size-3.5" aria-hidden /> 다관점 통합 결론</p>
              <div className="flex items-center gap-2">
                {conf != null && (
                  <span className="rounded-full bg-[var(--surface-strong)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-secondary)]">
                    신뢰도 {conf}%
                  </span>
                )}
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${result.generated ? "border-[var(--accent-strong)]/30 text-[var(--accent-strong)]" : "border-[var(--line-strong)] text-[var(--text-tertiary)]"}`}>
                  {result.generated ? (result.roster ? `전문가 ${result.experts?.length ?? 0}인` : "AI") : "규칙기반"}
                </span>
              </div>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{result.consensus}</p>
            {(result.recommended_actions?.length ?? 0) > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs text-[var(--text-secondary)]">
                {result.recommended_actions!.map((a, i) => <li key={i} className="flex items-start gap-1"><Check className="mt-0.5 size-3 shrink-0" aria-hidden /><span>{a}</span></li>)}
              </ul>
            )}
          </div>

          {/* 전문가별 관점 */}
          <div className="grid gap-3 md:grid-cols-2">
            {(result.experts ?? []).map((e, i) => (
              <div key={i} className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3.5">
                <p className="inline-flex items-center gap-1.5 text-xs font-black text-[var(--text-primary)]"><User className="size-3.5" aria-hidden /> {e.role}</p>
                <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{e.opinion}</p>
                {(e.key_points?.length ?? 0) > 0 && (
                  <ul className="mt-1.5 space-y-0.5 text-[11px] text-[var(--text-tertiary)]">
                    {e.key_points!.map((p, j) => <li key={j}>· {p}</li>)}
                  </ul>
                )}
                {(e.concerns?.length ?? 0) > 0 && (
                  <p className="mt-1.5 flex items-start gap-1 text-[11px] text-amber-500"><AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden /><span>{e.concerns!.join(" / ")}</span></p>
                )}
              </div>
            ))}
          </div>

          {/* 토론 쟁점 */}
          {(result.debate?.length ?? 0) > 0 && (
            <div>
              <p className="inline-flex items-center gap-1.5 text-xs font-bold text-[var(--text-primary)]"><MessagesSquare className="size-3.5" aria-hidden /> 토론 쟁점</p>
              <div className="mt-2 space-y-2">
                {(result.debate ?? []).map((d, i) => (
                  <div key={i} className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs">
                    <p className="font-bold text-[var(--text-primary)]">{d.issue}</p>
                    <p className="mt-0.5 text-[var(--text-secondary)]">이견: {d.positions}</p>
                    <p className="mt-0.5 text-emerald-500">→ {d.resolution}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 검증: 리스크·반론·데이터 공백 */}
          {result.verification && (
            <div className="grid gap-3 md:grid-cols-3">
              <VBlock title={<span className="inline-flex items-center gap-1"><Search className="size-3" aria-hidden /> 검증 리스크</span>} items={result.verification.risks} tone="rose" />
              <VBlock title="↔ 반론·맹점" items={result.verification.counterpoints} tone="amber" />
              <VBlock title={<span className="inline-flex items-center gap-1"><ClipboardList className="size-3" aria-hidden /> 추가 확인 필요</span>} items={result.verification.data_gaps} tone="sky" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function VBlock({ title, items, tone }: { title: ReactNode; items?: string[]; tone: string }) {
  if (!items || items.length === 0) return null;
  const color: Record<string, string> = { rose: "text-rose-400", amber: "text-amber-400", sky: "text-sky-400" };
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-3">
      <p className={`text-[11px] font-bold ${color[tone] || ""}`}>{title}</p>
      <ul className="mt-1 space-y-0.5 text-[11px] text-[var(--text-secondary)]">
        {items.map((it, i) => <li key={i}>· {it}</li>)}
      </ul>
    </div>
  );
}
