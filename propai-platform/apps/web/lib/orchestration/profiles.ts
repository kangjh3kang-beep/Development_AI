// 분석 오케스트레이션 — 워크플로우 프로필 SSOT(L1 정식 스키마 + 프리셋)
// Phase B B5(프로필 모드) 정합. store(L2)·UI(L3)가 여기서 타입·프리셋·헬퍼를 가져다 쓴다.
//
// 쉬운 설명: "프로필"은 자주 쓰는 분석 묶음을 저장해 둔 워크플로우다.
// 예) 지주는 "토지·법률·개발방식·분양성"만 빠르게, 디벨로퍼는 "전 단계 풀패키지"처럼.
// 프리셋 4개는 코드에 박아둔 기본 워크플로우(수정·삭제 불가, 복제만 가능)이고,
// 사용자가 만든 워크플로우는 store에 저장(persist)된다. 이 파일은 "무엇이 프로필인가"의
// 단일 진실 출처(정식 타입)와 프리셋 상수, 그리고 프리셋+커스텀을 합치는 헬퍼만 담는다.
//
// 무목업: 프리셋 nodes/order는 실제 9노드 NodeId만 사용(node-registry 정합). 과금 없음(노드 billingKey만).

import type { NodeId } from "./types";

/** 프로필 식별자. 프리셋="preset:*", 사용자 커스텀=crypto.randomUUID(). */
export type ProfileId = string;

/**
 * 워크플로우 프로필 정식 스키마(SSOT).
 * store는 이 타입을 import해 쓰고 호환을 위해 re-export한다(기존 import 경로 보존).
 */
export interface WorkflowProfile {
  id: ProfileId;
  /** 화면 표시 이름. */
  label: string;
  /** 한 줄 설명(무엇을 빠르게/깊게 보는 워크플로우인지). */
  description: string;
  /** true=프리셋(코드 상수 — 수정·삭제 불가, 복제만). false=사용자 커스텀. */
  builtin: boolean;
  /** 선택 시드(leaf). 실행 시 엔진(computeClosure)이 상류로 자동 확장한다. */
  nodes: NodeId[];
  /** 표시·실행 순서(사용자 재배열 보존). 폐포 노드만 head로 끌어오는 순서 힌트. */
  order: NodeId[];
  /** 진입 시 기본 모드(가이드=전노드 안내, 선택=고른 것만). */
  defaultMode: "guided" | "selective";
  /** standalone 폴백 시 업스트림 자동실행 동의 기본값. */
  autoRunUpstream: boolean;
  /** 생성 시각(epoch ms). 프리셋은 0 고정(코드 상수라 시각 불필요). */
  createdAt: number;
}

/**
 * 프리셋 4종 — 실무 페르소나별 기본 워크플로우.
 * createdAt=0(코드 상수). builtin:true라 UI에서 수정·삭제 불가(복제만 노출).
 */
export const PRESET_PROFILES: WorkflowProfile[] = [
  {
    id: "preset:landowner-quick",
    label: "지주 빠른검토",
    description: "토지·법률·개발방식·분양성만 빠르게(수지·금융 제외)",
    builtin: true,
    nodes: ["land", "legal", "recommend", "sales"],
    order: ["land", "legal", "recommend", "sales"],
    defaultMode: "selective",
    autoRunUpstream: true,
    createdAt: 0,
  },
  {
    id: "preset:developer-full",
    label: "디벨로퍼 풀패키지",
    // finance 시드 → 폐포가 전 분석노드로 확장(audit은 말단검증이라 별도 비포함).
    description: "전 스토리라인 가이드(토지→금융+심의+적산)",
    builtin: true,
    nodes: ["finance"],
    order: ["land", "legal", "recommend", "design", "audit", "sales", "qto", "feasibility", "finance"],
    defaultMode: "guided",
    autoRunUpstream: true,
    createdAt: 0,
  },
  {
    id: "preset:pf-finance",
    label: "PF·금융중심",
    description: "수지·PF금융 중심(상류 자동충족)",
    builtin: true,
    nodes: ["feasibility", "finance"],
    order: ["land", "design", "qto", "sales", "feasibility", "finance"],
    defaultMode: "guided",
    autoRunUpstream: true,
    createdAt: 0,
  },
  {
    id: "preset:architect",
    label: "설계사",
    description: "설계·심의·적산 중심",
    builtin: true,
    nodes: ["design", "audit", "qto"],
    order: ["land", "legal", "recommend", "design", "audit", "qto"],
    defaultMode: "selective",
    autoRunUpstream: true,
    createdAt: 0,
  },
];

/** 프리셋 + 사용자 커스텀을 합쳐 전체 프로필 목록을 반환(프리셋 먼저). */
export function allProfiles(custom: WorkflowProfile[]): WorkflowProfile[] {
  return [...PRESET_PROFILES, ...custom];
}

/** id로 프로필 조회(프리셋 ∪ 커스텀). 없으면 undefined. */
export function findProfile(
  id: ProfileId | null,
  custom: WorkflowProfile[],
): WorkflowProfile | undefined {
  if (!id) return undefined;
  return allProfiles(custom).find((p) => p.id === id);
}
