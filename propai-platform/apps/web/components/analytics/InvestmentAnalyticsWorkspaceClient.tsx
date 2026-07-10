"use client";

/**
 * 리스크 시뮬레이션(몬테카를로) — 실수지 base 불확실성 → 손실확률·하방리스크·민감도.
 *
 * ★무목업(전면 재배선): 예전엔 이 위젯이 브라우저에서 setTimeout(가짜지연) + Box-Muller
 *   Math.random()으로 NPV/IRR/히스토그램/민감도를 '조작 생성'했다(apiClient·store 미연동).
 *   이제 프로젝트 실수지 base(FeasibilityCalculateRequest)를 조립해 실제 백엔드를 호출한다:
 *     ① POST /api/v2/feasibility/sensitivity  → 토네이도 + base_values(5변수 기준값)
 *     ② POST /api/v2/feasibility/monte-carlo   → base_values를 평균, 사용자 불확실성을 표준편차로
 *        섭동해 net_profit_won(순이익) 분포·손실확률·하방리스크 산출(실수지 재계산 기반).
 *   base_values(엔진이 산출한 총공사비·총토지비·PF금리 등)를 ①에서 회수해 ②의 변수 평균으로
 *   재사용하므로 프론트가 기준값을 날조하지 않는다(무목업). 그래서 ①→② 순차 호출이다.
 *
 * base 조립(2계층):
 *   1순위) 수지분석 v2 store input — 사용자가 수지분석을 실행해 채운 실입력(그대로 base).
 *   2순위) 프로젝트 컨텍스트 SSOT(개략수지·부지·설계)로 최소 base 조립(공용 buildNodeBody 재사용).
 *   필수(개발유형·부지면적·연면적·매출단가) 결측이면 호출하지 않고 '개략수지/수지분석을 먼저
 *   실행하세요' 정직 안내(가짜 기본값 금지).
 */

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Button, Card, CardContent } from "@propai/ui";
import { NumberInput } from "@/components/common/NumberInput";
import type { Locale } from "@/i18n/config";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { buildNodeBody } from "@/lib/orchestration/node-body-builders";
import {
  useProjectContextStore,
  type SiteAnalysisData,
  type DesignData,
  type FeasibilityData,
} from "@/store/useProjectContextStore";
import { useFeasibilityV2Store, type FeasibilityInput } from "@/store/use-feasibility-v2-store";

/* ── 백엔드 응답 타입(계약 1:1) ──
   apps/api/app/schemas/feasibility_v2.py MonteCarloResponse / SensitivityResponse 와 동일 키. */

type HistogramBin = { bin_start: number; bin_end: number; count: number };

type MonteCarloResponse = {
  mean: number; // 순이익 평균(원)
  std: number;
  p5: number; // 하방리스크(최악 5%) 순이익(원)
  p50: number; // 중앙값
  p95: number; // 상방(5% 초과 달성) 순이익(원)
  probability_positive: number; // 흑자확률(0~1) — 손실확률 = 1 - 이 값
  // convergence_ratio 는 변동계수 CV(σ/|μ|) — '수렴'이 아니라 결과 분포의 리스크 지표.
  convergence_ratio: number;
  standard_error_ratio?: number | null; // σ/(√N·|μ|) — 실제 수렴 지표
  converged?: boolean | null; // SE비율 < 1% (표본 충분·안정)
  n_simulations: number; // 실제 실행 횟수(실수지 모드 상한 1,000)
  histogram: HistogramBin[];
  target_metric: string; // 실수지 모드="net_profit_won"
  calc_source: string; // 실수지 모드="feasibility_v2"
  note?: string | null; // 횟수 상한 등 제약 정직 고지
};

type TornadoItem = {
  variable: string;
  name: string;
  low_profit: number; // 수익률(profit_rate_pct, %) 하한
  high_profit: number; // 수익률(%) 상한
  spread: number; // 변동폭(%p) — 내림차순 정렬됨
};

type SensitivityBaseResult = {
  net_profit_won?: number;
  roi_pct?: number;
  npv_won?: number;
  grade?: string;
  profit_rate_pct?: number;
  total_revenue_won?: number;
  total_cost_won?: number;
};

type SensitivityResponse = {
  base_result: SensitivityBaseResult;
  scenarios: unknown[];
  tornado: TornadoItem[];
  base_values: Record<string, number>; // {sale_price, construction_cost, land_cost, interest_rate, project_months}
  calc_source: string;
};

/* ── 섭동 5변수(백엔드 BASE_PERTURB_VARIABLES와 1:1) ──
   사용자는 각 변수의 '불확실성(±%)'만 조정한다. 평균값은 엔진 base_values에서 온다(무날조). */
const PERTURB_VARS: Array<{ key: string; ko: string; en: string; unitKo: string; unitEn: string }> = [
  { key: "sale_price", ko: "분양가", en: "Sale price", unitKo: "원/평", unitEn: "KRW/py" },
  { key: "construction_cost", ko: "총공사비", en: "Construction cost", unitKo: "원", unitEn: "KRW" },
  { key: "land_cost", ko: "총토지비", en: "Land cost", unitKo: "원", unitEn: "KRW" },
  { key: "interest_rate", ko: "금리", en: "Interest rate", unitKo: "PF금리", unitEn: "PF rate" },
  { key: "project_months", ko: "사업기간", en: "Project period", unitKo: "개월", unitEn: "months" },
];

// 기본 불확실성(±%) — 변수별 통념 수준. 사용자가 조정한다.
const DEFAULT_UNCERTAINTY: Record<string, number> = {
  sale_price: 10,
  construction_cost: 10,
  land_cost: 10,
  interest_rate: 15,
  project_months: 10,
};

type MCVariablePayload = { name: string; mean: number; std: number; distribution: string };
type BaseSource = "feasibility-store" | "project-context";

/* ── 유틸 ── */
function numOf(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function strOf(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}
/** ApiClientError면 FastAPI 422 detail을 우선 노출(정직한 원인 표기). */
function errText(e: unknown): string {
  if (e instanceof ApiClientError) {
    const payload = e.payload as { detail?: unknown } | null;
    if (payload && typeof payload.detail === "string") return payload.detail;
    return e.message;
  }
  return e instanceof Error ? e.message : "분석 오류";
}

/**
 * 실수지 base(FeasibilityCalculateRequest) 조립.
 *  1순위: 수지분석 v2 store input(핵심 4필드가 채워졌고 ★현재 프로젝트에 바인딩된 경우만) 그대로 base.
 *  2순위: 프로젝트 컨텍스트 SSOT(개략수지·부지·설계) — 공용 buildNodeBody로 매핑(면적은 통합면적 우선).
 *  결측이면 base=null + missing[] 반환(호출 금지·정직 안내).
 *
 *  ★프로젝트 오염 방지: 수지 store 는 전역 단일이라 프로젝트를 바꿔도 이전 input 이 남는다.
 *   feasBoundProjectId(store.boundProjectId)가 현재 projectId 와 다르면 '남의 프로젝트' 데이터이므로
 *   1순위로 신뢰하지 않고 2순위(현재 프로젝트 SSOT)로 내려간다(무목업·타프로젝트 실데이터 오표시 차단).
 */
function assembleBase(
  feasInput: Partial<FeasibilityInput> | null | undefined,
  feasBoundProjectId: string | null | undefined,
  site: SiteAnalysisData | null,
  design: DesignData | null,
  feas: FeasibilityData | null,
  projectId: string,
): { base: Record<string, unknown> | null; baseSource: BaseSource | null; missing: string[] } {
  // ── 1순위: 수지분석 실행분(store input) — 단, 현재 프로젝트에 바인딩된 경우만 ──
  const li = feasInput ?? {};
  const boundToThisProject = !!feasBoundProjectId && feasBoundProjectId === projectId;
  const hasCore =
    boundToThisProject &&
    !!strOf(li.development_type) &&
    (numOf(li.total_land_area_sqm) ?? 0) > 0 &&
    (numOf(li.total_gfa_sqm) ?? 0) > 0 &&
    (numOf(li.avg_sale_price_per_pyeong) ?? 0) > 0;
  if (hasCore) {
    return { base: { ...li }, baseSource: "feasibility-store", missing: [] };
  }

  // ── 2순위: 프로젝트 컨텍스트 SSOT → 공용 body 매핑(재사용) ──
  const { body, missing } = buildNodeBody(
    "feasibility",
    { siteAnalysis: site, designData: design, feasibilityData: feas },
    projectId,
  );
  // 보강(의미있는 분포용): 공시지가·시도/시군구·기간·할인율. 값 출처는 부지 SSOT 또는 백엔드 표준기본.
  const officialPrice = numOf(site?.officialPrices?.[0]?.pricePerSqm);
  if (officialPrice != null && officialPrice > 0) body.official_price_per_sqm = officialPrice;
  const addr = strOf(site?.address);
  if (addr) {
    const parts = addr.split(/\s+/).filter(Boolean);
    if (parts[0]) body.sido_name = parts[0];
    if (parts[1]) body.sigungu_name = parts[1];
  }
  // feasibilityData엔 기간/할인율이 없으므로 백엔드 문서화 표준기본(48개월·8%)을 명시(요약 표시·섭동 원점).
  if (body.project_months == null) body.project_months = 48;
  if (body.discount_rate == null) body.discount_rate = 0.08;

  // ★매출단가 결측이면 순이익 분포가 무의미(매출=0) → 정직 게이트(가짜 매출 금지).
  if ((numOf(body.avg_sale_price_per_pyeong) ?? 0) <= 0 && !missing.includes("avg_sale_price_per_pyeong")) {
    missing.push("avg_sale_price_per_pyeong");
  }
  // ★백엔드 /calculate 매출은 세대수 기반(total_households×avg_area×단가) — 결측 시 revenue=0으로
  //   손실확률 100% 오탐이 나온다. 세대수·평형 미확보면 정직 게이트(가짜 리스크 지표 금지).
  if ((numOf(body.total_households) ?? 0) <= 0 && !missing.includes("total_households")) {
    missing.push("total_households");
  }
  if ((numOf(body.avg_area_pyeong) ?? 0) <= 0 && !missing.includes("avg_area_pyeong")) {
    missing.push("avg_area_pyeong");
  }
  if (missing.length > 0) return { base: null, baseSource: "project-context", missing };
  return { base: body, baseSource: "project-context", missing: [] };
}

/* ── 라벨(한국어 우선) ── */
type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  formTitle: string;
  uncertaintyIntro: string;
  simulationsLabel: string;
  submitAction: string;
  running: string;
  baseSummaryTitle: string;
  baseSourceStore: string;
  baseSourceContext: string;
  bDevType: string;
  bLandArea: string;
  bGfa: string;
  bSalePrice: string;
  bHouseholds: string;
  bMonths: string;
  bDiscount: string;
  bOfficialPrice: string;
  missingTitle: string;
  missingBody: string;
  missingFieldsPrefix: string;
  noUncertaintyError: string;
  riskTitle: string;
  lossProbLabel: string;
  positiveProbLabel: string;
  downsideLabel: string;
  nSimLabel: string;
  distTitle: string;
  meanLabel: string;
  stdLabel: string;
  p50Label: string;
  p95Label: string;
  histTitle: string;
  honestTitle: string;
  cvLabel: string;
  cvNote: string;
  convergedLabel: string;
  convergedYes: string;
  convergedNo: string;
  seLabel: string;
  targetMetricLabel: string;
  calcSourceLabel: string;
  noteLabel: string;
  baseResultTitle: string;
  netProfitLabel: string;
  roiLabel: string;
  npvLabel: string;
  gradeLabel: string;
  profitRateLabel: string;
  tornadoTitle: string;
  tornadoNote: string;
  baseValuesTitle: string;
  placeholder: string;
  projectRef: string;
};

const KO_LABELS: Labels = {
  heroTitle: "리스크 시뮬레이션",
  heroDescription: "실수지 base의 불확실성으로 손실확률·하방리스크·민감도를 산출합니다.",
  heroHint:
    "실수지 base(개략수지/수지분석 결과)를 기준으로 5개 변수의 불확실성을 몬테카를로로 섭동해 순이익 분포·손실확률·하방리스크·민감도를 산출합니다. 호출: POST /api/v2/feasibility/monte-carlo · /sensitivity (실수지 재계산 기반).",
  formTitle: "불확실성 입력",
  uncertaintyIntro:
    "총사업비·매출은 base(수지)에서 자동 확정됩니다. 아래 5개 변수의 불확실성(±%)과 시뮬 횟수만 조정하세요.",
  simulationsLabel: "시뮬레이션 횟수 (실수지 모드 상한 1,000)",
  submitAction: "리스크 시뮬 실행",
  running: "실수지 재계산 중",
  baseSummaryTitle: "기준 입력(base) — 읽기 전용",
  baseSourceStore: "수지분석 실행분",
  baseSourceContext: "프로젝트 컨텍스트(개략수지·부지·설계)",
  bDevType: "개발유형",
  bLandArea: "부지면적",
  bGfa: "연면적",
  bSalePrice: "분양가(만원/평)",
  bHouseholds: "세대수",
  bMonths: "사업기간",
  bDiscount: "할인율",
  bOfficialPrice: "공시지가(원/㎡)",
  missingTitle: "먼저 수지 base가 필요합니다.",
  missingBody:
    "위 STEP 1 '개략수지(기준 산출)' 또는 수지분석을 먼저 실행하세요. 실수지 base가 있어야 손실확률·하방리스크를 실제로 계산합니다(가짜 기본값을 만들지 않습니다).",
  missingFieldsPrefix: "결측 필수값",
  noUncertaintyError: "변수 불확실성을 1개 이상 0보다 크게 설정하세요.",
  riskTitle: "리스크 요약",
  lossProbLabel: "손실확률 P(순이익<0)",
  positiveProbLabel: "흑자확률 P(순이익>0)",
  downsideLabel: "하방리스크 (최악 5%, p5 순이익)",
  nSimLabel: "실행 횟수",
  distTitle: "순이익 분포",
  meanLabel: "기대 순이익 (평균)",
  stdLabel: "표준편차",
  p50Label: "중앙값 (p50)",
  p95Label: "상방 (p95)",
  histTitle: "순이익 분포 히스토그램",
  honestTitle: "정직 표기 (수렴·출처)",
  cvLabel: "변동계수 CV (σ/|μ|)",
  cvNote: "결과 분포의 리스크 지표 — '수렴'이 아님",
  convergedLabel: "수렴 여부",
  convergedYes: "수렴(표본 충분)",
  convergedNo: "미수렴(표본 확대 권장)",
  seLabel: "표준오차 비율 σ/(√N·|μ|)",
  targetMetricLabel: "대상 지표",
  calcSourceLabel: "산출 출처",
  noteLabel: "제약",
  baseResultTitle: "기준 수지 (base 결과)",
  netProfitLabel: "순이익",
  roiLabel: "ROI",
  npvLabel: "NPV",
  gradeLabel: "사업성 등급",
  profitRateLabel: "수익률",
  tornadoTitle: "민감도 분석 (토네이도 · 수익률 %p)",
  tornadoNote: "각 변수를 ±섭동했을 때 수익률(profit_rate_pct) 변동폭. 내림차순 = 영향 큰 순.",
  baseValuesTitle: "섭동 기준값 (엔진 산출 base_values)",
  placeholder: "불확실성을 확인하고 '리스크 시뮬 실행'을 누르면 손실확률·하방리스크·민감도가 표시됩니다.",
  projectRef: "프로젝트",
};

const EN_LABELS: Labels = {
  heroTitle: "Risk simulation",
  heroDescription: "Derive loss probability, downside risk, and sensitivity from the live feasibility base.",
  heroHint:
    "Perturbs 5 variables' uncertainty around the live feasibility base (rough/detailed feasibility result) via Monte Carlo to derive net-profit distribution, loss probability, downside risk, and sensitivity. Calls: POST /api/v2/feasibility/monte-carlo, /sensitivity (real feasibility re-computation).",
  formTitle: "Uncertainty input",
  uncertaintyIntro:
    "Total cost and revenue are fixed automatically from the base (feasibility). Adjust only the uncertainty (±%) of the 5 variables below and the simulation count.",
  simulationsLabel: "Simulations (real-feasibility mode cap 1,000)",
  submitAction: "Run risk simulation",
  running: "Re-computing feasibility",
  baseSummaryTitle: "Base input — read-only",
  baseSourceStore: "Detailed feasibility run",
  baseSourceContext: "Project context (rough feasibility / site / design)",
  bDevType: "Dev. type",
  bLandArea: "Land area",
  bGfa: "Total GFA",
  bSalePrice: "Sale price (10K KRW/py)",
  bHouseholds: "Households",
  bMonths: "Project period",
  bDiscount: "Discount rate",
  bOfficialPrice: "Official price (KRW/㎡)",
  missingTitle: "A feasibility base is required first.",
  missingBody:
    "Run STEP 1 'Rough feasibility (base)' or the detailed feasibility first. A live base is required to actually compute loss probability and downside risk (no fabricated defaults).",
  missingFieldsPrefix: "Missing required",
  noUncertaintyError: "Set at least one variable's uncertainty above 0.",
  riskTitle: "Risk summary",
  lossProbLabel: "Loss probability P(profit<0)",
  positiveProbLabel: "Positive probability P(profit>0)",
  downsideLabel: "Downside risk (worst 5%, p5 profit)",
  nSimLabel: "Executed runs",
  distTitle: "Net-profit distribution",
  meanLabel: "Expected profit (mean)",
  stdLabel: "Std. deviation",
  p50Label: "Median (p50)",
  p95Label: "Upside (p95)",
  histTitle: "Net-profit histogram",
  honestTitle: "Honest labels (convergence / source)",
  cvLabel: "Coefficient of variation CV (σ/|μ|)",
  cvNote: "Risk indicator of the distribution — NOT convergence",
  convergedLabel: "Converged",
  convergedYes: "Converged (sufficient sample)",
  convergedNo: "Not converged (increase samples)",
  seLabel: "Std. error ratio σ/(√N·|μ|)",
  targetMetricLabel: "Target metric",
  calcSourceLabel: "Calc source",
  noteLabel: "Constraint",
  baseResultTitle: "Base result",
  netProfitLabel: "Net profit",
  roiLabel: "ROI",
  npvLabel: "NPV",
  gradeLabel: "Grade",
  profitRateLabel: "Profit rate",
  tornadoTitle: "Sensitivity (tornado · profit rate %p)",
  tornadoNote: "Profit-rate (profit_rate_pct) swing under ± perturbation. Descending = highest impact first.",
  baseValuesTitle: "Perturbation base_values (engine-computed)",
  placeholder: "Review uncertainty and click 'Run risk simulation' to see loss probability, downside risk, and sensitivity.",
  projectRef: "Project",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ── 포맷터 ── */
function fmtEok(locale: string, won: number) {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(won / 1e8);
}
function fmtPct01(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}
function fmtPctRaw(v: number) {
  return `${v.toFixed(1)}%`;
}
function fmtInt(v: number) {
  return new Intl.NumberFormat("ko-KR").format(Math.round(v));
}
/** 섭동 기준값(base_values) 표기 — 변수별 단위. */
function fmtBaseValue(locale: string, key: string, v: number) {
  if (key === "interest_rate") return `${(v * 100).toFixed(2)}%`;
  if (key === "project_months") return `${Math.round(v)}개월`;
  if (key === "sale_price") return `${fmtInt(v / 10000)}만원/평`;
  return `${fmtEok(locale, v)}억`; // construction_cost, land_cost
}

/* ── 컴포넌트 ── */
export function InvestmentAnalyticsWorkspaceClient({
  locale,
  projectId,
}: {
  locale: Locale;
  projectId: string;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const mode = apiClient.getRuntimeConfig().mode;

  // ★실데이터 구독 — 예전 projectId 미사용·store 미연동을 정정.
  const feasInput = useFeasibilityV2Store((s) => s.input);
  const feasBoundProjectId = useFeasibilityV2Store((s) => s.boundProjectId);
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const design = useProjectContextStore((s) => s.designData);
  const feas = useProjectContextStore((s) => s.feasibilityData);

  // base 조립(반응형) — store 변경 시 요약·게이트가 자동 갱신.
  //   feasBoundProjectId 를 함께 넘겨 '현재 프로젝트에 바인딩된 수지'만 1순위로 신뢰(오염 차단).
  const { base, baseSource, missing } = useMemo(
    () => assembleBase(feasInput, feasBoundProjectId, site, design, feas, projectId),
    [feasInput, feasBoundProjectId, site, design, feas, projectId],
  );

  const [uncertainty, setUncertainty] = useState<Record<string, number>>({ ...DEFAULT_UNCERTAINTY });
  const [simulations, setSimulations] = useState<number | null>(1000);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [workspaceError, setWorkspaceError] = useState("");
  const [mcResult, setMcResult] = useState<MonteCarloResponse | null>(null);
  const [sensResult, setSensResult] = useState<SensitivityResponse | null>(null);

  // ★프로젝트 전환 시 이전 프로젝트의 시뮬 결과(분포·토네이도)·오류를 즉시 비운다.
  //   (미초기화 시 다른 프로젝트로 바꿔도 예전 NPV 분포가 그대로 남아 오표시 — 무목업 위반)
  useEffect(() => {
    setMcResult(null);
    setSensResult(null);
    setWorkspaceError("");
  }, [projectId]);

  // ★인플라이트 가드 — 제출(민감도+몬테카를로, 최대 각 120초) 중 프로젝트를 바꾸면
  //   뒤늦게 도착한 이전 프로젝트 응답이 새 프로젝트 화면에 결과를 덮어써 오염된다.
  //   projectIdRef 로 '지금' 프로젝트를 읽어, 제출 시점과 달라졌으면 결과 반영을 폐기한다.
  const projectIdRef = useRef(projectId);
  useEffect(() => { projectIdRef.current = projectId; }, [projectId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    if (!base) {
      // 무목업: 결측이면 가짜 기본값(예전 300/450) 대신 정직 안내로 유도.
      setWorkspaceError(labels.missingBody);
      return;
    }
    // 이 제출이 어느 프로젝트 대상인지 고정 — 응답 반영 직전마다 현재 프로젝트와 대조(오염 차단).
    const submittedFor = projectId;
    const stillCurrent = () => projectIdRef.current === submittedFor;
    setIsSubmitting(true);
    try {
      // ① 민감도(토네이도) + base_values(5변수 엔진 기준값) 회수.
      const sens = await apiClient.postV2<SensitivityResponse>("/feasibility/sensitivity", {
        body: { base, scenarios: null } as Record<string, unknown>,
        timeoutMs: 120_000,
      });
      if (!stillCurrent()) return;  // 그 사이 프로젝트 전환 → 이전 프로젝트 결과 폐기
      setSensResult(sens);

      // ② 몬테카를로 변수 구성 — 평균=엔진 base_values, 표준편차=평균×불확실성(±%). 기준값 없으면 섭동 제외(정직).
      const bv = sens.base_values ?? {};
      const variables = PERTURB_VARS.map((v): MCVariablePayload | null => {
        const mean = numOf(bv[v.key]);
        if (mean == null || mean <= 0) return null;
        const uncPct = uncertainty[v.key] ?? 0;
        const std = Math.abs(mean) * (uncPct / 100);
        if (!(std > 0)) return null;
        return { name: v.key, mean, std, distribution: "normal" };
      }).filter((v): v is MCVariablePayload => v !== null);

      if (variables.length === 0) {
        setMcResult(null);
        setWorkspaceError(labels.noUncertaintyError);
        return;
      }

      // ③ 몬테카를로(실수지 base 섭동) — net_profit_won 분포.
      const mc = await apiClient.postV2<MonteCarloResponse>("/feasibility/monte-carlo", {
        body: {
          variables,
          n_simulations: simulations ?? 1000,
          seed: 42,
          base,
        } as Record<string, unknown>,
        timeoutMs: 120_000,
      });
      if (!stillCurrent()) return;  // 그 사이 프로젝트 전환 → 이전 프로젝트 결과 폐기
      setMcResult(mc);
    } catch (error) {
      if (stillCurrent()) setWorkspaceError(errText(error));
    } finally {
      // 제출 버튼 상태는 항상 해제(프로젝트 무관 — 인플라이트 완료 시 self-heal).
      setIsSubmitting(false);
    }
  }

  const lossProb = mcResult ? Math.min(1, Math.max(0, 1 - mcResult.probability_positive)) : 0;
  const baseResult = sensResult?.base_result ?? null;

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0" data-project-id={projectId}>
      {/* Hero — 거짓 heroHint('Calls POST /finance/monte-carlo') 정정 */}
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[color-mix(in_srgb,var(--accent-strong)_10%,transparent)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
              {mode === "live" ? "실연동" : "로컬(mock)"}
            </span>
            {projectId ? (
              <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-tertiary)]">
                {labels.projectRef} {projectId.slice(0, 8)}
              </span>
            ) : null}
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">{labels.heroDescription}</h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">{labels.heroHint}</p>
          {/* 경고배너 — 예전 text-[var(--spot)]은 미정의 토큰(침묵 폴백)이라 Operations 워크스페이스 idiom(status-warning)으로 통일. */}
          {workspaceError ? (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[var(--status-warning)]/30 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-5 text-sm leading-7 text-[var(--status-warning)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* base 요약(읽기 전용) 또는 결측 게이트 */}
      {base ? (
        <Card>
          <CardContent className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                {labels.baseSummaryTitle}
              </p>
              <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-[11px] font-semibold text-[var(--text-secondary)]">
                {baseSource === "feasibility-store" ? labels.baseSourceStore : labels.baseSourceContext}
              </span>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <MetricTile label={labels.bDevType} value={strOf(base.development_type) ?? "—"} />
              <MetricTile
                label={labels.bLandArea}
                value={numOf(base.total_land_area_sqm) != null ? `${fmtInt(numOf(base.total_land_area_sqm)!)}㎡` : "—"}
              />
              <MetricTile
                label={labels.bGfa}
                value={numOf(base.total_gfa_sqm) != null ? `${fmtInt(numOf(base.total_gfa_sqm)!)}㎡` : "—"}
              />
              <MetricTile
                label={labels.bSalePrice}
                value={
                  numOf(base.avg_sale_price_per_pyeong) != null
                    ? fmtInt(numOf(base.avg_sale_price_per_pyeong)! / 10000)
                    : "—"
                }
              />
              {numOf(base.total_households) != null ? (
                <MetricTile label={labels.bHouseholds} value={`${fmtInt(numOf(base.total_households)!)}`} />
              ) : null}
              <MetricTile
                label={labels.bMonths}
                value={numOf(base.project_months) != null ? `${Math.round(numOf(base.project_months)!)}개월` : "—"}
              />
              <MetricTile
                label={labels.bDiscount}
                value={numOf(base.discount_rate) != null ? fmtPct01(numOf(base.discount_rate)!) : "—"}
              />
              {numOf(base.official_price_per_sqm) != null ? (
                <MetricTile
                  label={labels.bOfficialPrice}
                  value={fmtInt(numOf(base.official_price_per_sqm)!)}
                />
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-6">
            <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5">
              <p className="text-sm font-bold text-[var(--text-primary)]">{labels.missingTitle}</p>
              <p className="mt-1.5 text-sm leading-7 text-[var(--text-secondary)]">{labels.missingBody}</p>
              {missing.length > 0 ? (
                <p className="mt-2 text-xs text-[var(--text-tertiary)]">
                  {labels.missingFieldsPrefix}: {missing.join(", ")}
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 불확실성 입력 */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{labels.formTitle}</p>
          <p className="mt-2 text-xs leading-6 text-[var(--text-secondary)]">{labels.uncertaintyIntro}</p>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {PERTURB_VARS.map((v) => (
                <label key={v.key} className="grid gap-1">
                  <span className="text-xs font-medium text-[var(--text-secondary)]">
                    {(locale === "en" ? v.en : v.ko)} · ±% ({locale === "en" ? v.unitEn : v.unitKo})
                  </span>
                  <NumberInput
                    allowDecimal
                    value={uncertainty[v.key] ?? 0}
                    onChange={(n) =>
                      setUncertainty((prev) => ({ ...prev, [v.key]: n ?? 0 }))
                    }
                    placeholder="±%"
                    className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                  />
                </label>
              ))}
              <label className="grid gap-1">
                <span className="text-xs font-medium text-[var(--text-secondary)]">{labels.simulationsLabel}</span>
                <NumberInput
                  value={simulations}
                  onChange={(n) => setSimulations(n)}
                  placeholder="1000"
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
              </label>
            </div>
            <Button type="submit" disabled={isSubmitting || !base}>
              {isSubmitting ? `${labels.running}...` : labels.submitAction}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* 결과 */}
      {mcResult ? (
        <>
          {/* 리스크 요약 — 손실확률 링 */}
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{labels.riskTitle}</p>
              <div className="mt-4 flex flex-wrap items-center gap-6">
                <div className="relative flex h-28 w-28 items-center justify-center">
                  <svg className="h-28 w-28 -rotate-90" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="42" fill="none" stroke="var(--line)" strokeWidth="8" />
                    <circle
                      cx="50"
                      cy="50"
                      r="42"
                      fill="none"
                      stroke="var(--status-error)"
                      strokeWidth="8"
                      strokeDasharray={`${lossProb * 263.9} 263.9`}
                      strokeLinecap="round"
                    />
                  </svg>
                  <span className="absolute text-xl font-bold text-[var(--text-primary)]">
                    {fmtPct01(lossProb)}
                  </span>
                </div>
                <div className="grid flex-1 gap-4 md:grid-cols-3">
                  <MetricTile label={labels.lossProbLabel} value={fmtPct01(lossProb)} />
                  <MetricTile
                    label={labels.positiveProbLabel}
                    value={fmtPct01(mcResult.probability_positive)}
                  />
                  <MetricTile
                    label={labels.downsideLabel}
                    value={`${fmtEok(locale, mcResult.p5)}억`}
                    tone={mcResult.p5 < 0 ? "negative" : "default"}
                  />
                  <MetricTile label={labels.nSimLabel} value={fmtInt(mcResult.n_simulations)} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 순이익 분포 + 히스토그램 + 정직표기 */}
          <Card>
            <CardContent className="p-6">
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{labels.distTitle}</p>
              <div className="mt-4 grid gap-4 md:grid-cols-3">
                <MetricTile
                  label={labels.meanLabel}
                  value={`${fmtEok(locale, mcResult.mean)}억`}
                  tone={mcResult.mean < 0 ? "negative" : "default"}
                />
                <MetricTile label={labels.stdLabel} value={`${fmtEok(locale, mcResult.std)}억`} />
                <MetricTile label={labels.p50Label} value={`${fmtEok(locale, mcResult.p50)}억`} />
                <MetricTile
                  label={labels.downsideLabel}
                  value={`${fmtEok(locale, mcResult.p5)}억`}
                  tone={mcResult.p5 < 0 ? "negative" : "default"}
                />
                <MetricTile label={labels.p95Label} value={`${fmtEok(locale, mcResult.p95)}억`} />
              </div>

              {mcResult.histogram?.length > 0 ? (
                <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{labels.histTitle}</p>
                  <div className="mt-3 space-y-2">
                    {(() => {
                      const maxCount = Math.max(...mcResult.histogram.map((h) => h.count), 0);
                      return mcResult.histogram.map((bin, i) => {
                        const pct = maxCount > 0 ? (bin.count / maxCount) * 100 : 0;
                        // 손실(음수) 구간은 빨강, 흑자 구간은 강조색, 걸친 구간은 앰버(공용 상태토큰).
                        const barColor =
                          bin.bin_end <= 0
                            ? "var(--status-error)"
                            : bin.bin_start >= 0
                              ? "var(--accent-strong)"
                              : "var(--status-warning)";
                        return (
                          <div key={`bin-${i}`} className="flex items-center gap-3">
                            <span className="w-32 shrink-0 text-[10px] text-[var(--text-tertiary)]">
                              {fmtEok(locale, bin.bin_start)} ~ {fmtEok(locale, bin.bin_end)}억
                            </span>
                            <div className="h-3 flex-1 rounded-full bg-[var(--line)]">
                              <div
                                className="h-3 rounded-full"
                                style={{ width: `${pct}%`, backgroundColor: barColor }}
                              />
                            </div>
                            <span className="w-12 text-right text-[10px] font-semibold text-[var(--text-secondary)]">
                              {bin.count}
                            </span>
                          </div>
                        );
                      });
                    })()}
                  </div>
                </div>
              ) : null}

              {/* 정직표기 — CV(변동계수)≠수렴, converged(수렴), SE비율, 대상지표/출처/제약 */}
              <div className="mt-4 rounded-[var(--radius-xl)] border border-[var(--line)] p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{labels.honestTitle}</p>
                <div className="mt-3 grid gap-x-6 gap-y-2 text-xs md:grid-cols-2">
                  <HonestRow
                    label={labels.cvLabel}
                    value={`${mcResult.convergence_ratio.toFixed(3)} — ${labels.cvNote}`}
                  />
                  <HonestRow
                    label={labels.convergedLabel}
                    value={mcResult.converged ? labels.convergedYes : labels.convergedNo}
                  />
                  {mcResult.standard_error_ratio != null ? (
                    <HonestRow label={labels.seLabel} value={mcResult.standard_error_ratio.toFixed(5)} />
                  ) : null}
                  <HonestRow label={labels.targetMetricLabel} value={mcResult.target_metric} />
                  <HonestRow label={labels.calcSourceLabel} value={mcResult.calc_source} />
                  {mcResult.note ? <HonestRow label={labels.noteLabel} value={mcResult.note} /> : null}
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}

      {/* 기준 수지(base_result) — 민감도 응답에서 회수 */}
      {baseResult ? (
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{labels.baseResultTitle}</p>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              {numOf(baseResult.net_profit_won) != null ? (
                <MetricTile
                  label={labels.netProfitLabel}
                  value={`${fmtEok(locale, baseResult.net_profit_won!)}억`}
                  tone={baseResult.net_profit_won! < 0 ? "negative" : "default"}
                />
              ) : null}
              {numOf(baseResult.profit_rate_pct) != null ? (
                <MetricTile label={labels.profitRateLabel} value={fmtPctRaw(baseResult.profit_rate_pct!)} />
              ) : null}
              {numOf(baseResult.roi_pct) != null ? (
                <MetricTile label={labels.roiLabel} value={fmtPctRaw(baseResult.roi_pct!)} />
              ) : null}
              {numOf(baseResult.npv_won) != null ? (
                <MetricTile label={labels.npvLabel} value={`${fmtEok(locale, baseResult.npv_won!)}억`} />
              ) : null}
              {strOf(baseResult.grade) != null ? (
                <MetricTile label={labels.gradeLabel} value={strOf(baseResult.grade)!} />
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* 민감도 토네이도 + 섭동 기준값 */}
      {sensResult && sensResult.tornado.length > 0 ? (
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{labels.tornadoTitle}</p>
            <p className="mt-1.5 text-xs leading-6 text-[var(--text-secondary)]">{labels.tornadoNote}</p>
            <div className="mt-4 space-y-3">
              {(() => {
                const maxSpread = Math.max(...sensResult.tornado.map((t) => t.spread), 0);
                const center =
                  numOf(baseResult?.profit_rate_pct) ??
                  (sensResult.tornado.length > 0
                    ? (sensResult.tornado[0].low_profit + sensResult.tornado[0].high_profit) / 2
                    : 0);
                return sensResult.tornado.map((t, i) => {
                  const lowPct = maxSpread > 0 ? (Math.abs(center - t.low_profit) / maxSpread) * 50 : 0;
                  const highPct = maxSpread > 0 ? (Math.abs(t.high_profit - center) / maxSpread) * 50 : 0;
                  return (
                    <div key={`tornado-${i}`} className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-[var(--text-primary)]">{t.name}</span>
                        <span className="text-xs text-[var(--text-tertiary)]">
                          {labels.profitRateLabel} ±{t.spread.toFixed(1)}%p
                        </span>
                      </div>
                      <div className="mt-2 flex items-center gap-1">
                        <div className="flex flex-1 justify-end">
                          {/* 하방(손실측) 막대 — 공용 상태토큰(60% 혼합). */}
                          <div
                            className="h-4 rounded-l-full"
                            style={{
                              width: `${lowPct}%`,
                              backgroundColor: "color-mix(in srgb, var(--status-error) 60%, transparent)",
                            }}
                          />
                        </div>
                        <div className="h-6 w-px bg-[var(--text-tertiary)]" />
                        <div className="flex-1">
                          {/* 상방(수익측) 막대 — 공용 상태토큰(60% 혼합). */}
                          <div
                            className="h-4 rounded-r-full"
                            style={{
                              width: `${highPct}%`,
                              backgroundColor: "color-mix(in srgb, var(--status-success) 60%, transparent)",
                            }}
                          />
                        </div>
                      </div>
                      <div className="mt-1 flex justify-between text-[10px] text-[var(--text-tertiary)]">
                        <span>{fmtPctRaw(t.low_profit)}</span>
                        <span>{fmtPctRaw(center)}</span>
                        <span>{fmtPctRaw(t.high_profit)}</span>
                      </div>
                    </div>
                  );
                });
              })()}
            </div>

            {/* 섭동 기준값(base_values) — 엔진 산출 출처 정직 표기 */}
            {sensResult.base_values && Object.keys(sensResult.base_values).length > 0 ? (
              <div className="mt-4 rounded-[var(--radius-xl)] border border-[var(--line)] p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                  {labels.baseValuesTitle}
                </p>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  {PERTURB_VARS.filter((v) => numOf(sensResult.base_values[v.key]) != null).map((v) => (
                    <MetricTile
                      key={`bv-${v.key}`}
                      label={locale === "en" ? v.en : v.ko}
                      value={fmtBaseValue(locale, v.key, sensResult.base_values[v.key])}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {/* 미실행 안내 */}
      {!mcResult && !sensResult ? (
        <Card>
          <CardContent className="p-6">
            <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </section>
  );
}

/* ── MetricTile ── */
function MetricTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "negative";
}) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">{label}</p>
      <p
        className={`mt-2 text-sm font-semibold ${
          tone === "negative" ? "text-[var(--status-error)]" : "text-[var(--text-primary)]"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

/* ── 정직표기 한 줄 ── */
function HonestRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[var(--text-tertiary)]">{label}</span>
      <span className="text-right font-medium text-[var(--text-secondary)]">{value}</span>
    </div>
  );
}
