"use client";

/**
 * 투자 수익성 분석 — 부동산개발 사업수지 기반(프로젝트 연동·자동로드·전문가 검증).
 *
 * 기존 단순 임대수익 계산기 → 개발사업 투자분석으로 전면 재구축:
 *  ① 프로젝트 선택 시 부지분석·설계 결과 자동 로드(전부 사용자 수정 가능)
 *  ② 토지비/공사비/일반사업비/금융(레버리지)/분양매출 구조화 입력
 *  ③ 실제 수지엔진 /api/v2/feasibility/calculate(15모델·4대 비용엔진) 계산
 *  ④ 총사업비 분해 + 순이익·수익률·ROI·NPV·자기자본수익률(ROE)·등급
 *  ⑤ 전문가 패널(회계사·세무사·MBA·디벨로퍼·시공사·증권·저축은행) + 할루시네이션 검증
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NumberInput } from "@/components/common/NumberInput";
import { ExpertPanelCard } from "@/components/common/ExpertPanelCard";
import { VerificationBadge } from "@/components/common/VerificationBadge";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/* ── 타입 ── */
interface CalcResult {
  development_type: string;
  module_name: string;
  total_revenue_won: number;
  total_cost_won: number;
  net_profit_won: number;
  profit_rate_pct: number;
  roi_pct: number;
  npv_won: number;
  grade: string;
  cost_breakdown_won: Record<string, number>; // land/construction/finance/other/tax
}

interface Form {
  development_type: string;
  building_type: string;
  total_land_area_sqm: number;
  official_price_per_sqm: number;
  price_multiplier: number;
  total_gfa_sqm: number;
  total_households: number;
  avg_sale_price_per_pyeong: number;
  avg_area_pyeong: number;
  sale_ratio: number;
  equity_won: number;
  bridge_amount_won: number;
  pf_amount_won: number;
  midpay_amount_won: number;
  sido_name: string;
  sigungu_name: string;
  project_months: number;
  discount_rate: number;
}

const DEV_TYPES = [
  ["M06", "일반분양(공동주택)"], ["M07", "주상복합"], ["M08", "오피스텔"],
  ["M09", "지식산업센터"], ["M01", "재개발"], ["M02", "재건축"],
  ["M04", "지역주택조합"], ["M03", "역세권개발"], ["M10", "단독주택"],
] as const;
const BUILDING_TYPES = [
  ["apartment", "아파트/공동주택"], ["officetel", "오피스텔"], ["office", "업무시설"],
  ["townhouse", "연립·다세대"], ["single_house", "단독주택"], ["warehouse", "지식산업센터/창고"],
] as const;

const SIDO = ["서울특별시", "경기도", "인천광역시", "부산광역시", "대구광역시", "대전광역시", "광주광역시", "울산광역시", "세종특별자치시", "강원도", "충청북도", "충청남도", "전라북도", "전라남도", "경상북도", "경상남도", "제주특별자치도"];

const PYEONG = 3.305785;

function fmtKrw(won: number): string {
  if (won == null || isNaN(won)) return "-";
  const abs = Math.abs(won);
  const sign = won < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(abs).toLocaleString()}원`;
}

function mapBuildingType(bt?: string | null): string {
  const s = (bt || "").toString();
  if (/오피스텔/.test(s)) return "officetel";
  if (/지식산업|창고|물류/.test(s)) return "warehouse";
  if (/업무|오피스(?!텔)/.test(s)) return "office";
  if (/연립|다세대|빌라/.test(s)) return "townhouse";
  if (/단독/.test(s)) return "single_house";
  return "apartment";
}
function mapDevType(bt: string): string {
  if (bt === "officetel") return "M08";
  if (bt === "warehouse") return "M09";
  if (bt === "office") return "M07";
  return "M06";
}
function parseSido(addr?: string | null): string {
  const a = addr || "";
  return SIDO.find((s) => a.includes(s) || a.includes(s.replace(/특별시|광역시|특별자치시|특별자치도|도$/g, ""))) || "";
}

const EMPTY: Form = {
  development_type: "M06", building_type: "apartment",
  total_land_area_sqm: 0, official_price_per_sqm: 0, price_multiplier: 1.2,
  total_gfa_sqm: 0, total_households: 0,
  avg_sale_price_per_pyeong: 25000000, avg_area_pyeong: 25, sale_ratio: 1.0,
  equity_won: 0, bridge_amount_won: 0, pf_amount_won: 0, midpay_amount_won: 0,
  sido_name: "", sigungu_name: "", project_months: 36, discount_rate: 0.08,
};

const fcls = "w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

/* ── 입력 행(자동/입력 배지 + 전부 수정가능) ── */
function NumRow({ label, unit, value, auto, edited, onChange, step, comma, decimal }: {
  label: string; unit?: string; value: number; auto: boolean; edited: boolean;
  onChange: (v: number) => void; step?: number; comma?: boolean; decimal?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-secondary)]">
        {label}
        {auto && !edited && <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[9px] font-bold text-emerald-400">자동</span>}
        {auto && edited && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-bold text-amber-400">수정됨</span>}
        {!auto && <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">입력</span>}
      </span>
      <div className="flex items-center gap-1.5">
        {comma ? (
          <NumberInput allowDecimal={decimal} value={Number.isFinite(value) ? value : 0}
            onChange={(n) => onChange(n ?? 0)} className={fcls} />
        ) : (
          <input type="number" step={step} value={Number.isFinite(value) ? value : 0}
            onChange={(e) => onChange(Number(e.target.value))} className={fcls} />
        )}
        {unit && <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">{unit}</span>}
      </div>
    </label>
  );
}

export function InvestmentFeasibilityClient() {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const costData = useProjectContextStore((s) => s.costData);
  const projectId = useProjectContextStore((s) => s.projectId);
  const isStale = useProjectContextStore((s) => s.isStale);

  const [form, setForm] = useState<Form>(EMPTY);
  const [autoFields, setAutoFields] = useState<Set<keyof Form>>(new Set());
  const [editedFields, setEditedFields] = useState<Set<keyof Form>>(new Set());
  const [pickerAddr, setPickerAddr] = useState("");
  const [result, setResult] = useState<CalcResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  // 마지막 계산에 사용한 공사비(원) — 공사비 변경 감지(stale)용
  const [costAtCalc, setCostAtCalc] = useState<number | null>(null);

  const set = useCallback((k: keyof Form, v: number | string) => {
    setForm((f) => ({ ...f, [k]: v }));
    setEditedFields((e) => new Set(e).add(k));
  }, []);

  // 프로젝트(활성 컨텍스트) → 폼 자동 로드. 사용자가 수정한 필드는 보존.
  useEffect(() => {
    if (!projectId) return;
    const land = siteAnalysis?.landAreaSqm || 0;
    const officialP = siteAnalysis?.officialPrices?.[0]?.pricePerSqm
      || (siteAnalysis?.estimatedValue && land ? Math.round(siteAnalysis.estimatedValue / land) : 0);
    const gfa = designData?.totalGfaSqm || 0;
    const bt = mapBuildingType(designData?.buildingType);
    const sido = parseSido(siteAnalysis?.address);
    const auto = new Set<keyof Form>();
    setForm((f) => {
      const n = { ...f };
      const put = (k: keyof Form, v: number | string, cond: boolean) => {
        if (cond && !editedFields.has(k)) { (n as Record<string, unknown>)[k] = v; auto.add(k); }
      };
      put("total_land_area_sqm", land, land > 0);
      put("official_price_per_sqm", officialP, officialP > 0);
      put("total_gfa_sqm", gfa, gfa > 0);
      put("building_type", bt, !!designData?.buildingType);
      put("development_type", mapDevType(bt), !!designData?.buildingType);
      put("sido_name", sido, !!sido);
      return n;
    });
    setAutoFields(auto);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, siteAnalysis, designData]);

  const calc = useCallback(async () => {
    if (!form.total_land_area_sqm || !form.total_gfa_sqm) {
      setErr("대지면적과 연면적을 입력하세요(프로젝트를 선택하면 자동 반영됩니다).");
      return;
    }
    setLoading(true); setErr("");
    try {
      const r = await apiClient.postV2<CalcResult>("/feasibility/calculate", {
        body: {
          ...form, project_name: pickerAddr || siteAnalysis?.address || "투자분석", land_category: "land",
          // 공사비 정밀 분석 결과가 있으면 수지엔진에 그대로 주입(3자 수치 정합)
          params: costData?.totalConstructionCostWon
            ? { construction_cost_override_won: costData.totalConstructionCostWon }
            : {},
        },
        useMock: false, timeoutMs: 90000,
      });
      setResult(r);
      // 이번 계산에 반영된 공사비를 기록(이후 공사비 변경 시 stale 감지)
      setCostAtCalc(costData?.totalConstructionCostWon ?? null);
    } catch {
      setErr("수지 계산에 실패했습니다. 입력값을 확인 후 다시 시도하세요.");
    } finally { setLoading(false); }
  }, [form, pickerAddr, siteAnalysis, costData]);

  // 공사비→수지 stale 판정: 이미 계산된 결과가 있고, 공사비가 수지보다 최신이거나
  // 직전 계산에 쓰인 공사비와 현재 공사비가 다르면 재계산 필요.
  const costStale = useMemo(() => {
    if (!result) return false;
    const cur = costData?.totalConstructionCostWon ?? null;
    if (cur == null) return false;
    if (isStale("feasibility")) return true;
    return costAtCalc != null && cur !== costAtCalc;
  }, [result, costData, costAtCalc, isStale]);

  // 마운트 상태에서 공사비가 변경되면 1회 자동 재계산(무한루프 방지: costStale가 곧 false가 됨).
  useEffect(() => {
    if (costStale && !loading) {
      void calc();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [costStale]);

  // 파생 지표: 자기자본수익률(ROE), 타인자본, 실효 LTV
  const derived = useMemo(() => {
    if (!result) return null;
    const equity = form.equity_won || 0;
    const debt = Math.max(0, result.total_cost_won - equity);
    const roe = equity > 0 ? (result.net_profit_won / equity) * 100 : null;
    const ltv = result.total_cost_won > 0 ? (debt / result.total_cost_won) * 100 : 0;
    return { equity, debt, roe, ltv };
  }, [result, form.equity_won]);

  const breakdown = result ? result.cost_breakdown_won : {};
  const COST_LABELS: [string, string][] = [
    ["land", "토지비"], ["construction", "공사비"], ["other", "일반사업비"], ["finance", "금융비용"], ["tax", "세금"],
  ];
  const totalCost = result?.total_cost_won || 0;

  const isAuto = (k: keyof Form) => autoFields.has(k);
  const isEdited = (k: keyof Form) => editedFields.has(k);

  return (
    <section className="grid gap-6">
      <div>
        <h1 className="text-2xl font-black text-[var(--text-primary)]">투자 수익성 분석 (개발사업 수지 기반)</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          프로젝트를 선택하면 부지·설계 데이터를 자동 반영하고, 토지비·공사비·일반사업비·금융 레버리지·분양매출 구조로 NPV·IRR·ROI·자기자본수익률을 실제 수지엔진으로 계산합니다. <b className="text-[var(--text-primary)]">자동 값도 모두 수정</b>할 수 있습니다.
      </p>
      </div>

      {/* 프로젝트 선택(자동 로드) */}
      <ProjectAddressInput value={pickerAddr} onChange={setPickerAddr} label="분석 대상 프로젝트" pickerLabel="프로젝트" placeholder="프로젝트를 선택하거나 주소를 검색하세요" />
      {!projectId && (
        <p className="-mt-3 text-[11px] text-[var(--text-hint)]">※ 프로젝트를 선택하면 대지면적·공시지가·연면적·용도가 자동 반영됩니다. 미선택 시 직접 입력하세요.</p>
      )}

      {/* 입력 폼 */}
      <div className="grid gap-5 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5 lg:grid-cols-2">
        {/* 토지 */}
        <div className="space-y-3">
          <h3 className="text-xs font-black uppercase tracking-widest text-[var(--accent-strong)]">① 토지</h3>
          <NumRow label="대지면적" unit="㎡" comma decimal value={form.total_land_area_sqm} auto={isAuto("total_land_area_sqm")} edited={isEdited("total_land_area_sqm")} onChange={(v) => set("total_land_area_sqm", v)} />
          <NumRow label="공시지가" unit="원/㎡" comma value={form.official_price_per_sqm} auto={isAuto("official_price_per_sqm")} edited={isEdited("official_price_per_sqm")} onChange={(v) => set("official_price_per_sqm", v)} />
          <NumRow label="감정/매입 배율" value={form.price_multiplier} step={0.05} auto={false} edited={false} onChange={(v) => set("price_multiplier", v)} />
        </div>
        {/* 건축 */}
        <div className="space-y-3">
          <h3 className="text-xs font-black uppercase tracking-widest text-[var(--accent-strong)]">② 건축·개발종목</h3>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">개발종목</span>
            <select value={form.development_type} onChange={(e) => set("development_type", e.target.value)} className={fcls}>
              {DEV_TYPES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">건축유형</span>
            <select value={form.building_type} onChange={(e) => set("building_type", e.target.value)} className={fcls}>
              {BUILDING_TYPES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
            </select>
          </label>
          <NumRow label="연면적(GFA)" unit="㎡" comma decimal value={form.total_gfa_sqm} auto={isAuto("total_gfa_sqm")} edited={isEdited("total_gfa_sqm")} onChange={(v) => set("total_gfa_sqm", v)} />
          <NumRow label="총 세대/호실수" unit="세대" comma value={form.total_households} auto={false} edited={false} onChange={(v) => set("total_households", v)} />
        </div>
        {/* 분양 */}
        <div className="space-y-3">
          <h3 className="text-xs font-black uppercase tracking-widest text-[var(--accent-strong)]">③ 분양(공급)</h3>
          <NumRow label="평균 분양가" unit="원/평" comma value={form.avg_sale_price_per_pyeong} auto={false} edited={false} onChange={(v) => set("avg_sale_price_per_pyeong", v)} />
          <NumRow label="평균 전용면적" unit="평" value={form.avg_area_pyeong} auto={false} edited={false} onChange={(v) => set("avg_area_pyeong", v)} />
          <NumRow label="분양률" unit="0~1" value={form.sale_ratio} step={0.05} auto={false} edited={false} onChange={(v) => set("sale_ratio", v)} />
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">지역(시도)</span>
            <select value={form.sido_name} onChange={(e) => set("sido_name", e.target.value)} className={fcls}>
              <option value="">선택…</option>
              {SIDO.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>
        {/* 금융·기간 */}
        <div className="space-y-3">
          <h3 className="text-xs font-black uppercase tracking-widest text-[var(--accent-strong)]">④ 금융 레버리지·기간</h3>
          <NumRow label="자기자본(자부담)" unit="원" comma value={form.equity_won} auto={false} edited={false} onChange={(v) => set("equity_won", v)} />
          <NumRow label="본PF 대출액" unit="원" comma value={form.pf_amount_won} auto={false} edited={false} onChange={(v) => set("pf_amount_won", v)} />
          <NumRow label="브릿지론" unit="원" comma value={form.bridge_amount_won} auto={false} edited={false} onChange={(v) => set("bridge_amount_won", v)} />
          <div className="grid grid-cols-2 gap-2">
            <NumRow label="사업기간" unit="개월" value={form.project_months} auto={false} edited={false} onChange={(v) => set("project_months", v)} />
            <NumRow label="할인율" unit="0~1" value={form.discount_rate} step={0.01} auto={false} edited={false} onChange={(v) => set("discount_rate", v)} />
          </div>
        </div>
      </div>

      {costStale && (
        <button onClick={calc} disabled={loading}
          className="flex items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 text-left text-xs font-bold text-amber-400 hover:bg-amber-500/15 disabled:opacity-50">
          🔄 공사비가 변경되었습니다 — 클릭하면 변경된 공사비({fmtKrw(costData?.totalConstructionCostWon ?? 0)})로 수지를 재계산합니다.
        </button>
      )}

      <div className="flex items-center gap-3">
        <button onClick={calc} disabled={loading}
          className="rounded-xl bg-[var(--accent-strong)] px-8 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50">
          {loading ? "수지 계산 중…" : "수지·투자수익성 분석"}
        </button>
        {err && <span className="text-xs font-semibold text-rose-400">{err}</span>}
      </div>

      {/* 결과 */}
      {result && derived && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["순이익", fmtKrw(result.net_profit_won), result.net_profit_won >= 0 ? "text-emerald-400" : "text-rose-400"],
              ["수익률", `${result.profit_rate_pct.toFixed(1)}%`, "text-[var(--accent-strong)]"],
              ["ROI", `${result.roi_pct.toFixed(1)}%`, "text-[var(--text-primary)]"],
              ["자기자본수익률(ROE)", derived.roe != null ? `${derived.roe.toFixed(1)}%` : "-", "text-indigo-400"],
              ["NPV", fmtKrw(result.npv_won), result.npv_won >= 0 ? "text-emerald-400" : "text-rose-400"],
              ["총 분양매출", fmtKrw(result.total_revenue_won), "text-[var(--text-primary)]"],
              ["총 사업비", fmtKrw(result.total_cost_won), "text-[var(--text-primary)]"],
              ["사업성 등급", result.grade, "text-amber-400"],
            ].map(([k, v, cls]) => (
              <div key={k} className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-5">
                <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{k}</p>
                <p className={`mt-2 text-2xl font-[1000] tracking-tight ${cls}`}>{v}</p>
              </div>
            ))}
          </div>

          {/* 총사업비 구조 분해 */}
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
            <h3 className="mb-3 text-sm font-black text-[var(--text-primary)]">총사업비 구조 ({result.module_name})</h3>
            <div className="space-y-2">
              {COST_LABELS.map(([k, label]) => {
                const v = breakdown[k] || 0;
                const pct = totalCost > 0 ? (v / totalCost) * 100 : 0;
                return (
                  <div key={k} className="flex items-center gap-3">
                    <span className="w-20 shrink-0 text-xs font-semibold text-[var(--text-secondary)]">{label}</span>
                    <div className="h-3 flex-1 overflow-hidden rounded-full bg-[var(--surface-strong)]">
                      <div className="h-full rounded-full bg-[var(--accent-strong)]" style={{ width: `${Math.min(100, pct)}%` }} />
                    </div>
                    <span className="w-24 shrink-0 text-right text-xs font-bold text-[var(--text-primary)]">{fmtKrw(v)}</span>
                    <span className="w-12 shrink-0 text-right text-[11px] text-[var(--text-tertiary)]">{pct.toFixed(0)}%</span>
                  </div>
                );
              })}
            </div>
            {/* 공사비 분석 연동(단일 데이터원) */}
            {costData?.totalConstructionCostWon != null && (
              <div className="mt-3 rounded-lg bg-[var(--surface-strong)] px-3 py-2 text-[11px] text-[var(--accent-strong)]">
                🔗 공사비 정밀 분석 연동 — 정밀 총공사비 <b>{fmtKrw(costData.totalConstructionCostWon)}</b>
                {costData.rangeMinWon != null && costData.rangeMaxWon != null && <span className="text-[var(--text-tertiary)]"> (범위 {fmtKrw(costData.rangeMinWon)}~{fmtKrw(costData.rangeMaxWon)})</span>}
                <span className="text-[var(--text-tertiary)]"> · 위 엔진 공사비({fmtKrw(breakdown.construction || 0)})와 동일 건축개요 기준</span>
              </div>
            )}

            {/* 금융 레버리지 */}
            <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2 border-t border-[var(--line)] pt-4 text-xs">
              <span><b className="text-[var(--text-secondary)]">자기자본</b> <span className="text-[var(--text-primary)] font-bold">{fmtKrw(derived.equity)}</span></span>
              <span><b className="text-[var(--text-secondary)]">타인자본(추정)</b> <span className="text-[var(--text-primary)] font-bold">{fmtKrw(derived.debt)}</span></span>
              <span><b className="text-[var(--text-secondary)]">실효 레버리지(LTV)</b> <span className="text-[var(--accent-strong)] font-bold">{derived.ltv.toFixed(0)}%</span></span>
            </div>
          </div>

          {/* 할루시네이션 검증 + 전문가 패널(회계사·세무사·MBA·디벨로퍼·시공사·증권·저축은행) */}
          <VerificationBadge analysisType="feasibility" context={{ inputs: form, result } as unknown as Record<string, unknown>} />
          <ExpertPanelCard
            analysisType="feasibility"
            address={siteAnalysis?.address || pickerAddr}
            context={{ inputs: form, result, derived, requested_experts: ["회계사", "세무사", "MBA", "디벨로퍼", "시공사", "투자증권", "저축은행"] } as unknown as Record<string, unknown>}
          />
        </>
      )}
    </section>
  );
}
