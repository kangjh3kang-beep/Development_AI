/**
 * Phase 1-A — 현장 역할/상태 라벨 및 기능키(feature) → 워크스페이스 탭 매핑(SSOT).
 * 백엔드 _ROLE_LABEL / _FEATURE_KEYS(_workspace/47 §3)와 정합. features[]가 게이팅 단일 출처다.
 */

import {
  Banknote,
  BarChart3,
  Briefcase,
  Building2,
  ConciergeBell,
  FileText,
  FolderTree,
  Home,
  Landmark,
  MessageCircle,
  NotebookPen,
  Receipt,
  RefreshCw,
  Share2,
  ShieldCheck,
  Ticket,
  TrendingUp,
  User,
  Users,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

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

/**
 * 현장 조직 node_type 라벨 SSOT — 백엔드 site_auth._ROLE_LABEL 정본과 1:1.
 *
 * ★봉합 배경(2026-07-22): 과거 같은 조직 노드가 조직도에선 DIRECTOR="이사"인데 수수료/더치페이
 *   화면에선 "본부장"(GM_DIRECTOR="총괄본부장")으로 표시돼, 한 사람의 직급이 화면마다 달랐다.
 *   정본은 로그인 역할 라벨(ROLE_LABEL)·백엔드와 동일한 '본부장(GM_DIRECTOR) > 이사(DIRECTOR)'.
 *   조직도·수수료·더치페이가 모두 이 한 부를 소비한다(재발 방지). MGM 등 도메인 전용 항목은
 *   소비처가 이 목록에 로컬로 덧붙인다(조직 node_type 이 아니므로 SSOT에 넣지 않는다).
 */
export const ORG_NODE_TYPES = [
  "AGENCY",
  "SUBAGENCY",
  "GM_DIRECTOR",
  "DIRECTOR",
  "TEAM_LEADER",
  "MEMBER",
] as const;
export type OrgNodeType = (typeof ORG_NODE_TYPES)[number];

export const NODE_TYPE_LABEL: Record<OrgNodeType, string> = {
  AGENCY: ROLE_LABEL.AGENCY, // 대행본사
  SUBAGENCY: ROLE_LABEL.SUBAGENCY, // 대행지사
  GM_DIRECTOR: ROLE_LABEL.GM_DIRECTOR, // 본부장
  DIRECTOR: ROLE_LABEL.DIRECTOR, // 이사
  TEAM_LEADER: ROLE_LABEL.TEAM_LEADER, // 팀장
  MEMBER: ROLE_LABEL.MEMBER, // 직원
};

/** node_type → 라벨(미등록 값은 원문 폴백). */
export const nodeTypeLabel = (t: string): string => NODE_TYPE_LABEL[t as OrgNodeType] ?? t;

/** { value, label }[] 옵션 — 조직도/수수료 select 공용. 기본은 전 조직 node_type. */
export const nodeTypeOptions = (
  types: readonly string[] = ORG_NODE_TYPES,
): { value: string; label: string }[] => types.map((value) => ({ value, label: nodeTypeLabel(value) }));

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
  /** 모바일 가로 스크롤 탭바 가독성용 아이콘(직관). 순수 표시용. */
  icon?: LucideIcon;
  /** 메뉴 헤더 1줄 설명(직관력) — 워크스페이스 상단 공통 헤더에 표시. */
  desc?: string;
}

// 탭 ↔ 기능키(feature) 매핑. feature는 백엔드 _FEATURE_KEYS(site_auth.py §_FEATURE_KEYS)와 정합:
//   dashboard·org·pricing·units·contracts·commission·customers·ads·reports·settings·site_password.
// 계약 후속 업무(청약/수납/대출/전매/세금)는 백엔드 'contracts' 기능키로 게이팅한다(별도 키 미정의).
export const SALES_TABS: SalesTabDef[] = [
  // 홈 — 역할별 랜딩 대시보드. 현장 멤버 전원 공통(alwaysOn)이며 기본 진입 탭이다.
  { key: "home", label: "홈", feature: "home", alwaysOn: true, icon: Home, desc: "오늘 할 일·핵심 지표·역할별 요약. 현장 실데이터 집계." },
  { key: "units", label: "세대 배치도", feature: "units", icon: Building2, desc: "동·호 배치·상태관리·지정/추첨. 세대 클릭으로 상태전이·특이사항·계약." },
  { key: "customers", label: "고객·상담", feature: "customers", icon: Users, desc: "방문·상담 고객 관리와 등급·배정." },
  // Phase 1-D — 업무일지. 현장 멤버 전원 공통(alwaysOn): 일자별 작성·실적집계.
  { key: "worklog", label: "업무일지", feature: "worklog", alwaysOn: true, icon: NotebookPen, desc: "일자별 업무 기록과 실적 집계." },
  { key: "pricing", label: "분양가", feature: "pricing", icon: Wallet, desc: "적정분양가 추천 → 기준단가·가중치 설정 → 그룹 일괄 → 세대 가격표." },
  { key: "subscription", label: "청약·당첨", feature: "contracts", icon: Ticket, desc: "청약 접수·추첨·당첨자 관리." },
  { key: "payments", label: "수납·납부", feature: "contracts", icon: Receipt, desc: "계약자별 납부·연체·할인·환급 현황." },
  { key: "loan", label: "중도금 대출", feature: "contracts", icon: Landmark, desc: "중도금 대출 프로그램·약정 관리." },
  { key: "resale", label: "전매·실거래", feature: "contracts", icon: RefreshCw, desc: "전매 신청·실거래 신고 관리." },
  { key: "tax", label: "세금·보증", feature: "contracts", icon: BarChart3, desc: "세금계산서·보증 관리." },
  { key: "org", label: "조직도", feature: "org", icon: FolderTree, desc: "대행사→본부장→팀→팀원 계층·인원 배정·팀 현황." },
  { key: "commission", label: "수수료", feature: "commission", icon: Banknote, desc: "수수료 책정·단계 배분·세금유형·지급." },
  { key: "desk", label: "방문 데스크", feature: "customers", icon: ConciergeBell, desc: "모델하우스 방문 체크인·집객 통계." },
  { key: "integrity", label: "무결성 가드", feature: "settings", icon: ShieldCheck, desc: "데이터 정합성 검증·이상 탐지." },
  { key: "projection", label: "시행사 통합", feature: "reports", icon: TrendingUp, desc: "보유 현장 통합 집계·연결결산(개인정보 제외)." },
  // 해촉증명서: 프리랜서뷰(내 증명서)는 현장 멤버 전원 공통(alwaysOn). 발급주체뷰는
  // 패널 내부에서 역할(시행/대행 본부장↑·admin)로 차등 노출한다.
  { key: "cert", label: "해촉증명서", feature: "cert", alwaysOn: true, icon: FileText, desc: "근무현장 일괄 해촉증명서 신청·발급(PDF/이미지)." },
  // Phase 1-E — 공통(PUBLIC) 마켓·프로필. 현장 무관 전역 컨텐츠라 features와 무관하게 전원 공통(alwaysOn).
  { key: "market", label: "구인구직", feature: "market", alwaysOn: true, icon: Briefcase, desc: "분양 인력 구인·구직 마켓." },
  { key: "profile", label: "내 프로필", feature: "profile", alwaysOn: true, icon: User, desc: "재사용 프로필·경력 관리." },
  // Phase 1-H — 소셜(친구·단톡·다중톡). 전역 토큰 기반(현장 무관)이라 전원 공통(alwaysOn).
  { key: "social", label: "소셜·채팅", feature: "social", alwaysOn: true, icon: MessageCircle, desc: "친구·단체 채팅·푸시 알림." },
  // Phase C — 공유·바이럴(MGM 추천코드·공유링크/QR·Web Share·퍼널통계). 실적 귀속은 개인별이라 전원 공통(alwaysOn).
  { key: "referral", label: "공유·홍보", feature: "referral", alwaysOn: true, icon: Share2, desc: "추천코드·공유링크/QR·퍼널 통계." },
  // 직원관리(집계): 관리역할 전용(STAFF_OVERVIEW_ROLES). 비관리역할엔 미노출.
  { key: "staff", label: "직원관리", feature: "staff", icon: Users, desc: "하위 조직 인원·실적 집계 관리." },
];

// Phase 1-E 직원관리(집계) 노출 역할 — 관리역할(대행본사·본부장·이사·팀장↑·시행·관리자).
// 백엔드 staff overview는 관리 권한 검증으로 추가 게이팅한다(여기선 메뉴 노출만 차등).
export const STAFF_OVERVIEW_ROLES = new Set([
  "SUPERADMIN",
  "DEVELOPER",
  "AGENCY",
  "SUBAGENCY",
  "GM_DIRECTOR",
  "DIRECTOR",
  "TEAM_LEADER",
]);

/** features[]로 노출 탭 필터링. alwaysOn 탭은 항상 포함. */
export function visibleTabs(features: string[]): SalesTabDef[] {
  const set = new Set(features ?? []);
  return SALES_TABS.filter((t) => t.alwaysOn || set.has(t.feature));
}

// ── 모바일 내비 IA(디자인 핸드오프 design_handoff_salesapp) — 하단 5탭 + 전체메뉴 4그룹 ──
// 하단 탭바 주 슬롯(홈/고객/배치도/수납) — 마지막 슬롯 '전체'는 FieldNav 가 상시 부착한다.
// 역할별 노출은 visibleTabs 결과와 교집합(예: MEMBER 는 payments 미노출 → 3슬롯+전체).
export const BOTTOM_NAV_KEYS = ["home", "customers", "units", "payments"] as const;

/** 전체메뉴 시트의 4그룹(IA SSOT) — 각 그룹의 탭 키. 노출은 visibleTabs 와 교집합으로 판정. */
export const MENU_GROUPS: { title: string; keys: string[] }[] = [
  { title: "Sales", keys: ["units", "customers", "pricing", "subscription"] },
  { title: "Money", keys: ["payments", "loan", "resale", "tax"] },
  { title: "Operations", keys: ["worklog", "desk", "integrity", "projection", "org", "commission", "staff", "cert", "market"] },
  { title: "My", keys: ["profile", "social", "referral"] },
];
