/**
 * Phase 1-A — 현장 역할/상태 라벨 및 기능키(feature) → 워크스페이스 탭 매핑(SSOT).
 * 백엔드 _ROLE_LABEL / _FEATURE_KEYS(_workspace/47 §3)와 정합. features[]가 게이팅 단일 출처다.
 */

// 백엔드 _ROLE_LABEL 정합(폴백 라벨; 응답 role_label 우선).
export const ROLE_LABEL: Record<string, string> = {
  SUPERADMIN: "총괄관리자",
  DEVELOPER: "시행사",
  AGENCY: "대행본사",
  SUBAGENCY: "대행지사",
  GM_DIRECTOR: "본부장",
  DIRECTOR: "이사",
  TEAM_LEADER: "팀장",
  MEMBER: "직원",
};

export const STATUS_LABEL: Record<string, string> = {
  PREP: "준비중",
  OPEN: "분양중",
  CLOSED: "분양종료",
};

// 현장 비밀번호 설정/변경 권한 역할(백엔드 _MANAGE_ROLES 정합). can_manage 응답을 우선 신뢰.
export const MANAGE_ROLES = new Set(["SUPERADMIN", "DEVELOPER", "AGENCY", "GM_DIRECTOR"]);

/**
 * 워크스페이스 탭 정의. `feature`는 백엔드 features[] 기능키와 매핑된다.
 * features에 해당 키가 포함된 경우에만 탭을 노출한다(역할 차등 게이팅).
 */
export interface SalesTabDef {
  key: string;
  label: string;
  /** features[]에 이 키가 있어야 노출. 모든 멤버 공통 탭은 alwaysOn. */
  feature: string;
  alwaysOn?: boolean;
}

export const SALES_TABS: SalesTabDef[] = [
  { key: "dashboard", label: "현장 요약", feature: "dashboard", alwaysOn: true },
  { key: "units", label: "세대 배치도", feature: "units" },
  { key: "customers", label: "고객·상담", feature: "customers" },
  { key: "pricing", label: "분양가", feature: "pricing" },
  { key: "subscription", label: "청약·당첨", feature: "subscription" },
  { key: "payments", label: "수납·납부", feature: "payments" },
  { key: "commission", label: "수수료", feature: "commission" },
  { key: "org", label: "조직도", feature: "org" },
  { key: "settings", label: "현장 설정", feature: "manage" },
];

/** features[]로 노출 탭 필터링. alwaysOn 탭은 항상 포함. */
export function visibleTabs(features: string[]): SalesTabDef[] {
  const set = new Set(features ?? []);
  return SALES_TABS.filter((t) => t.alwaysOn || set.has(t.feature));
}
