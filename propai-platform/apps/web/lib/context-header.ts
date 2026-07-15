// 생성허브 공용 대상 컨텍스트 헤더 — 표시 데이터 파생 유틸(순수 함수·무목업).
//
// 왜 필요한가(쉬운 설명):
// 후보지진단서·사업성검토서·시장분양리포트·인허가체크리스트·AI설계검토서·건축개요CAD 등
// "생성허브 6산출물"은 각기 다른 셸에 흩어져 있어, 사용자가 "이 산출물이 '어느 프로젝트·어느
// 토지'를 대상으로 분석한 것인지" 화면에서 알 수 없었다. 이 유틸은 프로젝트 컨텍스트 스토어
// (useProjectContextStore)의 단일 진실원천(SSOT)에서 표시용 값(프로젝트명·주소·PNU·용도지역·
// 대지면적·다필지 통합 여부)을 뽑아 ContextHeader 공용 컴포넌트가 6페이지 어디서나 동일하게
// 상시 표시하도록 한다(한 곳을 고치면 6페이지가 따라옴).
//
// ★기존 헬퍼 재사용(그린필드 재발명 금지):
//   - effectiveLandAreaSqm(lib/site-area): 다필지면 통합면적 우선(경합 면역).
//   - resolveDominantZone(lib/zoning-ssot): 통합 dominant_zone 우선 → 단일 zoneCode 폴백.
//   - normalizeZoning(lib/kr-building-regulations): 용도지역 라벨 정규화(코드/변형→정식 한글).
//
// ★무목업: 컨텍스트가 없으면 값은 null(가짜 생성 금지). 소비 컴포넌트가 "대상 미선택"으로
//   정직하게 안내한다.

import type {
  SiteAnalysisData,
  ProjectContextState,
} from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { resolveDominantZone } from "@/lib/zoning-ssot";
import { normalizeZoning } from "@/lib/kr-building-regulations";
import type { PipelineStep } from "@/components/common/AnalysisPipelineStepbar";

/** ContextHeader가 읽는 프로젝트 컨텍스트 입력(스토어 필드의 부분 집합). */
export interface ContextHeaderInput {
  projectId: string | null;
  projectName: string;
  siteAnalysis: SiteAnalysisData | null;
  /** 설계 산출(designData) — 부지분석에 용도지역이 없을 때 설계 폼이 쓴 용도지역으로 폴백하기 위한
   *  최소 입력(옵셔널·하위호환). 미전달이면 종전과 동일하게 siteAnalysis만으로 파생(무회귀). */
  designData?: { zoneCode?: string | null } | null;
}

/** ContextHeader 표시용 파생 결과 — 미확보 값은 전부 null(무목업). */
export interface ContextHeaderData {
  /** 대상 컨텍스트가 하나라도 있는가(프로젝트 선택 또는 부지 주소 확보). false면 "대상 미선택". */
  hasContext: boolean;
  /** 프로젝트명(빈 문자열이면 null). */
  projectName: string | null;
  /** 대상 부지 주소(없으면 null). */
  address: string | null;
  /** 필지고유번호(PNU) — 없으면 null. */
  pnu: string | null;
  /** 용도지역 표시 라벨(정규화된 정식 한글, 정규화 실패 시 원문 코드, 미확보 시 null). */
  zoneLabel: string | null;
  /** 용도지역 출처: "site"=부지분석 확정, "design"=설계 폼 직접 입력(폴백), null=미확보. */
  zoneSource: "site" | "design" | null;
  /** 유효 대지면적(㎡·다필지면 통합면적) — 미확보 시 null. */
  landAreaSqm: number | null;
  /** 유효 필지 수(다필지 판정용). 단일/미확보면 1 또는 null. */
  parcelCount: number | null;
  /** 다필지 통합 여부(parcelCount >= 2). */
  isMultiParcel: boolean;
}

/** 문자열 정규화(공백 trim, 빈값이면 null). */
function str(v: string | null | undefined): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

/**
 * 용도지역 코드/라벨 → 표시용 정식 한글 라벨.
 * normalizeZoning으로 정규화(예: "2R"·"제2종일반주거"→"제2종일반주거지역"), 실패하면 원문 그대로
 * 표시(미상 코드를 버리지 않고 정직하게 노출). 미확보 시 null.
 */
export function zoneDisplayLabel(zoneCode: string | null | undefined): string | null {
  const raw = str(zoneCode);
  if (!raw) return null;
  return normalizeZoning(raw) ?? raw;
}

/**
 * 프로젝트 컨텍스트(SSOT)에서 ContextHeader 표시 데이터를 파생한다(순수 함수).
 *
 * - 대지면적: effectiveLandAreaSqm(다필지=통합 우선)로 경합 면역 읽기.
 * - 용도지역: resolveDominantZone(통합 dominant > 단일 zoneCode) 후 표시 라벨 정규화.
 * - hasContext: 프로젝트 선택 또는 주소 확보 중 하나라도 있으면 true(무목업 안내 분기).
 */
export function deriveContextHeaderData(ctx: ContextHeaderInput): ContextHeaderData {
  const sa = ctx.siteAnalysis;
  const address = str(sa?.address);
  const pnu = str(sa?.pnu);
  const projectName = str(ctx.projectName);
  const parcelCount =
    typeof sa?.parcelCount === "number" && sa.parcelCount > 0
      ? sa.parcelCount
      : null;
  const isMultiParcel = (parcelCount ?? 1) > 1;
  // 용도지역: 부지분석(SSOT) 확정 우선 → 없으면 설계 폼이 쓴 용도지역(designData.zoneCode)으로 폴백.
  //   부지분석에 용도지역이 없고 사용자가 설계에서 직접 입력한 경우에도 "용도지역 —"이 아니라 실제
  //   값을 "직접 입력" 배지와 함께 보여 준다(무날조 — 폴백값이 없으면 그대로 null).
  const siteZoneLabel = zoneDisplayLabel(resolveDominantZone(sa));
  const designZoneLabel = zoneDisplayLabel(ctx.designData?.zoneCode);
  const zoneLabel = siteZoneLabel ?? designZoneLabel;
  const zoneSource: ContextHeaderData["zoneSource"] = siteZoneLabel
    ? "site"
    : designZoneLabel
      ? "design"
      : null;
  const landAreaSqm = effectiveLandAreaSqm(sa);
  const hasContext = !!(ctx.projectId || address || projectName);

  return {
    hasContext,
    projectName,
    address,
    pnu,
    zoneLabel,
    zoneSource,
    landAreaSqm,
    parcelCount,
    isMultiParcel,
  };
}

/**
 * 후보지진단(precheck) 등 부지분석 SSOT 기반 산출물의 분석 3단계 파생(순수 함수·무목업).
 *
 * ★정직 원칙: 각 단계는 store에 실제로 적재된 필드로만 판정한다(추측/날조 금지).
 *   - 수집(collect): 주소+유효면적 확보(hasSiteData와 동형 판정) → done, 부분 확보(주소만) →
 *     running(수집 진행 중으로 정직 표기), 전무 → idle.
 *   - 검증(verify): 근거 트레이스(evidence) 또는 법령 원문 링크(legalRefs)가 store에 적재됨
 *     (build_evidence_block 산출) → done, 미적재 → idle(검증 미실행을 done으로 위장하지 않음).
 *   - 전문가 LLM(expert): 특이부지 게이트(specialParcel) 또는 종상향 시나리오(upzoningScenarios)
 *     — 둘 다 LLM/규칙엔진 해석 산출물 — 존재 시 done, 미확보 시 idle.
 *
 * siteAnalysis가 아예 없으면 3단계 전부 idle(수집 전 상태 — 정직).
 */
export function deriveSitePipelineSteps(
  sa: SiteAnalysisData | null | undefined,
): PipelineStep[] {
  if (!sa) {
    return [
      { id: "collect", status: "idle" },
      { id: "verify", status: "idle" },
      { id: "expert", status: "idle" },
    ];
  }

  const hasArea = typeof effectiveLandAreaSqm(sa) === "number" && (effectiveLandAreaSqm(sa) ?? 0) > 0;
  const hasAddress = !!str(sa.address);
  const collectStatus: PipelineStep["status"] = hasAddress && hasArea
    ? "done"
    : hasAddress
      ? "running"
      : "idle";

  const hasEvidence = (sa.evidence?.length ?? 0) > 0 || (sa.legalRefs?.length ?? 0) > 0;

  const hasExpertOutput = !!sa.specialParcel || (sa.upzoningScenarios?.length ?? 0) > 0;

  return [
    {
      id: "collect",
      status: collectStatus,
      sourceLabel: hasAddress ? "부지분석(주소·면적·용도지역)" : null,
    },
    {
      id: "verify",
      status: hasEvidence ? "done" : "idle",
      sourceLabel: hasEvidence ? "근거 트레이스·법령 원문 교차검증" : null,
    },
    {
      id: "expert",
      status: hasExpertOutput ? "done" : "idle",
      sourceLabel: hasExpertOutput ? "특이부지 게이트·종상향 해석" : null,
    },
  ];
}

/**
 * 사업성검토(투자수익성) SSOT 기반 산출물의 분석 3단계 파생(순수 함수·무목업).
 *
 * ★정직 원칙: FeasibilityData에는 교차검증 트레이스 필드가 없다(store에 verify 전용 필드 부재
 *   확인 완료) — 있는 것처럼 위장하지 않고 verify는 항상 idle(미상)로 정직 표기한다. 억지로
 *   done을 만들지 않는 것이 "정직하게 idle" 원칙이다.
 *   - 수집(collect): 매출/원가(totalRevenueWon·totalCostWon) 확보 → done, 둘 중 하나만 → running,
 *     전무 → idle.
 *   - 검증(verify): 항상 idle(교차검증 트레이스 미보유 — 날조 금지).
 *   - 전문가 LLM(expert): grade(등급 산출) 확보 → done, 미확보 → idle.
 */
export function deriveFeasibilityPipelineSteps(
  fd: ProjectContextState["feasibilityData"] | null | undefined,
): PipelineStep[] {
  if (!fd) {
    return [
      { id: "collect", status: "idle" },
      { id: "verify", status: "idle" },
      { id: "expert", status: "idle" },
    ];
  }

  const hasRevenue = typeof fd.totalRevenueWon === "number" && fd.totalRevenueWon > 0;
  const hasCost = typeof fd.totalCostWon === "number" && fd.totalCostWon > 0;
  const collectStatus: PipelineStep["status"] = hasRevenue && hasCost
    ? "done"
    : hasRevenue || hasCost
      ? "running"
      : "idle";

  const hasGrade = !!str(fd.grade);

  return [
    {
      id: "collect",
      status: collectStatus,
      sourceLabel: collectStatus !== "idle" ? "수지 매출·원가(사업성 계산)" : null,
    },
    {
      // 교차검증 트레이스가 FeasibilityData에 없어 정직하게 idle 고정(날조 금지).
      id: "verify",
      status: "idle",
    },
    {
      id: "expert",
      status: hasGrade ? "done" : "idle",
      sourceLabel: hasGrade ? `사업성 등급 산출(${fd.grade})` : null,
    },
  ];
}

/**
 * 시장분양리포트(MarketInsightsWorkspaceClient) 컴포넌트 로컬 상태 기반 분석 3단계 파생(순수 함수·무목업).
 *
 * ★이 산출물의 진행 상태는 useProjectContextStore가 아니라 컴포넌트 로컬 state(report·genState·
 *   useLlm)에 있다 — 페이지 셸(서버 컴포넌트)까지 억지로 threading하지 않고, 실제 상태를 쥔
 *   컴포넌트 내부에서 이 함수를 직접 호출해 ContextHeader에 pipeline prop으로 넘긴다.
 * ★정직 원칙: 교차검증 트레이스 필드가 이 컴포넌트 응답에 없어 verify는 항상 idle 고정(날조 금지).
 *   - 수집(collect): 생성 중(genState==="report") → running, report 확보 → done, 전무 → idle.
 *   - 검증(verify): 항상 idle(교차검증 트레이스 미보유).
 *   - 전문가 LLM(expert): useLlm 켜짐 + report.narrative 확보 → done, useLlm 꺼짐(규칙 기반만) →
 *     idle(정직 — LLM 미실행을 done으로 위장하지 않음), report 없으면 idle.
 */
export function deriveMarketPipelineSteps(params: {
  genState: string;
  report: { narrative?: unknown } | null | undefined;
  useLlm: boolean;
}): PipelineStep[] {
  const { genState, report, useLlm } = params;
  const collectStatus: PipelineStep["status"] =
    genState === "report" ? "running" : report ? "done" : "idle";

  const hasNarrative = !!report && report.narrative != null;
  const expertStatus: PipelineStep["status"] = hasNarrative && useLlm ? "done" : "idle";

  return [
    {
      id: "collect",
      status: collectStatus,
      sourceLabel: collectStatus !== "idle" ? "실거래·시세 데이터(VWorld·MOLIT)" : null,
    },
    { id: "verify", status: "idle" },
    {
      id: "expert",
      status: expertStatus,
      sourceLabel: expertStatus === "done" ? "전문가 LLM 시장해설(narrative)" : null,
      honestBadge: hasNarrative && !useLlm ? "규칙 기반(LLM 미실행)" : null,
    },
  ];
}
