"use client";

/**
 * 관련법령 탐색 카드 — LLM이 부지 맥락의 핵심·관련 법령/조례/고시를 검색·식별하고 법령 정본(LegalHub)으로
 * 교차검증한 결과를 surface(L4: 법령엔진을 사용자에게 노출). POST /regulation/legal-discovery.
 *
 * 정직성: verified_ssot(정본 등재·law.go.kr 검증링크) vs llm_unverified(LLM 식별·정본 미등재·확인권고)를
 * 배지로 구분(무날조 — 가짜 링크를 검증된 것처럼 표시하지 않음). 지역 고시는 토지이음 deep-link.
 * opt-in(버튼)+localStorage 캐시(재과금 방지).
 */

import { useEffect, useState } from "react";
import { ScrollText, ShieldCheck, AlertTriangle, ExternalLink, Sparkles } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type LawItem = {
  law?: string; article?: string; category?: string; reason?: string;
  url?: string; verification?: string; registry_key?: string | null;
};
type GosiRef = { available?: boolean; region?: string; list_url?: string; categories?: string[] };
type DiscoverResp = {
  core_laws?: LawItem[]; related_laws?: LawItem[]; regional_gosi?: GosiRef | null;
  cross_validation?: { total?: number; verified_ssot?: number; llm_unverified?: number; gosi_identified?: number };
  disclosure?: string; generated?: boolean;
};

function hash(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

function CatBadge({ category }: { category?: string }) {
  const c = category === "고시" ? "bg-violet-500/15 text-violet-400"
    : category === "조례" ? "bg-sky-500/15 text-sky-400"
    : "bg-slate-500/15 text-slate-400";
  return <span className={`rounded px-1 py-0.5 text-[9px] font-bold ${c}`}>{category || "법령"}</span>;
}

function LawRow({ item }: { item: LawItem }) {
  const verified = item.verification === "verified_ssot";
  return (
    <li className="flex items-start gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1.5">
      {verified
        ? <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-emerald-500" aria-hidden />
        : <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-500" aria-hidden />}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1">
          <CatBadge category={item.category} />
          <span className="text-[11px] font-bold text-[var(--text-primary)]">{item.law}{item.article ? ` ${item.article}` : ""}</span>
          {verified
            ? <span className="text-[9px] font-bold text-emerald-500">정본 검증</span>
            : <span className="text-[9px] font-bold text-amber-500">LLM 식별·확인권고</span>}
        </div>
        {item.reason && <p className="text-[10px] leading-snug text-[var(--text-hint)]">{item.reason}</p>}
      </div>
      {item.url && verified && (
        <a href={item.url} target="_blank" rel="noopener noreferrer" title="법령 원문(law.go.kr)"
          className="shrink-0 text-[var(--accent-strong)]"><ExternalLink className="size-3.5" aria-hidden /></a>
      )}
    </li>
  );
}

export function LegalDiscoveryCard({ address }: { address?: string | null }) {
  const [data, setData] = useState<DiscoverResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const zoneCode = site?.zoneCode ?? null;

  const addr = (address ?? site?.address ?? "").trim();
  const parts = addr.split(/\s+/);
  const sido = parts[0] || "";
  const sigungu = parts.slice(1, 3).join(" ") || "";
  const key = addr ? `propai_legal_discovery_${hash(addr)}_${hash(zoneCode || "")}` : "";

  useEffect(() => {
    if (!key || typeof window === "undefined") { setData(null); return; }
    try { const raw = window.localStorage.getItem(key); setData(raw ? JSON.parse(raw) : null); }
    catch { setData(null); }
  }, [key]);

  async function run() {
    if (!addr || loading) return;
    setLoading(true); setError("");
    try {
      const r = await apiClient.post<DiscoverResp>("/regulation/legal-discovery", {
        body: { context: { zone_type: zoneCode || undefined, address: addr, sido, sigungu } },
        useMock: false, timeoutMs: 70000,
      });
      if (r && (r.core_laws?.length || r.related_laws?.length)) {
        setData(r);
        try { if (key) window.localStorage.setItem(key, JSON.stringify(r)); } catch { /* quota */ }
      } else {
        setError("관련 법령을 식별하지 못했습니다(LLM 미응답).");
      }
    } catch {
      setError("관련법령 탐색에 실패했습니다.");
    } finally { setLoading(false); }
  }

  if (!addr) return null;
  const cv = data?.cross_validation;

  return (
    <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--accent-strong)]">
          <Sparkles className="size-4" aria-hidden /> AI 관련법령 탐색·교차검증
        </p>
        <button onClick={run} disabled={loading}
          className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-black text-white hover:opacity-90 disabled:opacity-50">
          {loading ? "탐색 중…" : data ? "다시 탐색" : "관련법령 탐색"}
        </button>
      </div>
      {error && <p className="mt-2 text-[11px] text-[var(--danger,#dc2626)]">{error}</p>}
      {data && (
        <div className="mt-2.5 space-y-2.5">
          {cv && (
            <p className="text-[10px] text-[var(--text-hint)]">
              총 {cv.total}건 · <span className="text-emerald-500">정본검증 {cv.verified_ssot}</span> ·
              <span className="text-amber-500"> 확인권고 {cv.llm_unverified}</span>
              {cv.gosi_identified ? ` · 고시 ${cv.gosi_identified}` : ""}
            </p>
          )}
          {!!data.core_laws?.length && (
            <div>
              <p className="text-[11px] font-bold text-[var(--text-secondary)]">핵심 법령</p>
              <ul className="mt-1 space-y-1">{data.core_laws.map((it, i) => <LawRow key={`c${i}`} item={it} />)}</ul>
            </div>
          )}
          {!!data.related_laws?.length && (
            <div>
              <p className="text-[11px] font-bold text-[var(--text-secondary)]">관련 법령</p>
              <ul className="mt-1 space-y-1">{data.related_laws.map((it, i) => <LawRow key={`r${i}`} item={it} />)}</ul>
            </div>
          )}
          {data.regional_gosi?.list_url && (
            <a href={data.regional_gosi.list_url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] transition hover:border-[var(--accent-strong)]">
              <ScrollText className="size-3.5" aria-hidden /> 지역 고시정보(토지이음) 열람 <ExternalLink className="size-3" aria-hidden />
            </a>
          )}
          {data.disclosure && <p className="text-[10px] leading-relaxed text-[var(--text-hint)]">{data.disclosure}</p>}
        </div>
      )}
      {!data && !error && (
        <p className="mt-2 text-[11px] text-[var(--text-hint)]">버튼을 눌러 이 부지에 적용되는 법령·조례·고시를 AI로 탐색하고 법령 정본으로 교차검증합니다.</p>
      )}
    </div>
  );
}
