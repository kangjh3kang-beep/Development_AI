// 「전체 분석 한 번에」(U5 통합분석 단순화) 선택맵 산출 — 순수 함수.
//
// 한버튼 실행이 scope 내 "레지스트리 유효 노드"만 picked로 켜도록 정규화한다(미지 id·중복 제거).
// 의존(상류) 자동 포함은 buildPlan/computeClosure가 담당하므로 여기선 leaf 선택집합만 만든다.

import { NODES } from "@/lib/orchestration/node-registry";
import type { NodeId } from "@/lib/orchestration/types";

const VALID_NODE_IDS = new Set<string>(NODES.map((n) => n.id));

/**
 * scopeNodes 중 레지스트리에 실재하는 노드만 true로 켠 선택맵을 반환한다.
 * 미지 id는 무시(가짜 노드 선택 금지), 중복은 한 번만. setPicked가 그대로 소비.
 */
export function buildRunAllSelection(
  scopeNodes: NodeId[],
): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const id of scopeNodes) {
    if (VALID_NODE_IDS.has(id)) out[id] = true;
  }
  return out;
}
