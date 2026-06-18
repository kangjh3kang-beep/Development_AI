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
        store.updateSiteAnalysis(
          {
            landAreaSqm: readNum(resp, "landAreaSqm", "land_area_sqm", "area_sqm"),
            zoneCode:
              typeof resp.zoneCode === "string"
                ? resp.zoneCode
                : typeof resp.zone_code === "string"
                  ? (resp.zone_code as string)
                  : null,
          },
          { source: "auto" },
        );
        break;
      case "updateDesignData":
        store.updateDesignData(
          {
            totalGfaSqm: readNum(resp, "totalGfaSqm", "total_gfa_sqm"),
            floorCount: readNum(resp, "floorCount", "floor_count"),
            buildingType:
              typeof resp.buildingType === "string" ? resp.buildingType : null,
            bcr: readNum(resp, "bcr"),
            far: readNum(resp, "far"),
          } as DesignData,
          { source: "auto" },
        );
        break;
      case "updateCostData":
        store.updateCostData(
          {
            totalConstructionCostWon: readNum(
              resp,
              "totalConstructionCostWon",
              "total_construction_cost_won",
            ),
            perSqmWon: readNum(resp, "perSqmWon", "per_sqm_won"),
            perPyeongWon: readNum(resp, "perPyeongWon", "per_pyeong_won"),
            abovegroundWon: readNum(resp, "abovegroundWon"),
            undergroundWon: readNum(resp, "undergroundWon"),
            landscapeWon: readNum(resp, "landscapeWon"),
            directWon: readNum(resp, "directWon"),
            indirectWon: readNum(resp, "indirectWon"),
            rangeMinWon: readNum(resp, "rangeMinWon", "range_min_won"),
            rangeMaxWon: readNum(resp, "rangeMaxWon", "range_max_won"),
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
      case "updateComplianceData":
        store.updateComplianceData({
          bcrCompliant:
            typeof resp.bcrCompliant === "boolean" ? resp.bcrCompliant : null,
          farCompliant:
            typeof resp.farCompliant === "boolean" ? resp.farCompliant : null,
          heightCompliant:
            typeof resp.heightCompliant === "boolean" ? resp.heightCompliant : null,
          violations: Array.isArray(resp.violations)
            ? (resp.violations as string[])
            : [],
        } as ComplianceData);
        break;
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

    try {
      // ── (b) 노드 runner 호출(전담 interpreter 경유) ──
      // 레지스트리 path는 버전 prefix 포함 전체경로(/api/v1|v2/...)라 절대 URL로 호출한다
      // (apiClient 상대경로는 /api/v1을 자동 prepend → 이중 prefix 방지).
      const url = `${origin}${resolvedPath}`;
      const resp = await apiClient.request<RunnerResponse>(url, {
        method: node.runner.method,
        body: {
          // bodyBuilder 식별자 + 상류 컨텍스트를 함께 전달(백엔드가 컨텍스트 소비).
          builder: node.runner.bodyBuilder,
          context,
        },
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
