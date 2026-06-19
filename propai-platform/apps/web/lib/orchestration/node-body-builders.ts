// 분석 오케스트레이션 — 노드별 bodyBuilder(SSOT 슬롯 → 백엔드 평면 body 매핑) [B6-1]
//
// 쉬운 설명:
// 각 분석 노드는 백엔드 엔드포인트를 부를 때 "평평한 필드"(예: address, total_gfa_sqm)를
// top-level로 요구한다. 그런데 예전 useNodeRunner는 모든 노드를 똑같이
// { builder, context } 모양으로 보내서, 어떤 백엔드도 그 모양을 이해하지 못했다
// (미지의 키는 Pydantic이 그냥 무시 → 7개 노드 HTTP 422, design은 빈/기본 결과).
//
// 이 모듈은 노드별로 "상류 SSOT 슬롯 → 백엔드가 실제로 받는 평면 필드"를 정확히 매핑한다.
// 순수 함수만 모았다(React·store 인스턴스·apiClient 의존 0 — 테스트가 쉽다).
//
// 원칙(무목업·정직):
//  - 필수(★)필드를 SSOT에서 못 채우면 임의값을 날조하지 않고 missing[]에 넣어 호출을 막는다
//    (호출측이 needs-input으로 정직 고지). 0 강제 금지.
//  - 면적은 반드시 effectiveLandAreaSqm(통합면적 우선)으로 읽어 다필지 일관성을 지킨다.

import { effectiveLandAreaSqm } from "@/lib/site-area";
import type {
  SiteAnalysisData,
  DesignData,
  CostData,
  FeasibilityData,
} from "@/store/useProjectContextStore";
import type { NodeId } from "./types";

/**
 * useNodeRunner가 ready 슬롯에서 모은 상류 컨텍스트.
 * 키는 store 슬롯명과 동일(siteAnalysis·designData·costData·feasibilityData …).
 * 각 슬롯은 미확보면 부재(undefined) — 무목업: 없으면 missing 처리.
 */
export interface NodeBodyContext {
  siteAnalysis?: SiteAnalysisData | null;
  designData?: DesignData | null;
  costData?: CostData | null;
  feasibilityData?: FeasibilityData | null;
  // esg/compliance는 현재 body 매핑에 사용되지 않으나, 향후 확장·타입 호환을 위해 허용(옵셔널).
  esgData?: Record<string, unknown> | null;
  complianceData?: Record<string, unknown> | null;
}

/** buildNodeBody 결과 — body(전송 페이로드) + missing(못 채운 필수필드 키 목록). */
export interface NodeBodyResult {
  body: Record<string, unknown>;
  /** 필수(★)필드 중 SSOT에서 못 채운 키 목록. 비어있지 않으면 호출 금지(needs-input). */
  missing: string[];
}

/** feasibility 기본 개발유형 — 백엔드가 명시 문서화한 표준 가정(일반분양).
 *  근거: apps/api/app/routers/v2_feasibility.py:578 "일반분양(M06) 표준 가정",
 *        permit_validator.py:47 DEVELOPMENT_TYPE_NAMES["M06"]="일반분양".
 *  ★무목업: recommend(상류 추천)가 store 슬롯에 개발유형을 stamp하지 않으므로(레지스트리
 *  recommend.ssotOutputs=[] — 표시·선택지 전용), 안전한 백엔드 표준 기본값을 사용한다.
 *  임의 코드를 날조하지 않고, 백엔드가 문서화한 기본 development_type만 채택한다. */
const DEFAULT_DEVELOPMENT_TYPE = "M06";

/** 문자열 비어있지 않으면 그대로, 아니면 null. */
function nonEmptyStr(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

/** 0보다 큰 유한수면 그대로, 아니면 null(0 강제 금지·gt0 백엔드 제약 대응). */
function positiveNum(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? v : null;
}

/** 양수 정수면 그대로, 아니면 null(층수 등). */
function positiveInt(v: unknown): number | null {
  const n = positiveNum(v);
  return n == null ? null : Math.round(n);
}

/**
 * zone_code가 백엔드에 안전한 "영문/숫자 코드"인지 판정.
 *
 * 왜 필요한가(쉬운 설명): design 백엔드의 AutoDesignEngine은 zone_code를 "2R" 같은
 * 영문코드로 받는다. 한글 용도지역명("제2종일반주거지역")을 넣으면 매핑이 어긋나
 * 잘못된 법정한도가 적용되는 함정이 있다(특이부지 감지 메모와 동일 위험).
 * 따라서 한글이 섞이면 zone_code를 생략하고 백엔드 기본값("2R")에 맡긴다.
 *
 * 허용: 영문 대문자/숫자/하이픈만으로 이뤄진 짧은 토큰(예: "2R", "3R", "C2", "1R").
 */
function safeZoneCode(v: unknown): string | null {
  const s = nonEmptyStr(v);
  if (!s) return null;
  // 한글이 하나라도 있으면 코드가 아님 → 생략(함정 회피).
  if (/[가-힣]/.test(s)) return null;
  // 영문 대문자·숫자·하이픈으로만 구성된 짧은 코드만 허용.
  return /^[A-Z0-9-]{1,6}$/.test(s) ? s : null;
}

/**
 * 노드별 백엔드 평면 body를 구성한다(SSOT 슬롯 → 백엔드 필드).
 *
 * @param nodeId    실행 노드 식별자.
 * @param ctx       useNodeRunner가 ready 슬롯에서 모은 상류 컨텍스트(슬롯명 키).
 * @param projectId 데이터 SSOT projectId(설계 등 URL 식별자 노드 참고용 — body엔 미포함).
 * @returns body(전송 페이로드)와 missing(못 채운 필수필드). missing이 비어있지 않으면 호출 금지.
 */
export function buildNodeBody(
  nodeId: NodeId,
  ctx: NodeBodyContext,
  projectId: string | null,
): NodeBodyResult {
  const site = ctx.siteAnalysis ?? null;
  const design = ctx.designData ?? null;
  const cost = ctx.costData ?? null;
  const feas = ctx.feasibilityData ?? null;

  const address = nonEmptyStr(site?.address);
  const pnu = nonEmptyStr(site?.pnu);
  // ★면적: 통합면적 우선(다필지 일관성). 단일필지면 landAreaSqm.
  const landAreaSqm = positiveNum(effectiveLandAreaSqm(site));

  const body: Record<string, unknown> = {};
  const missing: string[] = [];

  switch (nodeId) {
    case "land":
    case "legal": {
      // {address★, pnu?} — 주소가 사실근거 루트(없으면 백엔드 400/422).
      if (address) body.address = address;
      else missing.push("address");
      if (pnu) body.pnu = pnu;
      break;
    }

    case "recommend": {
      // {addresses★: string[]} — 단일 주소를 배열로 래핑(다필지 통합 추천 엔드포인트).
      if (address) body.addresses = [address];
      else missing.push("addresses");
      break;
    }

    case "design": {
      // URL {id}=projectId(호출측 치환) + body {land_area_sqm?, zone_code?, floor_count?}.
      // 백엔드(BimGenerateRequest): land_area_sqm는 gt0 옵셔널, zone_code 기본 "2R".
      // 필수 강제 없음 — 면적 미확보면 백엔드가 합리적 기본 매스로 폴백(무회귀: 빈결과 방지엔
      // 면적 주입이 핵심이므로 가능하면 채운다). projectId는 URL용이라 body 미포함.
      void projectId; // body엔 사용 안 함(URL 식별자는 호출측이 path 치환).
      if (landAreaSqm != null) body.land_area_sqm = landAreaSqm;
      // ★zone_code는 영문코드일 때만(한글 용도지역명 함정 회피 — 없으면 백엔드 자동).
      const zc = safeZoneCode(site?.zoneCode);
      if (zc) body.zone_code = zc;
      const floor = positiveInt(design?.floorCount);
      if (floor != null) body.floor_count = floor;
      break;
    }

    case "sales": {
      // {address★, pnu?} (+JWT — apiClient가 Authorization 자동첨부).
      // 주의: 백엔드 market/report는 lawd_cd 결정에 pnu/bcode가 필요하다(없으면 400).
      // pnu가 있으면 함께 보내 lawd_cd 도출을 돕는다.
      if (address) body.address = address;
      else missing.push("address");
      if (pnu) body.pnu = pnu;
      break;
    }

    case "qto": {
      // {total_gfa_sqm★(gt0), floor_count_above?, building_type?}.
      const gfa = positiveNum(design?.totalGfaSqm);
      if (gfa != null) body.total_gfa_sqm = gfa;
      else missing.push("total_gfa_sqm");
      const floorAbove = positiveInt(design?.floorCount);
      if (floorAbove != null) body.floor_count_above = floorAbove;
      const bt = nonEmptyStr(design?.buildingType);
      if (bt) body.building_type = bt;
      break;
    }

    case "feasibility": {
      // {development_type★, total_land_area_sqm★(gt0), total_gfa_sqm★(gt0),
      //  building_type?, avg_sale_price_per_pyeong?, official_price_per_sqm?}.
      // ★development_type: 상류 추천이 store에 stamp하지 않으므로(recommend.ssotOutputs=[])
      //  백엔드 표준 기본값(M06=일반분양)을 사용. 백엔드가 허용·문서화한 기본이라 무목업 위배 아님.
      body.development_type = DEFAULT_DEVELOPMENT_TYPE;
      if (landAreaSqm != null) body.total_land_area_sqm = landAreaSqm;
      else missing.push("total_land_area_sqm");
      const gfa = positiveNum(design?.totalGfaSqm);
      if (gfa != null) body.total_gfa_sqm = gfa;
      else missing.push("total_gfa_sqm");
      const bt = nonEmptyStr(design?.buildingType);
      if (bt) body.building_type = bt;
      break;
    }

    case "finance": {
      // {total_project_cost_won★, construction_cost_won?}.
      const totalCost = positiveNum(feas?.totalCostWon);
      if (totalCost != null) body.total_project_cost_won = totalCost;
      else missing.push("total_project_cost_won");
      const constr = positiveNum(cost?.totalConstructionCostWon);
      if (constr != null) body.construction_cost_won = constr;
      break;
    }

    case "audit":
    default: {
      // audit는 available:false라 호출 경로에 도달하지 않는다(호출측 가드). body 미구성.
      break;
    }
  }

  return { body, missing };
}
