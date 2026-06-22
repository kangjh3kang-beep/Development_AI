"use client";

/**
 * useNodeRunner — 단일 노드 실행 캡슐(노드 불변계약 5단계 §6).
 *
 * 한 노드를 실행할 때 항상 같은 순서를 강제한다:
 *  (a) 그라운딩 + 입력 자동주입 — resolveInputs로 상류 SSOT를 runner body의 context에 채운다.
 *      미확보 슬롯은 grounding[slot]="unavailable"(0 강제 금지·정직 고지).
 *  (b) 노드 runner 호출 — node.runner(method/path/bodyBuilder) 백엔드 POST(전담 interpreter 경유).
 *  (c) 전문가 패널 — node.expertPanel이면 POST /expert-panel/analyze(lens 전달) 다관점 협업.
 *  (d) 가드 — node.verify.crossValidate/verifyAnalysis면 POST /verify/analysis →
 *      판정(pass/warn/fail)을 nodeResult.verifyStatus에.
 *  (e) 정직 고지 — node.ssotOutputs의 update*Action을 데이터 SSOT store에 source:"auto"로 환류 +
 *      grounding/verifyStatus 기록.
 *
 * available:false 노드(audit)는 백엔드 호출 없이 state="skipped-unavailable"로 정직 표기한다.
 *
 * 무회귀: 데이터 SSOT(useProjectContextStore)는 update*Action 호출만(읽기 소비 + 환류). 정책 미접촉.
 * R4(이중 자동재계산 방지): moduleKey=null 노드는 currentSignature를 inputSignature로 기록 —
 * useStageAutoRecalc와 동일 시그니처 게이트를 공유한다. 과금은 엔진 단일(이 훅 외 호출 금지).
 */

import { useCallback } from "react";

import { resolveApiOrigin, apiClient } from "@/lib/api-client";
import { currentSignature, moduleKeyOf } from "@/lib/orchestration/dependency-graph";
import {
  buildNodeBody,
  type NodeBodyContext,
} from "@/lib/orchestration/node-body-builders";
import { NODES } from "@/lib/orchestration/node-registry";
import type { AnalysisNode, NodeId, SsotOutputSpec } from "@/lib/orchestration/types";
import {
  useOrchestrationStore,
  type NodeResult,
  type NodeVerifyStatus,
} from "@/store/useOrchestrationStore";
import {
  useProjectContextStore,
  type ProjectContextState,
  type DesignData,
  type CostData,
  type EsgData,
  type ComplianceData,
} from "@/store/useProjectContextStore";

const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

/** /verify/analysis 응답(부분) — VerificationBadge와 동일 계약. */
interface VerifyResponse {
  verdict?: "pass" | "warn" | "fail" | string;
}

/** runner 응답은 노드마다 달라 느슨한 레코드로 받는다(환류 매핑은 ssotOutputs가 결정). */
type RunnerResponse = Record<string, unknown>;

/**
 * 과금 — runner 성공 후 단일 호출(중복방지).
 *
 * ★코드 확인 결과(2026-06-19, feat-tmp): 프론트 호출가능 과금 엔드포인트는
 *   POST /api/v1/billing/charge(routers/billing.py:126)가 존재하나, 그 라우터의 action
 *   화이트리스트(billing.py:121,133)가 ("project_create","land_analysis","sales_provision",
 *   "registry_issue","registry_analysis")로 하드코딩돼 있어 노드 billingKey("stage:land" 등
 *   stage:* 규약)를 보내면 HTTP 400("알 수 없는 행위")로 거부된다. 서비스 레이어
 *   (billing_service.compute_service_fee:508)는 stage:* 를 정상 디스패치하지만 라우터에서 막힌다.
 *
 *   따라서 stage:* 과금을 프론트에서 호출하려면 별도 백엔드 증분(라우터 화이트리스트에
 *   stage:* 허용)이 필요하다. B2는 백엔드 무수정 범위이므로 여기서는 가짜 호출(400 유발)을
 *   날조하지 않고 명시적 no-op으로 둔다. 단가 미설정=0원=무료이므로 현재 무과금이 정직한 동작이며,
 *   백엔드 증분 후 이 함수만 실호출로 교체하면 된다.
 *
 * TODO(billing): routers/billing.py charge 화이트리스트에 stage:* 허용 추가 후, 아래를
 *   apiClient.post("/billing/charge", { body:{ action: billingKey } })로 교체하고
 *   응답 charged_krw를 반환한다(중복방지는 호출측 plan 단위 1회).
 */
async function chargeStage(_billingKey: string): Promise<number> {
  // 프론트 호출가능 과금엔드포인트(stage:* 수용)가 부재 → no-op. 미설정 0원이라 현재 무과금.
  return 0;
}

/** runner 응답을 store update*Action 입력으로 안전 변환(부분/누락은 무시). */
function readNum(o: RunnerResponse, ...keys: string[]): number | null {
  for (const k of keys) {
    const v = o[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

/** 중첩 객체(예: cost 응답의 range:{min_won,max_won})에서 숫자 키를 안전하게 읽는다. */
function readNestedNum(
  o: RunnerResponse,
  parent: string,
  ...keys: string[]
): number | null {
  const child = o[parent];
  if (!child || typeof child !== "object") return null;
  return readNum(child as RunnerResponse, ...keys);
}

/**
 * design bim/generate 응답의 mass 블록은 GFA(연면적) 키를 직렬화하지 않는다
 * (building_width_m·building_depth_m·num_floors·floor_height_m·bcr_pct·far_pct·total_units만 포함).
 * 따라서 GFA는 폭×깊이×층수(footprint×층수 = 지상 연면적 근사)로 도출한다. 셋 중 하나라도
 * 미확보/비양수면 null(0 강제 금지) — 하류 qto/feasibility는 GFA 미확보 시 needs-input으로 정직 대기.
 * 응답이 직접 total_floor_area_sqm/total_gfa_sqm을 주면 그 값이 우선(이 도출은 마지막 폴백).
 */
export function deriveMassGfa(resp: Record<string, unknown>): number | null {
  const w = readNestedNum(resp, "mass", "building_width_m");
  const d = readNestedNum(resp, "mass", "building_depth_m");
  const f = readNestedNum(resp, "mass", "num_floors");
  if (w != null && d != null && f != null && w > 0 && d > 0 && f > 0) {
    return Math.round(w * d * f);
  }
  return null;
}

/**
 * recommend 응답(optimal-recommend)의 최상위 추천 개발방식 코드(M01~M15)를 뽑는다.
 *
 * 라이브 응답 모양: { ranked: [{ method:"M06", far_basis:"현행", composite:16.0, ... }, ...], ... }.
 * ranked는 composite 내림차순 정렬(백엔드)이라 ranked[0]이 최상위 추천이다.
 * ★far_basis가 "현행"인 후보를 우선 채택한다(종상향은 조건부 시나리오라 기본 수지 가정에 부적합).
 * 현행 후보가 하나도 없으면 정렬 1순위(ranked[0])를 폴백으로 쓴다.
 * ranked가 비었거나(게이트 차단=BLOCKED/resolvable NO) method가 비정상이면 null
 *  → 환류측이 미환류(무목업: 추천 없으면 백엔드 기본 M06 폴백 유지).
 */
export function pickRecommendedDevType(resp: RunnerResponse): string | null {
  const ranked = resp.ranked;
  if (!Array.isArray(ranked) || ranked.length === 0) return null;
  const methodOf = (item: unknown): string | null => {
    if (!item || typeof item !== "object") return null;
    const m = (item as Record<string, unknown>).method;
    return typeof m === "string" && m.trim() ? m.trim() : null;
  };
  const isCurrent = (item: unknown): boolean =>
    !!item &&
    typeof item === "object" &&
    (item as Record<string, unknown>).far_basis === "현행";
  // 현행 근거 후보 우선(정렬 순서 보존), 없으면 ranked[0] 폴백.
  const preferred = ranked.find((it) => isCurrent(it) && methodOf(it));
  return methodOf(preferred ?? ranked[0]);
}

/**
 * (Phase C-2) sales 응답(/api/v1/market/report)에서 수지 매출단가(원/평)를 뽑는다.
 *
 * 라이브 응답 모양: { trade: { 아파트: { per_pyeong: { avg: 11161, ... }, ... }, ... }, ... }.
 * trade.아파트.per_pyeong.avg는 "아파트 평당 실거래가(만원/평)"다(면적 정규화된 평당 단가).
 * 백엔드 수지(FeasibilityCalculateRequest.avg_sale_price_per_pyeong)는 "원/평"이므로 ×10000 변환한다.
 *  예) 11161 만원/평 → 111,610,000 원/평.
 *
 * ★단가 직접경로(평당)를 1차로 쓴다 — pricing_band.fair_price_10k류는 84㎡ 1세대 '총액(만원)'이라
 *  평당 환산에 면적가정이 끼어 부정확하므로 채택하지 않는다(무목업: 부정확 추정 배제).
 * 실거래 자료가 없으면(키 부재·비양수) null → 환류측이 미환류(백엔드 기본 동작 유지).
 */
export function pickSalesPricePerPyeongWon(resp: RunnerResponse): number | null {
  const trade = resp.trade;
  if (!trade || typeof trade !== "object") return null;
  const apt = (trade as Record<string, unknown>)["아파트"];
  if (!apt || typeof apt !== "object") return null;
  const perPyeong = (apt as Record<string, unknown>).per_pyeong;
  if (!perPyeong || typeof perPyeong !== "object") return null;
  const avg = (perPyeong as Record<string, unknown>).avg;
  // avg는 만원/평. 양의 유한수만 인정(0·음수·비숫자=자료 없음 → null).
  if (typeof avg !== "number" || !Number.isFinite(avg) || avg <= 0) return null;
  // 만원/평 → 원/평(×10000). 백엔드 입력단위와 동일하게 변환해 반환한다.
  return Math.round(avg * 10000);
}

/**
 * 노드 산출을 데이터 SSOT store로 환류(e). ssotOutputs의 updateAction별로 분기한다.
 * runner 응답 키는 노드마다 다르므로, 흔한 키 후보를 안전하게 읽어 store 슬롯에 채운다.
 * 미확보 필드는 null(0 강제 금지) — store merge 가드가 user 수동값과 기존값을 보존한다.
 */
function feedbackToStore(
  node: AnalysisNode,
  resp: RunnerResponse,
  store: ProjectContextState,
): void {
  for (const out of node.ssotOutputs) {
    switch (out.updateAction) {
      case "updateSiteAnalysis":
        // 백엔드 zoning/analyze 실응답 키: land_area_sqm, zone_type(용도지역명).
        // (zoneCode/zone_code도 후보 유지 — 다른 산출경로 호환.)
        store.updateSiteAnalysis(
          {
            landAreaSqm: readNum(resp, "landAreaSqm", "land_area_sqm", "area_sqm"),
            zoneCode:
              typeof resp.zoneCode === "string"
                ? resp.zoneCode
                : typeof resp.zone_code === "string"
                  ? (resp.zone_code as string)
                  : typeof resp.zone_type === "string"
                    ? (resp.zone_type as string)
                    : null,
          },
          { source: "auto" },
        );
        break;
      case "updateDesignData":
        // 백엔드 design/{id}/bim/generate 실응답은 mass:{building_width_m,building_depth_m,
        // num_floors,bcr_pct,far_pct,total_units} 중첩 구조다(★GFA 키는 직렬화 안 됨).
        // 면적·층수·건폐/용적·세대수를 mass에서 보강해 읽고, GFA는 키가 없으므로
        // deriveMassGfa(폭×깊이×층수)로 도출한다(top-level camelCase 후보도 유지 — 다른 경로 호환).
        // buildingType/용도는 mass 응답에 없어 null로 둔다 → 하류 qto/feasibility는 백엔드
        // 기본 용도(apartment)로 폴백한다(용도 SSOT 시드는 Phase C 추천결과 환류 시 보강).
        store.updateDesignData(
          {
            totalGfaSqm:
              readNum(resp, "totalGfaSqm", "total_gfa_sqm") ??
              readNestedNum(resp, "mass", "total_floor_area_sqm", "total_gfa_sqm") ??
              deriveMassGfa(resp),
            floorCount:
              readNum(resp, "floorCount", "floor_count") ??
              readNestedNum(resp, "mass", "num_floors", "floor_count"),
            buildingType:
              typeof resp.buildingType === "string" ? resp.buildingType : null,
            bcr: readNum(resp, "bcr") ?? readNestedNum(resp, "mass", "bcr_pct"),
            far: readNum(resp, "far") ?? readNestedNum(resp, "mass", "far_pct"),
            unitCount:
              readNum(resp, "unitCount", "total_units") ??
              readNestedNum(resp, "mass", "total_units"),
          } as DesignData,
          { source: "auto" },
        );
        break;
      case "updateCostData":
        // 백엔드 cost/estimate-overview 실응답 키: total_won, per_pyeong_won, unit_cost_per_sqm,
        // aboveground_won/underground_won/landscape_won/direct_won/indirect_won, range:{min_won,max_won}.
        // (camelCase 후보도 유지 — 다른 산출경로 호환.)
        store.updateCostData(
          {
            totalConstructionCostWon: readNum(
              resp,
              "totalConstructionCostWon",
              "total_construction_cost_won",
              "total_won",
            ),
            perSqmWon: readNum(resp, "perSqmWon", "per_sqm_won", "unit_cost_per_sqm"),
            perPyeongWon: readNum(resp, "perPyeongWon", "per_pyeong_won"),
            abovegroundWon: readNum(resp, "abovegroundWon", "aboveground_won"),
            undergroundWon: readNum(resp, "undergroundWon", "underground_won"),
            landscapeWon: readNum(resp, "landscapeWon", "landscape_won"),
            directWon: readNum(resp, "directWon", "direct_won"),
            indirectWon: readNum(resp, "indirectWon", "indirect_won"),
            rangeMinWon:
              readNum(resp, "rangeMinWon", "range_min_won") ??
              readNestedNum(resp, "range", "min_won"),
            rangeMaxWon:
              readNum(resp, "rangeMaxWon", "range_max_won") ??
              readNestedNum(resp, "range", "max_won"),
            source: "overview",
          } as CostData,
          { source: "auto" },
        );
        break;
      case "updateFeasibilityData": {
        // sales 노드는 매출만 부분패치(partial:true) — ROI 최종 stamp는 feasibility가 담당(슬롯 경합 회피).
        const patch: Record<string, number | null> = {
          totalRevenueWon: readNum(resp, "totalRevenueWon", "total_revenue_won"),
        };
        if (!out.partial) {
          patch.totalCostWon = readNum(resp, "totalCostWon", "total_cost_won");
          patch.profitRatePct = readNum(resp, "profitRatePct", "profit_rate_pct");
          patch.roiPct = readNum(resp, "roiPct", "roi_pct");
          patch.npvWon = readNum(resp, "npvWon", "npv_won");
        }
        // updateFeasibilityData는 meta 인자를 받지 않음(store 시그니처) — patch만 전달.
        store.updateFeasibilityData(patch);
        break;
      }
      case "updateEsgData":
        store.updateEsgData(
          {
            embodiedCarbonKg: readNum(resp, "embodiedCarbonKg"),
            operationalCarbonKg: readNum(resp, "operationalCarbonKg"),
            totalCarbonPerSqm: readNum(resp, "totalCarbonPerSqm"),
          } as EsgData,
          { source: "auto" },
        );
        break;
      case "updateComplianceData": {
        // (Fix #1·감사 HIGH) 백엔드 /regulation/analyze 실응답키 정합. 기존엔 백엔드가 emit하지 않는
        // camelCase 불리언만 읽어 complianceData가 항상 all-null이었다(법규단계 영구 미완료·근거 유실).
        // limits/evidence/legal_refs/zone_type를 SSOT에 보존(하류 재호출 불요). 적합판정 불리언은
        // 백엔드가 산출 시(camel 또는 snake) 읽되, 미산출(설계 전 단계)이면 null(설계 후 계산).
        const r = resp as Record<string, unknown>;
        const asBool = (camel: string, snake: string): boolean | null => {
          const v = r[camel] ?? r[snake];
          return typeof v === "boolean" ? v : null;
        };
        const asArr = (...keys: string[]): unknown[] | null => {
          for (const k of keys) if (Array.isArray(r[k])) return r[k] as unknown[];
          return null;
        };
        store.updateComplianceData({
          bcrCompliant: asBool("bcrCompliant", "bcr_compliant"),
          farCompliant: asBool("farCompliant", "far_compliant"),
          heightCompliant: asBool("heightCompliant", "height_compliant"),
          violations: Array.isArray(r.violations) ? (r.violations as string[]) : [],
          limits:
            r.limits && typeof r.limits === "object"
              ? (r.limits as Record<string, unknown>)
              : null,
          evidence: asArr("evidence"),
          legalRefs: asArr("legal_refs", "legalRefs"),
          zoneType:
            typeof r.zone_type === "string"
              ? r.zone_type
              : typeof r.zoneType === "string"
                ? r.zoneType
                : null,
        } as ComplianceData);
        break;
      }
      case "setRecommendedDevType": {
        // (Phase C-1) 추천 노드 → 최상위 추천 개발방식 코드(M01~M15)만 부분패치.
        // updatedAt.feasibility를 stamp하지 않는 전용 액션이라 수지 staleness를 오염시키지 않는다.
        // 코드 미산출(게이트 차단·ranked 비면 null)이면 setRecommendedDevType가 no-op(백엔드 기본 M06 폴백).
        const devType = pickRecommendedDevType(resp);
        store.setRecommendedDevType(devType);
        break;
      }
      case "setSalesPricePerPyeong": {
        // (Phase C-2) sales(시장보고서) → 아파트 평당 실거래가(만원/평)를 ×10000(원/평) 변환해 부분패치.
        // updatedAt.feasibility를 stamp하지 않는 전용 액션이라 수지 staleness를 오염시키지 않는다.
        // 실거래 자료 없음(키 부재·비양수)이면 null → setSalesPricePerPyeong가 no-op(백엔드 기본 동작).
        const priceWon = pickSalesPricePerPyeongWon(resp);
        store.setSalesPricePerPyeong(priceWon);
        break;
      }
      case "markFinanceUpdated":
        store.markFinanceUpdated();
        break;
      default:
        break;
    }
  }
}

/** ssotOutputs가 환류할 update*Action이 있는지(표시·검증 전용 노드는 환류 없음). */
function hasFeedback(outputs: SsotOutputSpec[]): boolean {
  return outputs.length > 0;
}

/**
 * useNodeRunner — runNode(id)를 반환하는 훅.
 * @returns runNode: 단일 노드를 5단계로 실행하고 NodeResult를 반환(store에도 환류).
 */
export function useNodeRunner(): { runNode: (id: NodeId) => Promise<NodeResult> } {
  const runNode = useCallback(async (id: NodeId): Promise<NodeResult> => {
    const node = BY_ID[id];
    const orch = useOrchestrationStore.getState();
    const dataStore = useProjectContextStore.getState();
    const now = () => Date.now();

    // 미정의 노드 방어(레지스트리 정합은 lint가 강제).
    if (!node) {
      const res: NodeResult = {
        state: "error",
        verifyStatus: null,
        grounding: {},
        chargedKrw: 0,
        inputSignature: null,
        at: now(),
        error: `미정의 노드: ${id}`,
      };
      orch.recordNodeResult(id, res);
      return res;
    }

    // available:false(audit 등) — 0 강제 금지·정직 고지. 백엔드 호출 없음.
    if (!node.available) {
      const res: NodeResult = {
        state: "skipped-unavailable",
        verifyStatus: null,
        grounding: Object.fromEntries(
          node.groundingSources.map((g) => [g, "unavailable" as const]),
        ),
        chargedKrw: 0,
        inputSignature: null,
        at: now(),
      };
      orch.recordNodeResult(id, res);
      return res;
    }

    orch.setNodeState(id, "running");

    // ── (a) 그라운딩 + 입력 자동주입 ──
    const { ready, missing } = orch.resolveInputs(id);
    // 미확보 입력 슬롯은 unavailable(0 강제 금지). 그라운딩 출처와 슬롯명을 함께 정직 표기.
    const missingGrounding: Record<string, "ok" | "unavailable"> = {};
    for (const m of missing) {
      missingGrounding[`input:${m.slot}${m.field ? "." + m.field : ""}`] = "unavailable";
    }
    // 상류 산출 = runner body의 context(모세혈관). ready 슬롯값을 컨텍스트로 모은다.
    const context: Record<string, unknown> = {};
    for (const r of ready) {
      const slotVal = (dataStore as unknown as Record<string, unknown>)[r.slot];
      if (slotVal != null) context[r.slot] = slotVal;
    }

    // 입력이 하나도 확보되지 않았고(상류 컨텍스트 0) 노드가 입력을 요구하면 정직하게 미가용 처리.
    // (가이드/선택 모드는 폐포가 상류를 먼저 실행하므로 보통 ready가 채워진다.)
    // 이 경로는 runner에 도달하지 않으므로 그라운딩 출처를 "ok"로 낙관표기하지 않는다 — 전부 unavailable
    // 초기화(미조회인데 "ok"로 보이던 결함 차단. available:false 경로와 일관).
    if (node.ssotInputs.length > 0 && ready.length === 0) {
      const grounding: Record<string, "ok" | "unavailable"> = {};
      for (const g of node.groundingSources) grounding[g] = "unavailable";
      Object.assign(grounding, missingGrounding);
      const res: NodeResult = {
        state: "skipped-unavailable",
        verifyStatus: null,
        grounding,
        chargedKrw: 0,
        inputSignature: moduleKeyOf(id) ? null : currentSignature(id, dataStore),
        at: now(),
      };
      orch.recordNodeResult(id, res);
      return res;
    }

    // runner에 실제로 도달하는 경로에서만 그라운딩 출처를 "ok"로 초기화한다(미확보 슬롯은 위 missing으로 덮음).
    const grounding: Record<string, "ok" | "unavailable"> = {};
    for (const g of node.groundingSources) grounding[g] = "ok";
    Object.assign(grounding, missingGrounding);

    const inputSignature = moduleKeyOf(id) ? null : currentSignature(id, dataStore);
    const origin = resolveApiOrigin();

    // runner path의 {id}/{project_id} 등 식별자 플레이스홀더는 데이터 SSOT projectId로 치환한다.
    // (현 레지스트리는 프로젝트 스코프 단일 토큰만 사용 — 비-projectId/다중 토큰 추가 시 토큰명 매핑 분기 필요).
    // projectId 미확보(null/빈값)면 백엔드를 부르지 않고 needs-input으로 정직 고지(0 강제 금지).
    const rawPath = node.runner.path;
    const hasPlaceholder = /\{[^}]+\}/.test(rawPath);
    const projectId = dataStore.projectId;
    if (hasPlaceholder && (projectId == null || projectId === "")) {
      const groundingMissing: Record<string, "ok" | "unavailable"> = {};
      for (const g of node.groundingSources) groundingMissing[g] = "unavailable";
      Object.assign(groundingMissing, missingGrounding);
      groundingMissing["input:projectId"] = "unavailable";
      const res: NodeResult = {
        state: "needs-input",
        verifyStatus: null,
        grounding: groundingMissing,
        chargedKrw: 0,
        inputSignature,
        at: now(),
      };
      orch.recordNodeResult(id, res);
      return res;
    }
    const resolvedPath = hasPlaceholder
      ? rawPath.replace(/\{[^}]+\}/g, projectId as string)
      : rawPath;

    // ── (b-준비) 노드별 백엔드 평면 body 구성(SSOT 슬롯 → 백엔드 필드, B6-1) ──
    // 예전엔 모든 노드를 { builder, context }로 보내 백엔드가 소비하지 못해 7노드 422·
    // design 빈결과였다. buildNodeBody가 노드별 정확한 평면 body와 필수 누락(missing)을 만든다.
    const { body, missing: bodyMissing } = buildNodeBody(
      id,
      context as NodeBodyContext,
      projectId,
    );
    // 필수(★)필드를 SSOT에서 못 채웠으면 백엔드를 부르지 않고 needs-input으로 정직 고지(0 강제 금지).
    if (bodyMissing.length > 0) {
      const groundingMissing: Record<string, "ok" | "unavailable"> = {
        ...grounding,
      };
      for (const key of bodyMissing) {
        groundingMissing[`input:${key}`] = "unavailable";
      }
      const res: NodeResult = {
        state: "needs-input",
        verifyStatus: null,
        grounding: groundingMissing,
        chargedKrw: 0,
        inputSignature,
        at: now(),
      };
      orch.recordNodeResult(id, res);
      return res;
    }

    try {
      // ── (b) 노드 runner 호출(전담 interpreter 경유) ──
      // 레지스트리 path는 버전 prefix 포함 전체경로(/api/v1|v2/...)라 절대 URL로 호출한다
      // (apiClient 상대경로는 /api/v1을 자동 prepend → 이중 prefix 방지).
      const url = `${origin}${resolvedPath}`;
      const resp = await apiClient.request<RunnerResponse>(url, {
        method: node.runner.method,
        // 노드별 백엔드 평면 body(top-level 필드). 예전 { builder, context } 모양 폐기.
        body,
        useMock: false,
      });
      const runnerResp: RunnerResponse =
        resp && typeof resp === "object" ? (resp as RunnerResponse) : {};

      // ── (c) 전문가 패널(expertPanel:true 노드만) ──
      if (node.expertPanel) {
        try {
          await apiClient.post("/expert-panel/analyze", {
            body: {
              analysis_type: node.lens,
              address:
                (context.siteAnalysis as { address?: string } | undefined)?.address ??
                "",
              context: runnerResp,
              mode: "single",
            },
            useMock: false,
          });
        } catch {
          // 패널 실패는 본 분석을 무효화하지 않는다(보조 협업 — 조용히 무시).
        }
      }

      // ── (d) 가드 — /verify/analysis(crossValidate/verifyAnalysis) ──
      let verifyStatus: NodeVerifyStatus = null;
      if (node.verify.crossValidate || node.verify.verifyAnalysis) {
        try {
          const v = await apiClient.post<VerifyResponse>("/verify/analysis", {
            body: {
              analysis_type: node.lens,
              source: context, // 상류 사실근거(원천)
              output: runnerResp, // 노드 LLM 산출(주장)
            },
            useMock: false,
          });
          const verdict = v?.verdict;
          verifyStatus =
            verdict === "pass" || verdict === "warn" || verdict === "fail"
              ? verdict
              : "warn"; // 알 수 없는 판정은 보수적으로 warn(통과로 오인 금지)
        } catch {
          verifyStatus = null; // 검증 실패는 분석 자체를 무효화하지 않음(정직: 미검증)
        }
      }

      // ── (e) 정직 고지 — store 환류(source:"auto") ──
      if (hasFeedback(node.ssotOutputs)) {
        feedbackToStore(node, runnerResp, dataStore);
      }

      // ── 과금 — runner 성공 후 단일 호출(no-op, 위 chargeStage 주석 참고) ──
      const chargedKrw = node.billingKey ? await chargeStage(node.billingKey) : 0;

      const res: NodeResult = {
        state: "done",
        verifyStatus,
        grounding,
        chargedKrw,
        inputSignature,
        at: now(),
      };
      orch.recordNodeResult(id, res);
      return res;
    } catch (err) {
      const res: NodeResult = {
        state: "error",
        verifyStatus: null,
        grounding,
        chargedKrw: 0,
        inputSignature,
        at: now(),
        error: err instanceof Error ? err.message : "노드 실행 실패",
      };
      orch.recordNodeResult(id, res);
      return res;
    }
  }, []);

  return { runNode };
}
