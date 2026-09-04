// 분석 오케스트레이션 — 레지스트리 → 셀렉터 옵션 어댑터(L3 소비 보조)
// Phase B 블루프린트 §3-A 정합. AnalysisModuleSelector(공용 컴포넌트)는 무수정 — 이 어댑터가
// 9노드 레지스트리를 그 컴포넌트의 AnalysisModuleOption[]로 변환만 한다.
//
// 쉬운 설명: 화면의 "분석 항목 선택" 체크박스 목록을, 노드 레지스트리(SSOT) 한 곳에서 자동 생성한다.
// 어느 항목이 얼마인지(coinCost), 잠겼는지(locked), 이미 최신이라 스킵되는지(description)를
// 레지스트리 메타 + 관리자 요율(feeOf) + 현재 상태(ctx)로 채운다. 수치는 절대 하드코딩하지 않는다.
//
// 무목업·과금 원칙:
//   - coinCost = feeOf(node.billingKey). 관리자 미설정이면 0 → 셀렉터가 "추가 비용 없음" 표기(허위값 금지).
//   - locked = !node.available(audit 심의엔진 미머지) 또는 폐포 강제 노드(의존 자동포함, 체크 불가).
//   - description = 신선분이면 "최신(스킵)" / unavailable이면 정직 표기.

import {
  BarChart3,
  Compass,
  Landmark,
  LayoutGrid,
  Map as MapIcon,
  Ruler,
  Scale,
  Search,
  Tag,
  Blocks,
  type LucideIcon,
} from "lucide-react";
import { NODES } from "./node-registry";
import type { AnalysisModuleOption } from "@/components/common/AnalysisModuleSelector";
import type { AnalysisNode, NodeId, LifecycleStage } from "./types";

/** id → 노드 메타 빠른 조회. */
const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

/** storylineStage(11단계) → 한국어 그룹 라벨(셀렉터 분류 헤더). */
const STAGE_GROUP_LABEL: Record<LifecycleStage, string> = {
  "site-analysis": "토지·입지",
  legal: "법규·인허가",
  design: "설계·심의",
  bim: "BIM",
  construction: "시공·적산",
  feasibility: "사업성·분양",
  finance: "개발금융",
  esg: "ESG",
  permit: "인허가 검토",
  report: "보고서",
  operations: "운영",
};

/** storylineStage 표시 순서(스토리라인 위상순) — 그룹 정렬 결정성. */
const STAGE_ORDER: LifecycleStage[] = [
  "site-analysis",
  "legal",
  "permit",
  "design",
  "bim",
  "construction",
  "feasibility",
  "finance",
  "esg",
  "report",
  "operations",
];

/**
 * nodesToOptions가 현재 상태(신선/폐포 강제)를 판정하기 위해 받는 어댑터 컨텍스트.
 * store/엔진을 직접 import하지 않고 콜백으로 주입받아 순수성을 유지한다(테스트 용이).
 */
export interface SelectorAdapterCtx {
  /** 노드가 이미 최신이라 재실행이 불필요한가(신선분 스킵 → "최신(스킵)" 표기). */
  isFresh: (id: NodeId) => boolean;
  /**
   * 현재 선택(picked)의 폐포가 이 노드를 "강제 포함"하는가(상류 의존).
   * true면 사용자가 직접 끌 수 없으므로 locked 처리("의존 항목(자동 포함)").
   * 선택되지 않은 noise까지 잠그지 않도록, picked 자신은 false를 돌려주도록 호출측이 구성한다.
   */
  isClosureForced: (id: NodeId) => boolean;
}

/**
 * 레지스트리 노드 → AnalysisModuleOption[]. storylineStage로 그룹핑한다.
 *
 * @param nodeIds  표시할 노드(scope). 보통 한 워크스페이스가 다루는 NodeId[].
 * @param feeOf    billingKey → 코인(원). = balance.module_fees?.[k] ?? 0 (★하드코딩 금지).
 * @param ctx      신선/폐포 강제 판정 콜백.
 * @returns        그룹(분류)당 1개 부모 옵션 + 자식 옵션들(3-state). 단일 노드 그룹도 그룹으로 묶어 일관 표시.
 */
export function nodesToOptions(
  nodeIds: NodeId[],
  feeOf: (billingKey: string) => number,
  ctx: SelectorAdapterCtx,
): AnalysisModuleOption[] {
  // scope 내 노드만, 유효한 것만(레지스트리 정합은 lint 강제).
  const scoped = nodeIds.filter((id) => !!BY_ID[id]);

  // storylineStage별로 묶는다(표시순 STAGE_ORDER 유지).
  const byStage = new Map<LifecycleStage, NodeId[]>();
  for (const id of scoped) {
    const stage = BY_ID[id].storylineStage;
    if (!byStage.has(stage)) byStage.set(stage, []);
    byStage.get(stage)!.push(id);
  }

  const groups: AnalysisModuleOption[] = [];
  for (const stage of STAGE_ORDER) {
    const ids = byStage.get(stage);
    if (!ids || ids.length === 0) continue;
    // 그룹 내 노드는 storyOrder 오름차순(스토리라인 진행순).
    ids.sort((a, b) => BY_ID[a].storyOrder - BY_ID[b].storyOrder);

    const children = ids.map((id) => nodeToOption(BY_ID[id], feeOf, ctx));

    // 자식이 1개뿐인 그룹도 부모(분류)로 감싸 시선축을 단일화한다(셀렉터 3-state 일관).
    groups.push({
      key: `group:${stage}`,
      label: STAGE_GROUP_LABEL[stage] ?? stage,
      children,
    });
  }
  return groups;
}

/** 단일 노드 → 옵션(자식). 신선/미가용/폐포강제를 정직 표기로 변환한다. */
function nodeToOption(
  node: AnalysisNode,
  feeOf: (billingKey: string) => number,
  ctx: SelectorAdapterCtx,
): AnalysisModuleOption {
  const fresh = ctx.isFresh(node.id);
  // available:false(audit) 또는 폐포 강제(상류 의존) → locked. 둘 다 더미수치 금지·정직 라벨.
  const unavailableLocked = !node.available;
  const closureLocked = !unavailableLocked && ctx.isClosureForced(node.id);
  const locked = unavailableLocked || closureLocked;

  // 코인: 관리자 요율(미설정 0=무료). billingKey 없으면 과금 없음(0).
  const coinCost = node.billingKey ? feeOf(node.billingKey) : 0;

  // required = land(부지=모든 분석 사실근거 루트). 단, locked가 우선(중복 표기 방지).
  const required = node.id === "land" && !locked;

  return {
    key: node.id,
    label: node.label,
    description: describeNode(node, fresh, unavailableLocked, closureLocked),
    coinCost,
    // estimatedSeconds는 레지스트리 메타에 없으므로 미표기(블루프린트 §3-A: "노드 메타(없으면 미표기)").
    required,
    locked,
    lockedCtaLabel: locked
      ? unavailableLocked
        ? "심의엔진 연동 예정"
        : "의존 항목(자동 포함)"
      : undefined,
    icon: nodeIcon(node),
  };
}

/** 노드 설명 — 신선/미가용 상태를 정직하게 표기(0 강제·더미 금지). */
function describeNode(
  node: AnalysisNode,
  fresh: boolean,
  unavailableLocked: boolean,
  closureLocked: boolean,
): string {
  if (unavailableLocked) {
    // available:false 노드는 reportContract.unavailableLabel을 정직 표기.
    return node.reportContract.unavailableLabel || "현재 이용 불가";
  }
  if (closureLocked) {
    return "선택한 분석이 의존하는 상류 항목 — 자동 포함됩니다.";
  }
  if (fresh) {
    return "최신(스킵) — 이미 산출되어 재실행·재과금하지 않습니다.";
  }
  // 평시: 그라운딩 출처를 간략 표기(사실근거 투명성).
  const src = node.groundingSources.slice(0, 2).join("·");
  return src ? `근거: ${src}` : node.label;
}

/** 노드 아이콘 키 → 표시용 Lucide 아이콘(순수 표시·직관). 미지정은 일반 분석 아이콘. */
function nodeIcon(node: AnalysisNode): LucideIcon {
  switch (node.id) {
    case "land":
      return MapIcon;
    case "legal":
      return Scale;
    case "recommend":
      return Compass;
    case "design":
      return Ruler;
    case "audit":
      return Search;
    case "sales":
      return Tag;
    case "qto":
      return Blocks;
    case "feasibility":
      return BarChart3;
    case "finance":
      return Landmark;
    default:
      return LayoutGrid;
  }
}
