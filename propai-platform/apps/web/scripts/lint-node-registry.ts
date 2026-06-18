// 분석 오케스트레이션 — 노드 레지스트리 lint(빌드타임 계약 강제, CI 상주)
// Phase B 블루프린트 §6 정합. 노드 추가 시 불변계약 위반을 컴파일/CI 타임에 차단한다.
//
// 검사 항목:
//   (E1) 사이클 탐지         — upstream 순환 → fail
//   (E2) 미정의 upstream     — 존재하지 않는 NodeId 참조 → fail
//   (E3) 중복 billingKey     — 동일 "stage:<name>" 중복 → fail
//   (E4) 계약 5단계 누락      — verify.crossValidate/verifyAnalysis 누락, 판단분기인데 expertPanel=false,
//                              groundingSources 빈배열, reportContract.unavailableLabel 빈문자열 → fail
//   (E5) stage-node-map 일관성 — node.storylineStage vs STAGE_TO_NODES 역매핑 불일치 → fail
//   (W1) MODULE_UPSTREAM 드리프트 — moduleKey 보유 노드의 노드폐포 ⊉ MODULE_UPSTREAM 폐포 → warn
//
// 실행: 단독 CLI(`npx tsx apps/web/scripts/lint-node-registry.ts`) 또는
//       CI 게이트 vitest(`lib/orchestration/lint-node-registry.test.ts`가 lintNodeRegistry()를 호출해 errors=0 단언).
//       위반(errors) 발생 시 process.exit(1).

import { NODES } from "@/lib/orchestration/node-registry";
import { STAGE_TO_NODES } from "@/lib/orchestration/stage-node-map";
import { computeClosure } from "@/lib/orchestration/dependency-graph";
import type { NodeId, ModuleKey, AnalysisNode } from "@/lib/orchestration/types";

export interface LintResult {
  errors: string[];
  warnings: string[];
}

/**
 * useProjectContextStore의 MODULE_UPSTREAM(7키 DAG) 미러.
 * store는 미수정 원칙이라 export하지 않으므로, 드리프트 검사용으로 여기 동기화한다.
 * 코드 대조: apps/web/store/useProjectContextStore.ts L255-264 (변경 시 이 미러도 갱신).
 */
const MODULE_UPSTREAM_MIRROR: Record<ModuleKey, ModuleKey[]> = {
  siteAnalysis: [],
  design: ["siteAnalysis"],
  cost: ["siteAnalysis", "design"],
  feasibility: ["siteAnalysis", "design", "cost"],
  finance: ["feasibility", "cost"],
  esg: ["design"],
  compliance: ["siteAnalysis", "design"],
};

/** ModuleKey 폐포(MODULE_UPSTREAM 미러 기준 전이 상류). */
function moduleClosure(key: ModuleKey): Set<ModuleKey> {
  const seen = new Set<ModuleKey>();
  const stack: ModuleKey[] = [...(MODULE_UPSTREAM_MIRROR[key] ?? [])];
  while (stack.length) {
    const k = stack.pop()!;
    if (seen.has(k)) continue;
    seen.add(k);
    for (const up of MODULE_UPSTREAM_MIRROR[k] ?? []) stack.push(up);
  }
  return seen;
}

/** 노드 레지스트리 전체 계약 검사. 순수함수(부수효과 없음) → 테스트·CLI 공용.
 * nodes를 주입하면(기본=실 레지스트리 NODES) 깨진 레지스트리 네거티브 테스트가 가능하다.
 * (W1 드리프트는 computeClosure가 실 NODES를 참조하므로 실 레지스트리에 대해서만 수행). */
export function lintNodeRegistry(nodes: AnalysisNode[] = NODES): LintResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const ids = nodes.map((n) => n.id);
  const idSet = new Set<NodeId>(ids);

  // 중복 NodeId 방어(레지스트리 자체 무결성).
  if (idSet.size !== ids.length) {
    errors.push(`중복 NodeId 존재: ${ids.join(", ")}`);
  }

  // (E2) 미정의 upstream
  for (const node of nodes) {
    for (const up of node.upstream) {
      if (!idSet.has(up)) {
        errors.push(`[E2 미정의 upstream] 노드 "${node.id}"가 존재하지 않는 "${up}"를 참조`);
      }
    }
  }
  // (E1) 사이클: 각 노드 폐포 계산 중 자기 자신이 상류에 등장하면 순환.
  for (const node of nodes) {
    if (hasCycleFrom(node.id, idSet, nodes)) {
      errors.push(`[E1 사이클] 노드 "${node.id}"에서 의존성 순환 감지`);
    }
  }

  // (E3) 중복 billingKey
  const billingSeen = new Map<string, NodeId>();
  for (const node of nodes) {
    if (!node.billingKey) continue;
    const prev = billingSeen.get(node.billingKey);
    if (prev) {
      errors.push(
        `[E3 중복 billingKey] "${node.billingKey}" — "${prev}" / "${node.id}" 충돌`,
      );
    } else {
      billingSeen.set(node.billingKey, node.id);
    }
  }

  // (E4) 계약 5단계 — 노드 불변계약상 모든 노드는 trust.cross_validate + verify를 수행해야 하므로
  //   "존재 여부"가 아니라 true를 강제한다(false로 끄는 silent 우회 차단).
  for (const node of nodes) {
    if (node.verify?.crossValidate !== true) {
      errors.push(`[E4 계약] 노드 "${node.id}" verify.crossValidate=true 필요(교차검증 필수)`);
    }
    if (node.verify?.verifyAnalysis !== true) {
      errors.push(`[E4 계약] 노드 "${node.id}" verify.verifyAnalysis=true 필요(할루시네이션 가드 필수)`);
    }
    if (!node.groundingSources || node.groundingSources.length === 0) {
      errors.push(`[E4 계약] 노드 "${node.id}" groundingSources 빈 배열(그라운딩 출처 필수)`);
    }
    if (!node.reportContract || node.reportContract.unavailableLabel.trim() === "") {
      errors.push(`[E4 계약] 노드 "${node.id}" reportContract.unavailableLabel 빈 문자열(0 강제 금지·정직표기 필수)`);
    }
    // 판단분기 노드(다관점 협업 필요)인데 expertPanel=false면 위반.
    // 판단분기 = recommend/legal/sales/feasibility/finance(audit은 엔진 내부라 예외).
    if (JUDGEMENT_NODES.has(node.id) && node.expertPanel !== true) {
      errors.push(`[E4 계약] 판단분기 노드 "${node.id}"는 expertPanel=true 필요(다관점 협업)`);
    }
  }

  // (E5) stage-node-map 일관성: node.storylineStage(SSOT)와 STAGE_TO_NODES 역매핑 일치
  for (const node of nodes) {
    const bucket = STAGE_TO_NODES[node.storylineStage] ?? [];
    if (!bucket.includes(node.id)) {
      errors.push(
        `[E5 stage-map] 노드 "${node.id}"(storylineStage=${node.storylineStage})가 STAGE_TO_NODES에서 누락`,
      );
    }
  }
  // 역방향: STAGE_TO_NODES에 있는 노드가 실제로 그 storylineStage를 가지는가
  for (const [stage, bucketRaw] of Object.entries(STAGE_TO_NODES)) {
    for (const nid of bucketRaw as NodeId[]) {
      const node = nodes.find((n) => n.id === nid);
      if (!node) {
        errors.push(`[E5 stage-map] STAGE_TO_NODES["${stage}"]에 미정의 노드 "${nid}"`);
      } else if (node.storylineStage !== stage) {
        errors.push(
          `[E5 stage-map] 노드 "${nid}" storylineStage=${node.storylineStage}인데 STAGE_TO_NODES["${stage}"]에 잘못 매핑`,
        );
      }
    }
  }

  // (W1) MODULE_UPSTREAM 드리프트: moduleKey 보유 노드의 노드폐포가 store 폐포를 모두 덮는지(warn).
  //   computeClosure가 실 NODES를 참조하므로 실 레지스트리에 대해서만 수행(주입 레지스트리는 스킵).
  if (nodes === NODES) {
    for (const node of nodes) {
      if (!node.moduleKey) continue;
      const nodeClosureIds = new Set(computeClosure([node.id]));
      // 노드폐포가 stamp하는 ModuleKey 집합.
      const stampedKeys = new Set<ModuleKey>();
      for (const cid of nodeClosureIds) {
        const cn = nodes.find((n) => n.id === cid);
        if (cn?.moduleKey) stampedKeys.add(cn.moduleKey);
      }
      const storeClosure = moduleClosure(node.moduleKey);
      for (const reqKey of storeClosure) {
        if (!stampedKeys.has(reqKey)) {
          warnings.push(
            `[W1 드리프트] 노드 "${node.id}"(moduleKey=${node.moduleKey}) 노드폐포가 MODULE_UPSTREAM 상류 "${reqKey}"를 stamp하지 않음`,
          );
        }
      }
    }
  }

  return { errors, warnings };
}

/** 판단분기 노드(다관점 협업 expertPanel 강제 대상). audit은 엔진 내부라 제외. */
const JUDGEMENT_NODES = new Set<NodeId>([
  "recommend",
  "legal",
  "sales",
  "feasibility",
  "finance",
]);

/** id에서 시작해 자기 자신으로 돌아오는 순환이 있는지(DFS 재귀스택). nodes 주입 가능(네거티브 테스트). */
function hasCycleFrom(start: NodeId, idSet: Set<NodeId>, nodes: AnalysisNode[]): boolean {
  const visiting = new Set<NodeId>();
  const done = new Set<NodeId>();
  const byId = new Map(nodes.map((n) => [n.id, n]));
  function dfs(id: NodeId): boolean {
    if (visiting.has(id)) return true; // 재귀스택에 다시 등장 → 사이클
    if (done.has(id)) return false;
    visiting.add(id);
    const node = byId.get(id);
    if (node) {
      for (const up of node.upstream) {
        if (!idSet.has(up)) continue; // 미정의는 E2가 보고
        if (dfs(up)) return true;
      }
    }
    visiting.delete(id);
    done.add(id);
    return false;
  }
  return dfs(start);
}

/** CLI 진입 — 위반 출력 후 errors>0이면 비0 종료. (vitest 환경에선 main 가드로 미실행) */
function runCli(): void {
  const { errors, warnings } = lintNodeRegistry();
  for (const w of warnings) console.warn(`WARN ${w}`);
  if (errors.length) {
    for (const e of errors) console.error(`FAIL ${e}`);
    console.error(`\nlint-node-registry: ${errors.length}건 위반(경고 ${warnings.length}건).`);
    process.exit(1);
  }
  console.log(`lint-node-registry: 통과 — 노드 ${NODES.length}개, 위반 0, 경고 ${warnings.length}건.`);
}

// main 모듈로 직접 실행될 때만 CLI 구동(import 시에는 미실행 → 테스트 안전).
// vitest는 import.meta.url과 argv가 다르므로 자동 미실행.
const isDirectRun =
  typeof process !== "undefined" &&
  Array.isArray(process.argv) &&
  /lint-node-registry\.(ts|js|mjs|cjs)$/.test(process.argv[1] ?? "");
if (isDirectRun) runCli();
