// 분석 오케스트레이션 — 식별자 3집합 봉합 어댑터
// Phase B 블루프린트 §5-A 정합. store LifecycleStage(11, kebab) ↔ NodeId(9) ↔ LifecycleStageViews StageType(8, snake).
//
// 쉬운 설명: 같은 "단계"를 부르는 이름이 코드 곳곳에서 다르다(라이프사이클 11단계, 분석노드 9개, 화면탭 8개).
// 이 파일이 셋을 한 표로 묶어, 진행레일 상태 집계와 화면탭 배선이 어긋나지 않게 한다.
// node.storylineStage가 SSOT이고, 이 맵은 그 미러다(일관성은 lint-node-registry가 검사).

import type { NodeId, LifecycleStage } from "./types";
import { NODES } from "./node-registry";

/**
 * LifecycleStageViews(컴포넌트)의 비공개 StageType(8)과 정합하는 로컬 미러.
 * 컴포넌트 미수정 원칙상 직접 import하지 않고, 검증된 8값을 여기 선언한다(코드 대조: LifecycleStageViews.tsx L30-38).
 */
export type StageType =
  | "site_analysis"
  | "legal_compliance"
  | "design_ai"
  | "feasibility"
  | "esg_dashboard"
  | "permit_portal"
  | "construction"
  | "operations";

/**
 * LifecycleStage(11) → 그 단계에 속한 노드들. 진행레일 상태 집계용.
 * node.storylineStage를 역집계해 생성(드리프트 0). bim/esg/report/operations는 B1 노드 미배치 → [].
 */
export const STAGE_TO_NODES: Record<LifecycleStage, NodeId[]> = (() => {
  const map: Record<LifecycleStage, NodeId[]> = {
    "site-analysis": [],
    legal: [],
    design: [],
    bim: [], // design의 BIM 산출 — 별도 노드 없음
    construction: [],
    feasibility: [],
    finance: [],
    esg: [], // esg 노드 = B3 추가
    permit: [],
    report: [], // 보고서 = reportContract 수집(별도 노드 없음)
    operations: [], // 운영 노드 = B3 이후
  };
  for (const node of NODES) {
    map[node.storylineStage].push(node.id);
  }
  return map;
})();

/**
 * NodeId(9) → LifecycleStageViews 탭(StageType). 탭 배선용. 매핑 없으면 null.
 * 블루프린트 §5-A 표 정합:
 *   site-analysis→site_analysis / legal·recommend(permit)→legal_compliance·permit_portal /
 *   design·audit→design_ai / construction→construction / feasibility·sales→feasibility / finance→feasibility(금융 카드)
 */
export const NODE_TO_STAGETYPE: Record<NodeId, StageType | null> = {
  land: "site_analysis",
  legal: "legal_compliance",
  recommend: "permit_portal", // recommend는 permit 스토리라인(인허가 포털 탭)
  design: "design_ai",
  audit: "design_ai",
  sales: "feasibility",
  qto: "construction",
  feasibility: "feasibility",
  finance: "feasibility", // 금융 카드는 feasibility 탭 내 표시
};
