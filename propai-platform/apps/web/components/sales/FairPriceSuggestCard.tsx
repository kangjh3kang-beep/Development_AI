"use client";

/**
 * P1-2 적정분양가 추천 카드 — 주변 실거래(교차검증) 기반 기준층 분양가 3안(보수/기준/공격).
 * GET /sales/pricing/suggest → 공급면적(상업=분양면적) 평당가·㎡단가·84타입 총액 + 신뢰도.
 * "이 단가로 채택" → onAdopt(원/㎡) 으로 전 타입 기준단가(PER_AREA) 일괄 반영.
 * 직접입력(평당 만원) 도 지원. 가짜값 금지: data_source!=live 면 근거/경고 그대로 표기.
 */
import { useState } from "react";
import { salesApi } from "@/lib/salesApi";
import { ApiClientError } from "@/lib/api-client";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";

type Tier = { tier: string; label: string; premium_pct: number; per_pyeong_10k: number; per_sqm_10k: number; ref_unit_total_10k: number };
type Suggest = {
  data_source: string; address?: string; lawd_cd?: string; area_basis_label?: string;
  market_reference?: { market_pp_supply_10k?: number; market_pp_exclusive_10k?: number; dong?: { median?: number; n?: number }; sigungu?: { median?: number; n?: number } };
  trust?: { confidence?: number; verdict?: string; used_sources?: string[]; excluded_outliers?: { name?: string; reason?: string }[]; warnings?: string[] };
  tiers?: Tier[]; note?: string;
  // 전역정책 Phase0: 근거·법령링크·신선도(백엔드 build_evidence_block 출력 — additive).
  evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[]; provenance?: { name?: string }[];
};

const eok = (man?: number) => (man && man > 0 ? `${(man / 10000).toLocaleString(undefined, { maximumFractionDigits: 1 })}억` : "-");

export default function FairPriceSuggestCard({ siteCode, onAdopt }: { siteCode: string; onAdopt: (perSqmWon: number, label: string) => void }) {
  const [data, setData] = useState<Suggest | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [direct, setDirect] = useState("");

  const load = async () => {
    setBusy(true); setErr("");
    try {
      const r = await salesApi(siteCode).get<Suggest>("/pricing/suggest");
      setData(r);
      if (r.data_source !== "live") setErr(r.note || "주변시세 데이터를 확보하지 못했습니다.");
    } catch (e) {
      const st = e instanceof ApiClientError ? e.status : 0;
      setErr(st === 401 || st === 403 ? "권한이 없습니다(시행사·대행사)." : `적정분양가 조회 실패${st ? ` (오류 ${st})` : ""}.`);
    } finally { setBusy(false); }
  };

  const conf = data?.trust?.confidence ?? 0;
  const confColor = conf >= 0.7 ? "text-emerald-500" : conf >= 0.45 ? "text-amber-500" : "text-rose-500";

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-bold text-[var(--text-secondary)]">⓪ 적정분양가 추천 <span className="font-normal text-[var(--text-hint)]">(주변 실거래 교차검증)</span></p>
        <button onClick={load} disabled={busy}
          className="rounded-md border border-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50">
          {busy ? "분석 중…" : data ? "다시 분석" : "추천 받기"}
        </button>
      </div>

      {err && <p className="mb-2 rounded-md bg-rose-500/10 px-2 py-1 text-[11px] text-rose-500">{err}</p>}

      {data?.tiers && data.tiers.length > 0 && (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
            <span>주변 실거래(공급) <b className="text-[var(--text-secondary)]">{data.market_reference?.market_pp_supply_10k?.toLocaleString()}만원/평</b></span>
            <span>· 기준 {data.area_basis_label}</span>
            <span>· 신뢰도 <b className={confColor}>{Math.round(conf * 100)}%</b> ({data.trust?.verdict})</span>
            {data.market_reference?.dong?.n ? <span>· 동 실거래 {data.market_reference.dong.n}건</span> : null}
            {data.market_reference?.sigungu?.n ? <span>· 시군구 {data.market_reference.sigungu.n}건</span> : null}
          </div>

          <div className="grid grid-cols-3 gap-2">
            {data.tiers.map((t) => (
              <div key={t.tier} className={`rounded-lg border p-2 text-center ${t.tier === "base" ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]" : "border-[var(--line)] bg-[var(--surface-strong)]"}`}>
                <p className="text-[11px] font-bold text-[var(--text-secondary)]">{t.label} <span className="text-[var(--text-hint)]">+{t.premium_pct}%</span></p>
                <p className="mt-0.5 text-base font-black text-[var(--text-primary)]">{t.per_pyeong_10k.toLocaleString()}<span className="text-[10px] font-normal">만원/평</span></p>
                <p className="text-[10px] text-[var(--text-tertiary)]">84타입 {eok(t.ref_unit_total_10k)}</p>
                <button onClick={() => onAdopt(Math.round(t.per_sqm_10k * 10000), t.label)}
                  className="mt-1.5 w-full rounded-md bg-[var(--accent-strong)] px-2 py-1 text-[11px] font-bold text-white hover:opacity-90">채택</button>
              </div>
            ))}
          </div>

          {data.trust?.excluded_outliers && data.trust.excluded_outliers.length > 0 && (
            <p className="mt-2 text-[10px] text-amber-500/90">⚠ 이상치 제외: {data.trust.excluded_outliers.map((e) => `${e.name}(${e.reason})`).join(", ")}</p>
          )}

          <div className="mt-2 flex items-center gap-1.5">
            <input type="number" value={direct} onChange={(e) => setDirect(e.target.value)} placeholder="직접입력(평당 만원)"
              className="w-36 rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
            <button onClick={() => { const pp = Number(direct); if (pp > 0) onAdopt(Math.round((pp / 3.305785) * 10000), "직접입력"); }}
              className="rounded-md border border-[var(--line-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-secondary)]">직접 채택</button>
            <span className="text-[10px] text-[var(--text-hint)]">채택 시 전 타입 기준단가(㎡당)로 일괄 반영</span>
          </div>
          <p className="mt-1.5 text-[10px] leading-snug text-[var(--text-hint)]">{data.note}</p>

          {/* 산출 근거 + 법령 원문(EvidencePanel) — adaptEvidence로 legal_ref_key 조인.
              url_status=pending이면 LegalRefChip이 텍스트 폴백(가짜 링크 0). */}
          {(() => {
            const items = adaptEvidence(data.evidence, data.legal_refs);
            return items.length > 0 ? <div className="mt-2"><EvidencePanel items={items} title="적정분양가 산출 근거" /></div> : null;
          })()}

          {/* AI 검증 배지 — 분양가 산출(원천 실거래 vs 산출값) 교차검증 자동 실행. */}
          <div className="mt-2">
            <VerificationBadge
              analysisType="fair_price"
              context={{
                address: data.address,
                market_reference: data.market_reference,
                tiers: data.tiers,
                trust: data.trust,
              }}
            />
          </div>
        </>
      )}
    </div>
  );
}
