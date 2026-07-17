"use client";

/**
 * 개략수지(rough-scenario) 통합 워크플로우 패널.
 *
 * 사용자 요구를 한 화면에서 완결한다:
 *  ① 프로젝트 선택/수정 — ProjectSwitcher(공용)로 프로젝트를 고르면 그 컨텍스트
 *     (주소·다필지·용도·통합면적)를 개략수지 입력으로 프리필한다. 주소는 직접 수정도 가능.
 *  ③④⑤⑥⑦ 기본 개략수지 — '개략수지 생성' 버튼으로 POST /api/v2/feasibility/rough-scenario
 *     를 호출해 입력요약·토지비·공사비·분양수입·20% 마진·요약지표를 구조화 표시.
 *  ③ 월별 DCF — 응답 cashflow.monthly_rows 를 월별 표로, summary(NPV·IRR·회수기간·peak) 요약.
 *  ⑧ 2차 사용자 수정 — 토지비·공사비 단가·분양단가·공사기간·마진율·할인율 등을 편집해
 *     overrides 로 재요청(source=user_override 배지·원값 대비 변경 하이라이트).
 *
 * 무목업 원칙: 백엔드가 값을 못 구한 축은 null + degraded_notes 로 내려온다. 프론트도
 * '데이터 없음'으로 정직 표기하고 가짜 0 을 만들지 않는다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ComposedChart,
  Bar,
  Line,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { apiClient, resolveApiOrigin } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { parcelDataToRows, shouldSendParcels } from "@/lib/parcel-rows";
import { regionFromAddress } from "@/lib/region";
import { ProjectSwitcher } from "@/components/common/ProjectSwitcher";
import { roughResultToFeasibilityPatch } from "@/components/feasibility/rough-scenario-commit";
import { DataSourceNotice } from "@/components/ui/DataSourceNotice";

/** Nexus label-caps(DESIGN.md B2) — 인풋 상단 소형 라벨. Space Grotesk 대문자 트래킹. */
const labelCapsCls =
  "text-[11px] font-bold uppercase tracking-[0.06em] text-[var(--text-tertiary)]";
const labelCapsStyle = { fontFamily: "var(--font-display)" } as const;

/* ── 백엔드 /feasibility/rough-scenario 응답 계약(1:1) ── */
interface RsInputs {
  land_area_sqm: number | null;
  zone_type: string | null;
  effective_far_pct: number | null;
  dev_type: string | null;
  dev_type_name?: string | null;
  gfa_sqm: number | null;
  saleable_area_pyeong: number | null;
  parcel_count: number | null;
  project_months: number | null;
  // 세대수 가정(GFA÷유형 표준 전용면적) — 설계 확정 전 리스크시뮬 base 재계산용(백엔드 additive).
  total_households?: number | null;
}
interface RsLandCost {
  total_won: number | null;
  per_sqm_won: number | null;
  basis: string | null;
  evidence?: unknown;
  source: string | null;
}
interface RsConstruction {
  total_won: number | null;
  unit_per_sqm_won: number | null;
  basis: string | null;
  source: string | null;
}
interface RsRevenue {
  total_won: number | null;
  sale_price_per_pyeong: number | null;
  saleable_area_pyeong: number | null;
  basis: string | null;
  source: string | null;
}
interface RsCostBreakdown {
  land_won: number | null;
  construction_won: number | null;
  finance_won: number | null;
  other_won: number | null;
  /** 부담금(B공사+C분양 단계 시행사 부담) — 백엔드 6b 계상. 구버전 응답은 미존재(옵셔널 소비). */
  charges_won?: number | null;
}
interface RsMargin {
  developer_profit_won: number | null;
  rate_pct: number | null;
  target_revenue_won: number | null;
}
interface RsSummary {
  total_cost_won: number | null;
  total_revenue_won: number | null;
  net_profit_won: number | null;
  roi_pct: number | null;
  npv_won: number | null;
  irr_pct: number | null;
  payback_month: number | null;
  grade: string | null;
}
interface RsCashflowRow {
  month: number;
  phase: string;
  inflow: number;
  outflow: number;
  net?: number;
  cumulative: number;
}
interface RsCashflowSummary {
  total_months?: number;
  total_inflow?: number;
  total_outflow?: number;
  net_profit?: number;
  profit_rate_pct?: number;
  peak_negative_cashflow?: number;
  equity_amount?: number;
  bridge_loan_amount?: number;
  pf_loan_amount?: number;
  irr_annual_pct?: number | null;
  npv_won?: number | null;
  discount_rate_annual_pct?: number;
  payback_month?: number | null;
}
interface RoughScenarioResult {
  address: string;
  project_id: string | null;
  scenario_status: string;
  inputs: RsInputs;
  land_cost: RsLandCost;
  construction_cost: RsConstruction;
  revenue: RsRevenue;
  cost_breakdown: RsCostBreakdown;
  margin: RsMargin;
  summary: RsSummary;
  cashflow: { monthly_rows: RsCashflowRow[]; summary: RsCashflowSummary } | null;
  overrides_applied: string[];
  degraded_notes: string[];
  special_parcel?: { honest_disclosure?: string | null } | null;
}

/* ── 표기 헬퍼 — 값 없으면 null 반환(호출부가 '데이터 없음' 정직표기) ── */
const eok = (v: number | null | undefined): string | null =>
  v == null || !Number.isFinite(v)
    ? null
    : `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억`;
const wonStr = (v: number | null | undefined): string | null =>
  v == null || !Number.isFinite(v) ? null : `${Math.round(v).toLocaleString()}원`;
const pctStr = (v: number | null | undefined, digits = 1): string | null =>
  v == null || !Number.isFinite(v) ? null : `${Number(v).toFixed(digits)}%`;
const sqmStr = (v: number | null | undefined): string | null =>
  v == null || !Number.isFinite(v) ? null : `${Math.round(v).toLocaleString()}㎡`;
const pyStr = (v: number | null | undefined): string | null =>
  v == null || !Number.isFinite(v) ? null : `${Math.round(v).toLocaleString()}평`;
const moStr = (v: number | null | undefined): string | null =>
  v == null || !Number.isFinite(v) ? null : `${Math.round(v)}개월`;

/** 값 또는 '데이터 없음'(무목업 정직표기). */
function Val({ text }: { text: string | null }) {
  if (text == null)
    return <span className="font-normal text-[var(--text-hint)]">데이터 없음</span>;
  return <>{text}</>;
}

// 추정·폴백·미확보 계열 출처 토큰 — 검증된 실데이터가 아니므로 amber(경고)로 정직 구분.
// ★HIGH-1/2: "폴백"뿐 아니라 "추정"·"비실거래"·"미확보"·"가정단가"·"실지가 아님"도 amber.
//   초록(success)은 검증된 실데이터(주변 실거래 MOLIT·탁상감정·국토부 SSOT 등)에만 준다.
const ESTIMATE_SOURCE_TOKENS = [
  "추정",
  "비실거래",
  "폴백",
  "fallback",
  "미확보",
  "가정단가",
  "실지가 아님",
];

/** 데이터 출처 배지 — 백엔드 source 문자열을 정직하게 색으로 구분(토큰만 사용). */
function SourceBadge({ source }: { source: string | null | undefined }) {
  if (!source || source === "unavailable") return null;
  const s = source;
  let variant: "success" | "warning" | "accent" = "success";
  let label = s;
  if (s === "user_override") {
    variant = "accent";
    label = "실데이터 반영(사용자 수정)";
  } else if (ESTIMATE_SOURCE_TOKENS.some((t) => s.includes(t))) {
    variant = "warning";
  }

  return (
    <span className={`sa-chip sa-chip--${variant}`} title={`데이터 출처: ${s}`}>
      {label}
    </span>
  );
}

/** 사업성 등급 배지 — 등급별 의미색(토큰). */
function GradeChip({ grade }: { grade: string | null | undefined }) {
  if (!grade) return null;
  const g = grade.toUpperCase();
  const variant =
    g.startsWith("S") || g.startsWith("A")
      ? "success"
      : g.startsWith("B") || g.startsWith("C")
      ? "warning"
      : "error";
  return <span className={`sa-chip sa-chip--${variant}`}>등급 {grade}</span>;
}

/* ── 2차 수정(overrides) 필드 정의 — 백엔드 overrides 키와 1:1 ── */
type OverrideKey =
  | "land_cost_won"
  | "construction_unit_won"
  | "sale_price_per_pyeong"
  | "construction_months"
  | "sale_start_month"
  | "sale_duration_months"
  | "margin_rate_pct"
  | "discount_rate_pct";
const OVERRIDE_FIELDS: { key: OverrideKey; label: string; hint: string }[] = [
  { key: "land_cost_won", label: "토지비 총액(원)", hint: "적정 토지비(취득세 등 포함)" },
  { key: "construction_unit_won", label: "공사비 단가(원/㎡)", hint: "연면적당 직접공사비" },
  { key: "sale_price_per_pyeong", label: "분양단가(원/평)", hint: "공급면적 기준" },
  { key: "construction_months", label: "공사기간(월)", hint: "착공~준공" },
  { key: "sale_start_month", label: "분양시작(월)", hint: "착공 기준 개월" },
  { key: "sale_duration_months", label: "분양기간(월)", hint: "분양 소진 개월" },
  { key: "margin_rate_pct", label: "마진율(%)", hint: "총사업비 대비 개발이익" },
  { key: "discount_rate_pct", label: "할인율(%)", hint: "NPV 할인율(연)" },
];

type OverrideBaseline = Partial<Record<OverrideKey, number | null>>;

const inputCls =
  "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

export function RoughScenarioPanel({ projectId }: { projectId?: string }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  const updateFeasibilityData = useProjectContextStore((s) => s.updateFeasibilityData);
  // ★인플라이트 프로젝트 전환 오염 가드(보강): 요청을 보낸 "시점"의 프로젝트를 기억해뒀다가
  //   커밋 시점에 대조한다. result.project_id 가드만으로는 약식(프로젝트 미확정) 요청처럼
  //   응답에 project_id가 없는 경우를 못 걸러 레이스가 남는다.
  const requestProjectRef = useRef<string | null>(null);

  // 부지 컨텍스트 프리필(주소는 수정 가능 — 요구 ①).
  const [address, setAddress] = useState(siteAnalysis?.address ?? "");
  const [result, setResult] = useState<RoughScenarioResult | null>(null);
  const [busy, setBusy] = useState<"" | "base" | "override">("");
  const [error, setError] = useState<string | null>(null);

  // 2차 수정 폼(문자열 입력) + 기준값(원값 대비 변경 하이라이트용).
  const [form, setForm] = useState<Partial<Record<OverrideKey, string>>>({});
  const [baseline, setBaseline] = useState<OverrideBaseline>({});
  const [showOverrides, setShowOverrides] = useState(false);
  // ★W4(감사 고아 엔드포인트): 개략수지→시니어 보고서(/rough-scenario/report) 다운로드 상태.
  //   백엔드가 pdf/pptx/docx 3포맷을 지원 → 어떤 포맷이 생성 중인지 문자열로 추적(시장 ReportActionsBar 패턴 미러).
  const [reportFmt, setReportFmt] = useState<"" | "pdf" | "pptx" | "docx">("");
  const [reportError, setReportError] = useState<string | null>(null);

  // ★W4: 백엔드 보고서 엔진(/rough-scenario/report — BankReady·통합 보고서 정본 조합)이
  //   프론트 호출 0건 고아였다. 현재 시나리오를 그대로 전달해 재계산 없이 보고서를 받는다.
  //   백엔드는 pdf/pptx/docx 3포맷 지원(v2_feasibility.py RoughScenarioReportRequest.format).
  //   use_llm=false 기본(과금 정책 — AI 서술 없이 정직 고지 포함 보고서).
  const downloadReport = useCallback(async (fmt: "pdf" | "pptx" | "docx") => {
    if (!result) return;
    setReportFmt(fmt);
    setReportError(null);
    try {
      const token =
        (typeof window !== "undefined" && localStorage.getItem("propai_access_token")?.trim()) || "";
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 120_000);
      let res: Response;
      try {
        res = await fetch(`${resolveApiOrigin()}/api/v2/feasibility/rough-scenario/report`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ scenario: result, use_llm: false, format: fmt }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
      if (!res.ok) {
        // 오류 사유 보존 — 백엔드 {detail}(422 재생성/생성 실패 등)을 읽어 실제 원인을 표기.
        let detail = "";
        try {
          const body = (await res.json()) as { detail?: string };
          detail = body?.detail || "";
        } catch { /* JSON 아니면 상태코드만 */ }
        throw new Error(detail || `보고서 생성 실패 (${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `rough-scenario-report-${new Date().toISOString().slice(0, 10)}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setReportError(e instanceof Error ? e.message : "보고서 생성 실패");
    } finally {
      setReportFmt("");
    }
  }, [result]);

  // 프로젝트 전환(컨텍스트 주소 변경) 시 주소 필드를 그 프로젝트로 재적재하고 이전 결과를 비운다.
  const lastCtxAddrRef = useRef<string | null>(siteAnalysis?.address ?? null);
  useEffect(() => {
    const ctxAddr = siteAnalysis?.address ?? null;
    if (ctxAddr && ctxAddr !== lastCtxAddrRef.current) {
      lastCtxAddrRef.current = ctxAddr;
      setAddress(ctxAddr);
      setResult(null);
      setForm({});
      setBaseline({});
      setError(null);
    }
  }, [siteAnalysis?.address]);

  // 결과 산출 시 모세혈관(feasibilityData) 반영 — 이 SSOT를 STEP 2 투자수익성 요약과
  //   STEP 3 리스크 시뮬 base 조립(buildNodeBody)이 읽는다(페이지 계약: 앞 단계 결과 이어받기).
  //   ★인플라이트 오염 가드: 응답의 project_id가 있고 현재 컨텍스트 프로젝트와 다르면
  //   (요청 후 프로젝트 전환) 남의 프로젝트 SSOT를 덮지 않도록 커밋하지 않는다.
  useEffect(() => {
    if (!result) return;
    if (result.project_id && ctxProjectId && result.project_id !== ctxProjectId) return;
    // 요청 시점 프로젝트와 현재 프로젝트가 다르면(인플라이트 중 전환·약식→프로젝트 포함) 커밋 금지.
    if (requestProjectRef.current !== ((projectId || ctxProjectId) ?? null)) return;
    const patch = roughResultToFeasibilityPatch(result);
    if (patch) updateFeasibilityData(patch);
  }, [result, ctxProjectId, updateFeasibilityData, projectId]);

  // 컨텍스트에서 파생되는 입력(통합면적·다필지·자기자본).
  const landArea = useMemo(() => effectiveLandAreaSqm(siteAnalysis), [siteAnalysis]);
  const parcelRows = useMemo(
    () => parcelDataToRows(siteAnalysis?.parcels),
    [siteAnalysis?.parcels],
  );
  const equityWon = useMemo(() => {
    // 자동파생(총사업비×비율) 자기자본은 재전송하지 않는다 — 1차/2차 생성 결과가 달라지는
    // 비멱등 방지. 사용자가 직접 입력한 값(equityIsManual)만 백엔드에 실어보낸다.
    if (feasibilityData?.equityIsManual !== true) return undefined;
    const e = feasibilityData?.equityWon;
    return typeof e === "number" && e > 0 ? e : undefined;
  }, [feasibilityData?.equityWon, feasibilityData?.equityIsManual]);

  /** rough-scenario 요청 body 조립(공용) — 다필지는 2필지↑일 때만 첨부(무회귀). */
  const buildBody = useCallback(
    (overrides?: Record<string, number>) => ({
      address: address.trim(),
      ...(shouldSendParcels(parcelRows) ? { parcels: parcelRows } : {}),
      project_id: projectId || ctxProjectId || undefined,
      // region: 시군구는 주소로 정밀 매칭되므로 여기선 폴백 힌트만 — 미도출 시 "" 로
      //  '서울' 기본값이 지방 부지를 과대평가하지 않게 한다(백엔드 주소 시도추론에 위임).
      region: regionFromAddress(address) ?? "",
      ...(equityWon ? { equity_won: equityWon } : {}),
      ...(overrides && Object.keys(overrides).length > 0 ? { overrides } : {}),
    }),
    [address, parcelRows, projectId, ctxProjectId, equityWon],
  );

  /** 기본 개략수지 생성(요구 ③④⑤⑥⑦) — overrides 없이 호출하고 2차 수정 기준값을 시드. */
  const generateBase = useCallback(async () => {
    if (!address.trim()) {
      setError("주소가 없습니다. 프로젝트를 선택하거나 주소를 입력하세요.");
      return;
    }
    setBusy("base");
    setError(null);
    try {
      requestProjectRef.current = (projectId || ctxProjectId) ?? null;
      const r = await apiClient.postV2<RoughScenarioResult>("/feasibility/rough-scenario", {
        body: buildBody(),
      });
      setResult(r);
      // 2차 수정 기준값(원값) 시드 — 공사기간/분양시작은 백엔드 기본식과 동일하게 근사.
      const pm = r.inputs.project_months ?? 30;
      const cm = Math.max(6, pm - 6);
      const base: OverrideBaseline = {
        land_cost_won: r.land_cost.total_won,
        construction_unit_won: r.construction_cost.unit_per_sqm_won,
        sale_price_per_pyeong: r.revenue.sale_price_per_pyeong,
        construction_months: cm,
        sale_start_month: Math.min(6, Math.max(0, cm - 1)),
        sale_duration_months: 6,
        margin_rate_pct: r.margin.rate_pct ?? 20,
        discount_rate_pct: r.cashflow?.summary?.discount_rate_annual_pct ?? 6,
      };
      setBaseline(base);
      const seeded: Partial<Record<OverrideKey, string>> = {};
      for (const f of OVERRIDE_FIELDS) {
        const v = base[f.key];
        seeded[f.key] = v == null ? "" : String(v);
      }
      setForm(seeded);
    } catch (e) {
      setError(e instanceof Error ? e.message : "개략수지 산정에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }, [address, buildBody, projectId, ctxProjectId]);

  /** 변경된 override 만 추출(원값과 다르고 유효 숫자인 키). */
  const buildOverrides = useCallback((): Record<string, number> => {
    const out: Record<string, number> = {};
    for (const f of OVERRIDE_FIELDS) {
      const raw = (form[f.key] ?? "").trim();
      if (!raw) continue;
      const n = Number(raw);
      if (!Number.isFinite(n)) continue;
      const base = baseline[f.key];
      if (base != null && Number(base) === n) continue; // 원값과 동일 — 미전송
      out[f.key] = n;
    }
    return out;
  }, [form, baseline]);

  const changedKeys = useMemo(
    () => new Set(Object.keys(buildOverrides())),
    [buildOverrides],
  );

  /** 2차 수정 반영 재계산(요구 ⑧) — 변경된 overrides 로 재요청. */
  const recalcWithOverrides = useCallback(async () => {
    if (!address.trim()) return;
    const overrides = buildOverrides();
    setBusy("override");
    setError(null);
    try {
      requestProjectRef.current = (projectId || ctxProjectId) ?? null;
      const r = await apiClient.postV2<RoughScenarioResult>("/feasibility/rough-scenario", {
        body: buildBody(overrides),
      });
      setResult(r); // 기준값(baseline)은 유지 — 계속 원값 대비 변경을 하이라이트.
    } catch (e) {
      setError(e instanceof Error ? e.message : "재계산에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }, [address, buildBody, buildOverrides, projectId, ctxProjectId]);

  const inp = result?.inputs;
  const cf = result?.cashflow;

  return (
    <div className="flex flex-col gap-6">
      {/* ── ① 프로젝트 선택/수정 + 부지 컨텍스트 ── */}
      <section className="sa-di-block">
        <div className="sa-di-block__body space-y-4">
          <div className="flex items-center gap-2">
            <span className="sa-di-eyebrow">STEP 1 · 프로젝트 · 부지</span>
          </div>
          {/* 공용 프로젝트 선택기 — 선택 시 컨텍스트(주소·다필지·용도·면적) 자동 적재 */}
          <ProjectSwitcher />
          {/* 주소 직접 수정(요구 ① '수정 가능') */}
          <label className="block">
            <span className={labelCapsCls} style={labelCapsStyle}>
              분석 주소
            </span>
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="예) 서울특별시 강남구 역삼동 737"
              className={`${inputCls} mt-1`}
            />
          </label>
          {/* 적재된 컨텍스트 요약(전송될 값) */}
          <div className="sa-di-tiles sa-di-tiles--4">
            <div className="sa-di-tile">
              <span className="sa-di-tile__label">통합면적</span>
              <span className="sa-di-tile__value">
                <Val text={sqmStr(landArea)} />
              </span>
            </div>
            <div className="sa-di-tile">
              <span className="sa-di-tile__label">용도지역</span>
              <span className="sa-di-tile__value sa-di-tile__value--text">
                <Val text={siteAnalysis?.zoneCode ?? null} />
              </span>
            </div>
            <div className="sa-di-tile">
              <span className="sa-di-tile__label">필지 수</span>
              <span className="sa-di-tile__value">
                <Val text={siteAnalysis?.parcelCount ? `${siteAnalysis.parcelCount}필지` : parcelRows.length ? `${parcelRows.length}필지` : null} />
              </span>
            </div>
            <div className="sa-di-tile">
              <span className="sa-di-tile__label">자기자본</span>
              <span className="sa-di-tile__value">
                <Val text={equityWon ? eok(equityWon) : null} />
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={generateBase}
              disabled={busy !== "" || !address.trim()}
              className="h-10 rounded-lg bg-[var(--accent-strong)] px-5 text-sm font-bold text-white transition-opacity disabled:opacity-50"
            >
              {busy === "base" ? "산정 중…" : result ? "개략수지 다시 생성" : "개략수지 생성"}
            </button>
            {shouldSendParcels(parcelRows) && (
              <span className="text-[11px] text-[var(--text-hint)]">
                다필지 {parcelRows.length}필지 통합면적 기준으로 산정합니다.
              </span>
            )}
          </div>
          {error && (
            <p className="text-xs font-semibold text-[var(--status-error)]">{error}</p>
          )}
        </div>
      </section>

      {result && (
        <>
          {/* ── degraded 정직표기(무목업) ── */}
          {result.degraded_notes.length > 0 && (
            <section className="rounded-xl border border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] p-4">
              <p className="mb-1.5 flex items-center gap-1.5 text-xs font-bold text-[var(--status-warning)]">
                <span className="sa-dot sa-dot--warning" /> 일부 데이터 미확보 — 정직 강등 고지
              </p>
              <ul className="list-disc space-y-1 pl-5 text-[11px] text-[var(--text-secondary)]">
                {result.degraded_notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </section>
          )}

          {/* ── 입력 요약(요구 ③) ── */}
          <section className="sa-di-block">
            <div className="sa-di-block__body space-y-3">
              <span className="sa-di-eyebrow">입력 요약 · INPUTS</span>
              <div className="sa-di-tiles">
                <Tile label="통합면적" text={sqmStr(inp?.land_area_sqm)} />
                <Tile label="용도지역" text={inp?.zone_type ?? null} textOnly />
                <Tile label="실효 용적률" text={pctStr(inp?.effective_far_pct)} />
                <Tile
                  label="개발유형(Top1)"
                  text={inp?.dev_type_name || inp?.dev_type || null}
                  textOnly
                  accent
                />
                <Tile label="연면적(GFA)" text={sqmStr(inp?.gfa_sqm)} />
                <Tile label="분양가능면적" text={pyStr(inp?.saleable_area_pyeong)} />
                <Tile label="필지 수" text={inp?.parcel_count ? `${inp.parcel_count}필지` : null} />
                <Tile label="사업기간" text={moStr(inp?.project_months)} />
              </div>
            </div>
          </section>

          {/* ── 토지비 · 공사비 · 분양수입(요구 ④⑤⑥) ── */}
          <div className="grid gap-4 lg:grid-cols-3">
            <CostBlock
              eyebrow="토지비 · LAND"
              total={result.land_cost.total_won}
              rows={[
                ["단가(원/㎡)", wonStr(result.land_cost.per_sqm_won)],
              ]}
              basis={result.land_cost.basis}
              source={result.land_cost.source}
            />
            <CostBlock
              eyebrow="공사비 · CONSTRUCTION"
              total={result.construction_cost.total_won}
              rows={[
                ["단가(원/㎡)", wonStr(result.construction_cost.unit_per_sqm_won)],
              ]}
              basis={result.construction_cost.basis}
              source={result.construction_cost.source}
            />
            <CostBlock
              eyebrow="분양수입 · REVENUE"
              total={result.revenue.total_won}
              rows={[
                ["분양단가(원/평)", wonStr(result.revenue.sale_price_per_pyeong)],
                ["분양가능면적", pyStr(result.revenue.saleable_area_pyeong)],
              ]}
              basis={result.revenue.basis}
              source={result.revenue.source}
            />
          </div>

          {/* ── 20% 마진(개발이익) 카드(요구) ── */}
          <section className="sa-di-block">
            <div className="sa-di-block__body">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="sa-di-eyebrow">개발이익 마진 · MARGIN</span>
                <span className="sa-di-token sa-di-token--accent">
                  마진율 {pctStr(result.margin.rate_pct, 0) ?? "—"}
                </span>
              </div>
              <div className="mt-3 sa-di-stats">
                <Stat label="개발이익(마진)" text={eok(result.margin.developer_profit_won)} accent />
                <Stat label="목표매출(역산)" text={eok(result.margin.target_revenue_won)} />
                <Stat label="예상 분양수입" text={eok(result.summary.total_revenue_won)} />
                <Stat
                  label="마진 충족여부"
                  text={
                    result.summary.total_revenue_won != null &&
                    result.margin.target_revenue_won != null
                      ? result.summary.total_revenue_won >= result.margin.target_revenue_won
                        ? "충족"
                        : "미달"
                      : null
                  }
                />
              </div>
            </div>
          </section>

          {/* ── 사업성 요약 지표(요구 ⑦) ── */}
          <section className="sa-di-block">
            <div className="sa-di-block__body">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="sa-di-eyebrow">사업성 요약 · SUMMARY</span>
                <div className="flex items-center gap-1.5">
                  {/* 선행절차(접도 확보·용도 해제 등) 전제 잠정치 — 등급/ROI를 확정치로 오독 방지 */}
                  {result.scenario_status === "tentative" && (
                    <span
                      className="sa-chip sa-chip--warning"
                      title="선행절차(접도 확보·용도 해제 등)를 전제한 잠정치 — ROI·등급·수지는 확정치가 아닙니다"
                    >
                      잠정 · 선행절차 전제
                    </span>
                  )}
                  <GradeChip grade={result.summary.grade} />
                </div>
              </div>
              <div className="mt-3 sa-di-stats">
                <Stat label="총사업비" text={eok(result.summary.total_cost_won)} />
                <Stat label="총수입" text={eok(result.summary.total_revenue_won)} />
                <Stat label="순이익" text={eok(result.summary.net_profit_won)} accent />
                <Stat label="ROI" text={pctStr(result.summary.roi_pct)} />
              </div>
              <div className="mt-3 sa-di-stats">
                <Stat label="NPV" text={eok(result.summary.npv_won)} />
                <Stat label="IRR(연)" text={pctStr(result.summary.irr_pct)} />
                <Stat label="회수기간" text={moStr(result.summary.payback_month)} />
                <Stat label="사업기간" text={moStr(inp?.project_months)} />
              </div>
              {/* 총사업비 구성 근거 투명화 */}
              <div className="mt-4 sa-di-rows">
                <DataRow label="토지비" text={eok(result.cost_breakdown.land_won)} />
                <DataRow label="공사비" text={eok(result.cost_breakdown.construction_won)} />
                <DataRow label="금융비" text={eok(result.cost_breakdown.finance_won)} />
                <DataRow label="제경비(기타)" text={eok(result.cost_breakdown.other_won)} />
                <DataRow label="부담금(공사·분양단계)" text={eok(result.cost_breakdown.charges_won)} />
              </div>
            </div>
          </section>

          {/* ── ★W4: 시니어 사업성 보고서 — 고아 엔드포인트 배선(PDF/PPT/DOCX 3포맷) ── */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => downloadReport("pdf")}
              disabled={!!reportFmt}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-xs font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
            >
              {reportFmt === "pdf" ? "PDF 생성 중…" : "사업성 보고서 PDF"}
            </button>
            <button
              type="button"
              onClick={() => downloadReport("pptx")}
              disabled={!!reportFmt}
              className="rounded-xl border border-[var(--line-strong)] px-5 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
            >
              {reportFmt === "pptx" ? "PPT 생성 중…" : "PPT"}
            </button>
            <button
              type="button"
              onClick={() => downloadReport("docx")}
              disabled={!!reportFmt}
              className="rounded-xl border border-[var(--line-strong)] px-5 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
            >
              {reportFmt === "docx" ? "DOCX 생성 중…" : "DOCX"}
            </button>
            <span className="text-[10px] text-[var(--text-tertiary)]">
              현재 개략수지 그대로 보고서화(재계산 없음·AI 서술 미포함 — 추가 LLM 과금 없음)
            </span>
            {reportError && <span className="text-[11px] text-[var(--status-error,#ef4444)]">{reportError}</span>}
          </div>

          {/* ── ⑧ 2차 사용자 수정(overrides) ── */}
          <section className="sa-di-block">
            <button
              type="button"
              onClick={() => setShowOverrides((v) => !v)}
              className="sa-di-block__head"
            >
              <span className="sa-di-block__title">
                실데이터로 2차 수정 (토지비·공사비·분양단가·기간·마진율·할인율)
              </span>
              {result.overrides_applied.length > 0 && (
                <span className="sa-di-token sa-di-token--accent">
                  {result.overrides_applied.length}개 반영됨
                </span>
              )}
              <span
                className="sa-di-block__chevron"
                data-open={showOverrides ? "true" : "false"}
              >
                ▾
              </span>
            </button>
            {showOverrides && (
              <div className="sa-di-block__body space-y-4">
                <p className="text-[11px] text-[var(--text-hint)]">
                  실제 확보한 값으로 수정하면 총사업비·마진·월별 DCF 가 재계산됩니다. 변경한
                  항목만 <span className="font-bold text-[var(--accent-strong)]">실데이터 반영</span>
                  (source=user_override)으로 표기됩니다.
                </p>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {OVERRIDE_FIELDS.map((f) => {
                    const changed = changedKeys.has(f.key);
                    return (
                      <label key={f.key} className="block">
                        <span className="flex items-center gap-1.5">
                          <span className={labelCapsCls} style={labelCapsStyle}>
                            {f.label}
                          </span>
                          {changed && <span className="sa-dot sa-dot--info" title="원값과 다름(반영 예정)" />}
                        </span>
                        <input
                          type="number"
                          value={form[f.key] ?? ""}
                          onChange={(e) =>
                            setForm((prev) => ({ ...prev, [f.key]: e.target.value }))
                          }
                          className={`${inputCls} mt-1 ${
                            changed ? "border-[var(--accent-strong)]" : ""
                          }`}
                        />
                        <span className="mt-0.5 block text-[10px] text-[var(--text-hint)]">
                          {f.hint}
                          {baseline[f.key] != null && (
                            <> · 원값 {Number(baseline[f.key]).toLocaleString()}</>
                          )}
                        </span>
                      </label>
                    );
                  })}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={recalcWithOverrides}
                    disabled={busy !== "" || changedKeys.size === 0}
                    className="h-9 rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-bold text-white disabled:opacity-50"
                  >
                    {busy === "override" ? "재계산 중…" : `실데이터 반영 재계산 (${changedKeys.size})`}
                  </button>
                  {result.overrides_applied.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {result.overrides_applied.map((k) => (
                        <span key={k} className="sa-di-token sa-di-token--accent">
                          {OVERRIDE_FIELDS.find((f) => f.key === k)?.label ?? k}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>

          {/* ── ③ 월별 DCF ── */}
          <section className="sa-di-block">
            <div className="sa-di-block__body space-y-3">
              <span className="sa-di-eyebrow">월별 현금흐름 · DCF</span>
              {cf && cf.monthly_rows.length > 0 ? (
                <>
                  <div className="sa-di-stats">
                    <Stat label="IRR(연)" text={pctStr(cf.summary.irr_annual_pct ?? result.summary.irr_pct)} accent />
                    <Stat
                      label={`NPV(할인 ${pctStr(cf.summary.discount_rate_annual_pct, 0) ?? "—"})`}
                      text={eok(cf.summary.npv_won ?? result.summary.npv_won)}
                    />
                    <Stat label="최대 자금소요(peak)" text={eok(cf.summary.peak_negative_cashflow)} />
                    <Stat label="자금 회수월" text={moStr(cf.summary.payback_month ?? result.summary.payback_month)} />
                  </div>
                  {/* ★로드맵④: 월별 현금흐름 추세 차트(순현금 막대 + 누적 곡선) — 아래 표와 동일 배열(monthly_rows) 재사용(재계산 0). */}
                  <div>
                    <p className="sa-di-eyebrow mb-2">현금흐름 추세 · CHART</p>
                    <MonthlyCashflowChart rows={cf.monthly_rows} />
                  </div>
                  <div className="max-h-[360px] overflow-auto rounded-lg border border-[var(--line)]">
                    <table className="sa-di-table w-full">
                      <thead className="sticky top-0 bg-[var(--surface-soft)]">
                        <tr>
                          <th>월</th>
                          <th>단계</th>
                          <th className="sa-di-num">유입</th>
                          <th className="sa-di-num">유출</th>
                          <th className="sa-di-num">순현금</th>
                          <th className="sa-di-num">누적</th>
                        </tr>
                      </thead>
                      <tbody>
                        {cf.monthly_rows.map((r) => {
                          const net = r.net ?? r.inflow - r.outflow;
                          return (
                            <tr key={r.month}>
                              <td>{r.month}</td>
                              <td className="text-[var(--text-secondary)]">{r.phase}</td>
                              <td className="sa-di-num">{r.inflow ? eok(r.inflow) : "-"}</td>
                              <td className="sa-di-num">{r.outflow ? eok(r.outflow) : "-"}</td>
                              <td
                                className="sa-di-num"
                                style={{ color: net < 0 ? "var(--status-error)" : "var(--status-success)" }}
                              >
                                {eok(net)}
                              </td>
                              <td
                                className="sa-di-num"
                                style={{
                                  color:
                                    r.cumulative < 0
                                      ? "var(--status-error)"
                                      : "var(--text-primary)",
                                }}
                              >
                                {eok(r.cumulative)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="sa-empty">
                  <span className="text-sm font-semibold text-[var(--text-secondary)]">
                    월별 현금흐름 데이터 없음
                  </span>
                  <span className="text-[11px] text-[var(--text-hint)]">
                    핵심 축(토지비·공사비·분양수입) 결측 시 DCF 를 산출하지 않습니다(무목업).
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* 공공데이터 고지(DESIGN.md B1) — 개략수지 전체 데이터 뷰 하단 출처·참고용 문구 */}
          <DataSourceNotice source="국토교통부 실거래가 · 조달청 공사비 지수 등 공공데이터" />
        </>
      )}
    </div>
  );
}

/* ── 소형 표시 컴포넌트(파일 로컬) ── */
function Tile({
  label,
  text,
  textOnly,
  accent,
}: {
  label: string;
  text: string | null;
  textOnly?: boolean;
  accent?: boolean;
}) {
  return (
    <div className={`sa-di-tile${accent ? " sa-di-tile--accent" : ""}`}>
      <span className="sa-di-tile__label">{label}</span>
      <span className={`sa-di-tile__value${textOnly ? " sa-di-tile__value--text" : ""}`}>
        <Val text={text} />
      </span>
    </div>
  );
}

function Stat({ label, text, accent }: { label: string; text: string | null; accent?: boolean }) {
  return (
    <div className="sa-di-stat">
      <span className="sa-di-stat__label">{label}</span>
      <span
        className="sa-di-stat__value"
        style={accent && text != null ? { color: "var(--data-accent)" } : undefined}
      >
        <Val text={text} />
      </span>
    </div>
  );
}

function DataRow({ label, text }: { label: string; text: string | null }) {
  return (
    <div className="sa-di-row">
      <span className="sa-di-row__label">{label}</span>
      <span className="sa-di-row__value">
        <Val text={text} />
      </span>
    </div>
  );
}

/** 토지비/공사비/분양수입 공용 블록 — 총액 + 세부행 + basis + 출처배지. */
function CostBlock({
  eyebrow,
  total,
  rows,
  basis,
  source,
}: {
  eyebrow: string;
  total: number | null;
  rows: [string, string | null][];
  basis: string | null;
  source: string | null;
}) {
  return (
    <section className="sa-di-block">
      <div className="sa-di-block__body space-y-3">
        <div className="flex items-center justify-between gap-2">
          <span className="sa-di-eyebrow">{eyebrow}</span>
          <SourceBadge source={source} />
        </div>
        <div className="sa-di-stat">
          <span className="sa-di-stat__value" style={{ fontSize: "1.25rem" }}>
            <Val text={eok(total)} />
          </span>
        </div>
        <div className="sa-di-rows">
          {rows.map(([label, text]) => (
            <DataRow key={label} label={label} text={text} />
          ))}
        </div>
        {basis && (
          <p className="text-[10px] leading-relaxed text-[var(--text-hint)]">{basis}</p>
        )}
      </div>
    </section>
  );
}

/**
 * 월별 현금흐름 추세 차트 — 순현금(막대·부호별 색) + 누적 현금흐름(라인).
 * DCF 표(cf.monthly_rows)와 동일 배열을 소비해 재계산하지 않는다(표=상세, 차트=보조 추세).
 * 단위는 억(원/1e8). 색상은 테마 토큰만 사용(DemographicPanel 관례 미러).
 */
function MonthlyCashflowChart({ rows }: { rows: RsCashflowRow[] }) {
  const data = rows.map((r) => ({
    month: r.month,
    net: (r.net ?? r.inflow - r.outflow) / 1e8,
    cumulative: r.cumulative / 1e8,
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 11, fill: "var(--text-secondary)" }}
          axisLine={{ stroke: "var(--line)" }}
          tickLine={false}
          label={{
            value: "개월",
            position: "insideBottomRight",
            offset: -2,
            fontSize: 10,
            fill: "var(--text-tertiary)",
          }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "var(--text-secondary)" }}
          axisLine={false}
          tickLine={false}
          width={48}
          tickFormatter={(v: number) => `${v}억`}
        />
        <Tooltip
          cursor={{ fill: "color-mix(in srgb, var(--accent-strong) 8%, transparent)" }}
          contentStyle={{
            background: "var(--surface-strong)",
            border: "1px solid var(--line-strong)",
            borderRadius: "var(--r-card)",
            fontSize: 12,
          }}
          formatter={(v, name) => [
            `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 })}억`,
            name,
          ]}
          labelFormatter={(m) => `${m}개월차`}
        />
        <ReferenceLine y={0} stroke="var(--line-strong)" />
        <Bar dataKey="net" name="순현금" radius={[2, 2, 0, 0]} maxBarSize={22}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={
                d.net < 0
                  ? "var(--status-error)"
                  : "color-mix(in srgb, var(--accent-strong) 55%, transparent)"
              }
            />
          ))}
        </Bar>
        <Line
          type="monotone"
          dataKey="cumulative"
          name="누적"
          stroke="var(--accent-strong)"
          strokeWidth={2}
          dot={false}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
