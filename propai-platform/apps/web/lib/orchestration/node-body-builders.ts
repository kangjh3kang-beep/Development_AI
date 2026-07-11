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
import { resolveFarPct, resolveBcrPct } from "@/lib/zoning-ssot";
import { PYEONG_SQM } from "@/lib/formatters";
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
 *  ★무목업: 상류 추천(recommend)이 feasibilityData.developmentType을 환류하면 그 값을 우선 채택하고,
 *  미환류(추천 미실행·게이트 차단으로 ranked 비음)면 이 백엔드 표준 기본값으로 폴백한다(무회귀).
 *  임의 코드를 날조하지 않고, 백엔드가 문서화한 기본 development_type만 폴백으로 채택한다. */
const DEFAULT_DEVELOPMENT_TYPE = "M06";

/** 추천 개발방식 코드가 백엔드가 수용하는 형식(M01~M15)인지 판정. 아니면 null(폴백 유도).
 *  근거(라이브 검증·permit_validator.py DEVELOPMENT_TYPE_NAMES): M 뒤 2자리 숫자(01~15). */
function safeDevelopmentType(v: unknown): string | null {
  const s = nonEmptyStr(v);
  if (!s) return null;
  return /^M(0[1-9]|1[0-5])$/.test(s) ? s : null;
}

/**
 * 건물유형별 표준 전용률(연면적 대비 분양/전용면적 비율, 0~1).
 *
 * 왜 필요한가(쉬운 설명): 곱하는 단가(trade.아파트.per_pyeong.avg)는 "전용면적 기준 평당가"인데,
 * 연면적(GFA)에는 복도·계단·주차 등 공용부가 포함돼 전용면적보다 크다. 연면적 그대로 곱하면
 * 분양수입이 부풀려진다. 그래서 연면적에 전용률을 곱해 "전용면적"으로 환산한 뒤 전용단가와 곱한다.
 *
 * ★무목업(정직 표기): 아래 값은 임의 가정이 아니라 이 플랫폼 백엔드가 이미 쓰는 표준 전용률이다
 *  (정본: apps/api/app/services/feasibility/unit_standards.py SELLABLE_EFFICIENCY_BY_BUILDING_TYPE,
 *   design_v61.py:347 efficiency_pct 기본 75.0). 백엔드 sellable_area = GFA × 전용률 산식과 동일.
 *  설계(design)가 실제 전용률(efficiencyPct)을 환류하면 그 실값을 우선 쓰고(아래 sale/feasibility),
 *  미확보일 때만 이 표준값으로 폴백한다 — 추정임을 정직히 표기.
 *
 * ★(G4→P2 수렴 완료) FE/BE 계약: 백엔드 정본은 apps/api/app/services/feasibility/unit_standards.py의
 *  SELLABLE_EFFICIENCY_BY_BUILDING_TYPE/get_sellable_efficiency로 수렴됐고(P2, project_pipeline은
 *  import 소비), FE는 교차언어라 이 미러를 유지한다(자동 동기화 없음). 한쪽 변경 시 반대쪽 상수와 두 계약 테스트
 *  (node-body-builders.test.ts의 "G4 계약" describe·apps/api/tests/test_sellable_efficiency_contract.py)를
 *  함께 갱신할 것. export는 그 계약 테스트가 실값을 직접 대조하기 위함(런타임 동작 불변).
 */
export const SELLABLE_EFFICIENCY_BY_TYPE: Record<string, number> = {
  아파트: 0.75,
  다세대주택: 0.78,
  오피스텔: 0.7,
  공동주택: 0.76,
  근린생활시설: 0.7,
};
/** 유형 미상 시 표준 전용률(백엔드 unit_standards.DEFAULT_SELLABLE_EFFICIENCY 0.75와 동일. G4 계약 대상). */
export const DEFAULT_SELLABLE_EFFICIENCY = 0.75;

/**
 * 연면적→전용면적 환산에 쓸 전용률(0~1)을 결정한다.
 *  1순위: 설계(design)가 환류한 실제 전용률(efficiencyPct, %). 백엔드 sellable_efficiency_pct 출처.
 *  2순위: 건물유형별 표준 전용률(백엔드 동일 테이블). 유형 미상이면 기본 0.75.
 * 항상 0초과 1이하 값을 반환한다(분양수입 0 방지·과대 방지).
 */
function resolveSellableEfficiency(
  efficiencyPct: unknown,
  buildingType: unknown,
): number {
  const pct = positiveNum(efficiencyPct);
  // 설계 실값(전용률 %)이 합리적 범위(0~100)면 소수비율로 환산해 우선 채택.
  if (pct != null && pct <= 100) return pct / 100;
  const bt = nonEmptyStr(buildingType);
  if (bt && SELLABLE_EFFICIENCY_BY_TYPE[bt] != null) {
    return SELLABLE_EFFICIENCY_BY_TYPE[bt];
  }
  return DEFAULT_SELLABLE_EFFICIENCY;
}

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
      // {address★, pnu? 또는 bcode?} (+JWT — apiClient가 Authorization 자동첨부).
      // 주의: 백엔드 market/report의 _resolve는 lawd_cd(법정동코드 앞5자리)를
      //   pnu·bcode에서만 도출한다(address는 무시). 둘 다 없으면 HTTP 400이 난다.
      //   따라서 pnu(또는 bcode)는 사실상 준-필수다 — 둘 다 없으면 호출을 막아
      //   백엔드 400 대신 needs-input으로 정직하게 처리한다(0·가짜 결과 금지).
      if (address) body.address = address;
      else missing.push("address");
      // bcode는 SSOT에 별도 슬롯이 없으므로 pnu(19자리) 앞 10자리(=법정동코드)에서 파생한다.
      // 백엔드 _resolve는 bcode[:5]로 lawd_cd를 얻으므로 이 10자리 bcode면 충분(라이브 검증).
      const bcode = pnu && pnu.length >= 10 ? pnu.slice(0, 10) : null;
      if (pnu) body.pnu = pnu;
      // pnu가 없어도 bcode가 있으면 백엔드 bcode 경로로 200을 받는다(둘 다 보내도 무해).
      if (bcode) body.bcode = bcode;
      // pnu·bcode 모두 없으면 lawd_cd를 못 구해 백엔드가 400 → 사전에 needs-input 처리.
      if (!pnu && !bcode) missing.push("pnu");
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
      // ★development_type: 상류 추천(recommend)이 환류한 feasibilityData.developmentType을 우선 채택하고,
      //  미확보(추천 미실행·게이트 차단으로 ranked 비음·비정상 코드)면 백엔드 표준 기본값(M06=일반분양)으로 폴백.
      //  → "모든 수지가 일반분양 고정"이던 결함 해소(무목업: 추천 있으면 추천값, 없으면 백엔드 기본).
      body.development_type =
        safeDevelopmentType(feas?.developmentType) ?? DEFAULT_DEVELOPMENT_TYPE;
      if (landAreaSqm != null) body.total_land_area_sqm = landAreaSqm;
      else missing.push("total_land_area_sqm");
      // 설계 SSOT 우선, 없으면 개략수지가 산정한 GFA(feasibilityData.totalGfaSqm) 폴백 —
      //   설계 전 단계에서도 개략수지 base로 수지·리스크 시뮬이 이어지게 한다(실데이터만, 무날조).
      const gfa = positiveNum(design?.totalGfaSqm) ?? positiveNum(feas?.totalGfaSqm);
      if (gfa != null) body.total_gfa_sqm = gfa;
      else missing.push("total_gfa_sqm");
      const bt = nonEmptyStr(design?.buildingType);
      if (bt) body.building_type = bt;
      // (Phase C-2) ★분양수입 폐루프: 매출단가·세대수·세대(전용)면적을 채워 수지가 실거래 기반으로 계산되게 한다.
      //  근거(코드 확정): 백엔드 revenue = (total_households × sale_ratio) × avg_area_pyeong(평) × avg_sale_price_per_pyeong(원/평)
      //   (revenue_engine.calculate_sale_revenue / revenue_block.compute_revenue). 면적에 전용률을 별도로 곱하지 않는다.
      //   ★sale_ratio는 "분양세대/전체세대 비율(세대수 분할)"이지 면적효율이 아니다(기본 1.0). 따라서 면적기준 정합은 우리가 직접 맞춰야 한다.
      //  셋 중 하나라도 0이면 분양수입=0(백엔드는 avg_area_pyeong 폴백이 없음) → 환류만으로는 효과가 없으므로 세대수·면적도 동반 채운다.
      //  모두 optional(미확보 시 미주입=백엔드 기본 0 → 종전과 동일 동작, 무회귀·needs-input 유지).
      // ① 매출단가(원/평): sales가 환류한 적정분양가. store에 백엔드 단위(원/평)로 보관돼 무변환 전달.
      //   ★이 단가는 "전용면적 기준 평당 실거래가"다(MOLIT excluUseAr=전용면적으로 정규화 — molit_client.py:369,
      //    market_report_service._per_pyeong_stat). 따라서 곱하는 면적도 "전용면적 평"이어야 기준이 일치한다.
      const salePriceWon = positiveNum(feas?.salePricePerPyeongWon);
      if (salePriceWon != null) body.avg_sale_price_per_pyeong = salePriceWon;
      // ② 세대수: 설계(BIM 매스)가 산출한 총세대수 우선, 없으면 개략수지 세대수 가정
      //   (feasibilityData.totalHouseholds, GFA÷유형 표준 전용면적)으로 폴백 — avg_area_pyeong
      //   산식(GFA×전용률÷세대수)에서 세대수가 소거되므로 매출은 GFA×전용률×단가로 개략수지
      //   기준을 재현한다(설계 전 단계에서 매출=0 오탐 방지). 둘 다 없으면 미주입(백엔드 0, 무회귀).
      const households = positiveInt(design?.unitCount) ?? positiveInt(feas?.totalHouseholds);
      if (households != null) body.total_households = households;
      // ③ 세대 평균 "전용"면적(평): 연면적(GFA)에 전용률을 곱해 전용면적으로 환산한 뒤 세대수로 나눈다.
      //    ★면적기준 정합(HIGH 결함 수정): 종전엔 연면적(공용·주차 포함)을 그대로 세대수로 나눠 전용단가와 곱해
      //     분양수입이 과대 산정됐다. 이제 "전용단가 × 전용면적"으로 기준을 일치시킨다.
      //     전용면적(평) = GFA(㎡) × 전용률 ÷ 3.305785 ÷ 세대수.
      //     전용률은 설계 실값(efficiencyPct) 우선, 미확보 시 건물유형 표준값(백엔드 동일 테이블) 폴백.
      //    GFA·세대수가 모두 양수일 때만(0 강제 금지).
      if (gfa != null && households != null && households > 0) {
        const efficiency = resolveSellableEfficiency(
          design?.efficiencyPct,
          design?.buildingType,
        );
        body.avg_area_pyeong = Number(
          ((gfa * efficiency) / PYEONG_SQM / households).toFixed(2),
        );
      }
      // LOW(백로그): sales 단가는 현재 trade.아파트.per_pyeong만 추출(useNodeRunner.pickSalesPricePerPyeongWon).
      //  비아파트(오피스텔·상가 등) 단가 경로는 미동작 — 이번 면적정합 범위 밖(무회귀, 별도 보완).
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

    case "permit": {
      // {address★, pnu?, parcels?} — 인허가 분석(POST /api/v1/permits/ai-analysis).
      // address가 백엔드 필수★(없으면 422/400) → 부지분석 주소로 채우고, 미확보면 missing(호출 금지).
      if (address) body.address = address;
      else missing.push("address");
      // pnu는 lawd_cd/필지식별 보조(있으면 전달).
      if (pnu) body.pnu = pnu;
      // 다필지 통합개발이면 추가 필지 주소 배열을 전달(2개 이상일 때만 — 단일필지는 생략).
      // ★site.parcels의 address만 뽑되, 대표 주소(address)와 중복은 빼고 빈 문자열은 거른다(무목업).
      const parcelAddrs = Array.isArray(site?.parcels)
        ? site!.parcels!
            .map((p) => nonEmptyStr(p?.address))
            .filter((a): a is string => !!a && a !== address)
        : [];
      if (parcelAddrs.length >= 1) body.parcels = parcelAddrs;
      break;
    }

    case "audit": {
      // 심의분석(POST /api/v1/deliberation/analyze) — BFF AnalyzeRequest = {payload, project_id?}.
      // payload는 엔진 AnalysisInput으로 정규화된다(_engine_contract.build_input_dump).
      // ★백엔드 _run_design_review(project_pipeline.py)의 엔진 입력 매핑과 동일하게 구성한다:
      //   - pnu: 19자리 숫자만(아니면 빈 문자열 — prevalidate가 19자리 아닌 비빈값을 거부).
      //   - address: 부지분석 주소(주소 기반 진입 허용).
      //   - calc_targets: building_area / gross_floor_area 산출 대상.
      //   - rules: BCR/FAR 한도 비교 규칙. ★rule_id는 반드시 rule 객체 안에 둔다
      //     (prevalidate가 rules[i].rule.rule_id 필수 — 평면 rule_id면 rule_missing으로 거부).
      // 무목업: 입력 미확보 시 빈 payload가 아니라 "채울 수 있는 필드만" 넣는다(measured/limit는 양수일 때만).
      // measured는 설계(designData.bcr·far) 실값, limit는 부지 실효 한도(effectiveBcrPct·effectiveFarPct,
      // 미확보 시 법정 nationalBcrPct·nationalFarPct 폴백) — 백엔드 site.max_bcr/max_far(실효)와 동일 의미.
      const payload: Record<string, unknown> = {};
      // pnu: 19자리 숫자만 — 아니면 생략(주소 기반 진입). prevalidate 계약 일치.
      if (pnu && /^\d{19}$/.test(pnu)) payload.pnu = pnu;
      if (address) payload.address = address;
      payload.calc_targets = [
        { target: "building_area" },
        { target: "gross_floor_area" },
      ];
      // BCR/FAR 한도 비교 규칙 — measured(설계 실값)·limit(부지 한도)가 모두 양수일 때만 동반 주입(무목업).
      const rules: Record<string, unknown>[] = [];
      const measuredBcr = positiveNum(design?.bcr);
      // ★SSOT 읽기 통일: resolveBcrPct(통합 > 실효 > 법정)로 일원화(다필지 통합 한도 우선).
      //   한도(comparator <=)이므로 positiveNum으로 양수만 통과(0/음수 한도 무의미).
      const limitBcr = positiveNum(resolveBcrPct(site));
      if (measuredBcr != null && limitBcr != null) {
        rules.push({
          rule: { rule_id: "BCR_LIMIT", comparator: "<=" },
          measured: measuredBcr,
          limit: limitBcr,
        });
      }
      const measuredFar = positiveNum(design?.far);
      const limitFar = positiveNum(resolveFarPct(site));
      if (measuredFar != null && limitFar != null) {
        rules.push({
          rule: { rule_id: "FAR_LIMIT", comparator: "<=" },
          measured: measuredFar,
          limit: limitFar,
        });
      }
      if (rules.length >= 1) payload.rules = rules;
      // BFF는 graceful — 입력이 비어도 degraded로 정직 처리하므로 missing 강제 안 함(needs-input 게이트 불요).
      body.payload = payload;
      if (projectId) body.project_id = projectId;
      break;
    }

    default: {
      // 정의되지 않은 노드는 body 미구성(호출측 가드).
      break;
    }
  }

  return { body, missing };
}
