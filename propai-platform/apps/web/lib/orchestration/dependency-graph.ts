// 분석 오케스트레이션 — 순수 그래프 엔진(L1)
// Phase B 블루프린트 §2-B 정합. store·React 비의존 순수 TypeScript → 단위테스트 100%, 무회귀 0.
//
// 쉬운 설명: 노드끼리는 "이걸 하려면 저게 먼저 필요하다"는 의존관계(DAG)가 있다.
// 이 파일은 (1) 선택한 노드의 상류를 전부 끌어모으고(폐포), (2) 실행 가능한 순서로 줄세우고(위상정렬),
// (3) 동시에 돌려도 되는 묶음으로 나누고(레벨), (4) 입력이 바뀌었는지 지문(서명)으로 판별하는,
// 순수한 계산 함수들의 모음이다. 외부 상태를 건드리지 않는다.

import { NODES } from "./node-registry";
import type {
  NodeId,
  AnalysisNode,
  ModuleKey,
  ProjectContextState,
} from "./types";

/** id → 노드 메타 빠른 조회 맵. */
const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

/** storyOrder 빠른 조회(topoSort tie-break·정렬용). */
const STORY_ORDER: Record<NodeId, number> = Object.fromEntries(
  NODES.map((n) => [n.id, n.storyOrder]),
) as Record<NodeId, number>;

/**
 * 선택집합 → 의존성 폐포(상류 전부 포함, 전이적).
 * DFS + 방문집합(사이클 가드)으로 무한루프를 막는다. 반환 순서는 storyOrder 안정 정렬.
 */
export function computeClosure(picked: NodeId[]): NodeId[] {
  const seen = new Set<NodeId>();
  const stack: NodeId[] = [...picked];
  while (stack.length) {
    const id = stack.pop()!;
    if (seen.has(id)) continue; // 이미 방문 → 사이클/중복 가드
    seen.add(id);
    const node = BY_ID[id];
    if (!node) continue; // 미정의 노드 방어(레지스트리 정합은 lint가 강제)
    for (const up of node.upstream) stack.push(up);
  }
  return [...seen].sort((a, b) => STORY_ORDER[a] - STORY_ORDER[b]);
}

/**
 * 폐포 → 위상정렬 실행순서(Kahn 알고리즘). 동일 in-degree는 storyOrder로 tie-break.
 * 입력 집합 내부 엣지만 고려한다(부분집합 정렬 가능). 사이클이면 throw.
 */
export function topoSort(ids: NodeId[]): NodeId[] {
  const set = new Set(ids);
  // 입력 집합으로 제한한 in-degree와 인접리스트(upstream → dependent 방향).
  const indeg = new Map<NodeId, number>();
  const dependents = new Map<NodeId, NodeId[]>();
  for (const id of set) {
    indeg.set(id, 0);
    dependents.set(id, []);
  }
  for (const id of set) {
    for (const up of BY_ID[id].upstream) {
      if (!set.has(up)) continue; // 집합 밖 의존은 무시(이미 완료 가정)
      indeg.set(id, (indeg.get(id) ?? 0) + 1);
      dependents.get(up)!.push(id);
    }
  }
  // in-degree 0인 후보를 storyOrder 오름차순 우선큐처럼 처리.
  const ready: NodeId[] = [...set].filter((id) => (indeg.get(id) ?? 0) === 0);
  ready.sort((a, b) => STORY_ORDER[a] - STORY_ORDER[b]);
  const out: NodeId[] = [];
  while (ready.length) {
    const id = ready.shift()!;
    out.push(id);
    for (const dep of dependents.get(id)!) {
      const d = (indeg.get(dep) ?? 0) - 1;
      indeg.set(dep, d);
      if (d === 0) {
        // storyOrder 순서를 유지하며 삽입.
        const pos = ready.findIndex((r) => STORY_ORDER[r] > STORY_ORDER[dep]);
        if (pos === -1) ready.push(dep);
        else ready.splice(pos, 0, dep);
      }
    }
  }
  if (out.length !== set.size) {
    const remaining = [...set].filter((id) => !out.includes(id));
    throw new Error(
      `topoSort: 의존성 사이클 감지 — 정렬 불가 노드: ${remaining.join(", ")}`,
    );
  }
  return out;
}

/**
 * topo 결과를 레벨(rank)별 그룹으로 — 동일 레벨은 상호 비의존이라 병렬 실행 가능.
 * rank(id) = max(rank(upstream)) + 1, 상류 없으면 0. 사이클이면 (topoSort가) throw.
 */
export function topoLevels(ids: NodeId[]): NodeId[][] {
  const ordered = topoSort(ids); // 사이클 가드 + 처리 순서 보장
  const set = new Set(ids);
  const rank = new Map<NodeId, number>();
  for (const id of ordered) {
    let r = 0;
    for (const up of BY_ID[id].upstream) {
      if (!set.has(up)) continue;
      r = Math.max(r, (rank.get(up) ?? 0) + 1);
    }
    rank.set(id, r);
  }
  const maxRank = ordered.length ? Math.max(...ordered.map((id) => rank.get(id)!)) : -1;
  const levels: NodeId[][] = Array.from({ length: maxRank + 1 }, () => []);
  for (const id of ordered) levels[rank.get(id)!].push(id);
  // 각 레벨 내부는 storyOrder 안정 정렬(표시·실행 결정성).
  for (const level of levels) level.sort((a, b) => STORY_ORDER[a] - STORY_ORDER[b]);
  return levels;
}

/** 노드 → ModuleKey(있으면). store isStale/isReadyForFirstCompute에 넘길 키. */
export function moduleKeyOf(id: NodeId): ModuleKey | null {
  return BY_ID[id].moduleKey;
}

/**
 * moduleKey=null 노드용 입력 시그니처(ssotInputs 슬롯/필드 값의 안정 직렬화 해시).
 * useStageAutoRecalc의 inputSignature 게이트와 동일 패턴 — 입력이 안 바뀌면 재실행/재과금 안 함.
 * 안정성: 동일 입력 → 동일 문자열(키 정렬·결정적 직렬화).
 */
export function currentSignature(id: NodeId, s: ProjectContextState): string {
  const node = BY_ID[id];
  if (!node) return "";
  const parts: string[] = [];
  for (const input of node.ssotInputs) {
    const slotVal = readSlot(s, input.slot, input.field);
    parts.push(`${input.slot}${input.field ? "." + input.field : ""}=${stableStringify(slotVal)}`);
  }
  return parts.join("|");
}

/** store 슬롯/필드 값 읽기(financeStamp는 데이터 필드 없음 → 부재로 취급). */
function readSlot(s: ProjectContextState, slot: string, field?: string): unknown {
  if (slot === "financeStamp") return null;
  const container = (s as unknown as Record<string, unknown>)[slot];
  if (container == null) return null;
  if (field) {
    if (typeof container !== "object") return null;
    return (container as Record<string, unknown>)[field] ?? null;
  }
  return container;
}

/** 결정적 JSON 직렬화(객체 키 정렬) — 시그니처 안정성 보장. */
function stableStringify(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(",")}}`;
}

/**
 * 가이드 모드 위상순서 = 전체 9노드를 storyOrder(11단계 스토리라인) 정렬 후 topoSort로 안정화.
 * 의존성을 깨지 않으면서 스토리라인 진행레일 순서를 따른다.
 */
export function guidedOrder(): NodeId[] {
  const all = NODES.map((n) => n.id).sort((a, b) => STORY_ORDER[a] - STORY_ORDER[b]);
  return topoSort(all);
}
