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

type Tier = { tier: string; label: string; premium_pct: number; per_pyeong_10k: number; per_sqm_10k: number; ref_unit_total_10k: number; construction_cost_ratio_pct?: number; margin_over_construction_pct?: number; cost_viable?: boolean };
// 2차 가드(원가 회수 검증) — 백엔드 cost_validation 그대로 소비(반쪽출하 방지).
type CostValidation = {
  cost_basis?: string; construction_cost_per_supply_pyeong_10k?: number;
  viable_price_floor_per_pyeong_10k?: number; conservative_viable?: boolean; warning?: string | null;
};
type Suggest = {
  data_source: string; address?: string; lawd_cd?: string; area_basis_label?: string;
  market_reference?: { market_pp_supply_10k?: number; market_pp_exclusive_10k?: number; dong?: { median?: number; n?: number }; sigungu?: { median?: number; n?: number } };
  trust?: { confidence?: number; verdict?: string; used_sources?: string[]; excluded_outliers?: { name?: string; reason?: string }[]; warnings?: string[] };
  tiers?: Tier[]; cost_validation?: CostValidation | null; note?: string;
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
                {/* ★[iter-2 반쪽출하 해소] 백엔드 cost_validation 이 tier별로 부착하는 원가 회수 지표를 렌더.
                    cost_viable(원가 회수 가능 여부) 배지 + 원가비율·마진. 데이터 없는 tier 는 정직 생략. */}
                {t.cost_viable != null && (
                  <span className={`mt-1 inline-block rounded-full px-1.5 py-0.5 text-[9px] font-bold ${t.cost_viable ? "bg-emerald-500/15 text-emerald-600" : "bg-rose-500/15 text-rose-500"}`}>
                    {t.cost_viable ? "원가회수 가능" : "원가미회수 ⚠"}
                  </span>
                )}
                {(t.construction_cost_ratio_pct != null || t.margin_over_construction_pct != null) && (
                  <p className="mt-0.5 text-[9px] leading-tight text-[var(--text-tertiary)]">
                    {t.construction_cost_ratio_pct != null && <>원가비율 {t.construction_cost_ratio_pct}%</>}
                    {t.construction_cost_ratio_pct != null && t.margin_over_construction_pct != null && " · "}
                    {t.margin_over_construction_pct != null && (
                      <span className={t.margin_over_construction_pct < 0 ? "text-rose-500" : ""}>마진 {t.margin_over_construction_pct}%</span>
                    )}
                  </p>
                )}
                <button onClick={() => onAdopt(Math.round(t.per_sqm_10k * 10000), t.label)}
                  className="mt-1.5 w-full rounded-md bg-[var(--accent-strong)] px-2 py-1 text-[11px] font-bold text-white hover:opacity-90">채택</button>
              </div>
            ))}
          </div>

          {data.trust?.excluded_outliers && data.trust.excluded_outliers.length > 0 && (
            <p className="mt-2 text-[10px] text-amber-500/90">⚠ 이상치 제외: {data.trust.excluded_outliers.map((e) => `${e.name}(${e.reason})`).join(", ")}</p>
          )}

          {/* 2차 가드: 원가(공사비+간접) 회수 검증 — 시장가가 원가를 못 넘으면 경고(가짜값 아님·정직 표기) */}
          {data.cost_validation && (
            <p className={`mt-2 rounded-md px-2 py-1 text-[10px] leading-snug ${data.cost_validation.warning ? "bg-rose-500/10 text-rose-500" : "bg-emerald-500/10 text-emerald-600/90"}`}>
              {/* ★[iter-3 데드필드 렌더] conservative_viable(보수안 원가회수 가능 여부) 배지 +
                  construction_cost_per_supply_pyeong_10k(공급평당 원가)을 함께 노출(타입선언만 하고
                  안 그리던 dead 필드 제거 — 백엔드가 산출한 지표를 화면에 종단배선). */}
              {data.cost_validation.conservative_viable != null && (
                <b className={data.cost_validation.conservative_viable ? "text-emerald-600" : "text-rose-500"}>
                  {data.cost_validation.conservative_viable ? "보수안 원가회수 OK" : "보수안 원가미회수 ⚠"} ·{" "}
                </b>
              )}
              원가검증({data.cost_validation.cost_basis})
              {data.cost_validation.construction_cost_per_supply_pyeong_10k != null
                ? ` · 공급평당 원가 ${data.cost_validation.construction_cost_per_supply_pyeong_10k.toLocaleString()}만원/평`
                : ""}
              {" · 원가기반 최저선 "}<b>{data.cost_validation.viable_price_floor_per_pyeong_10k?.toLocaleString()}만원/평</b>
              {data.cost_validation.warning ? ` · ⚠ ${data.cost_validation.warning}` : " · 보수안이 원가 최저선을 충족합니다."}
            </p>
          )}

          <div className="mt-2 flex items-center gap-1.5">
            <input type="number" value={direct} onChange={(e) => setDirect(e.target.value)} placeholder="직접입력(평당 만원)"
              className="w-36 rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
            <button onClick={() => { const pp = Number(direct); if (pp > 0) onAdopt(Math.round((pp / 3.305785) * 10000), "직접입력"); }}
              className="rounded-md border border-[var(--line-strong)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-secondary)]">직접 채택</button>
            <span className="text-[10px] text-[var(--text-hint)]">채택 시 전 타입 기준단가(㎡당)로 일괄 반영</span>
          </div>
          <p className="mt-1.5 text-[10px] leading-snug text-[var(--text-hint)]">{data.note}</p>
        </>
      )}
    </div>
  );
}
