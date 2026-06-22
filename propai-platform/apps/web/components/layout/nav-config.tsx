/**
 * 좌측 네비게이션 단일 출처(SSOT) — IA 원칙(docs/design/navigation-ia-system.md) 구현.
 *
 * 최대 3계층: 섹션(L1) → 항목/그룹(L2) → 하위메뉴(L3). 관련 작업은 부모 아래 children으로 중첩한다
 * (나열식·"└" 문자 흉내 금지). 데스크톱 SidebarNav·모바일 드로어가 이 트리 하나를 공통 구동한다.
 */

import {
  IconAuction,
  IconCost,
  IconDashboard,
  IconDesign,
  IconMarket,
  IconPermit,
  IconProject,
  IconRegulation,
  IconROI,
  IconSRE,
} from "./nav-icons";

export type NavNode = {
  id: string;
  label: string;
  href?: string; // 리프이거나, 그룹이면서도 자체 페이지를 가질 때
  icon?: React.ReactNode;
  children?: NavNode[];
};

export type NavSection = {
  id: string;
  title: string;
  items: NavNode[];
  adminOnly?: boolean; // 관리자(admin/manager)만 노출
  assetOpsOnly?: boolean; // 자산운용/운영권한만 노출
};

/** 로케일별 1차 네비게이션 트리(L1 섹션 → L2 항목/그룹 → L3 하위메뉴). */
export function buildPrimaryNav(locale: string): NavSection[] {
  const p = (path: string) => `/${locale}${path}`;
  return [
    {
      id: "review",
      title: "사업 검토",
      items: [
        { id: "center", label: "중앙분석센타", href: `/${locale}`, icon: <IconDashboard /> },
        { id: "precheck", label: "90초 사업성 진단", href: p("/precheck"), icon: <IconPermit /> },
        // 종합 부지분석 — 주소 1개로 7개 카테고리 자동 보고서(자족형 패널, 프로젝트 없이 단독 실행)
        { id: "comprehensive-analysis", label: "종합 부지분석", href: p("/analysis"), icon: <IconProject /> },
        { id: "projects", label: "프로젝트 관리", href: p("/projects"), icon: <IconProject /> },
        {
          id: "market-sales",
          label: "시장·분양",
          icon: <IconMarket />,
          children: [
            { id: "market-insights", label: "시장·시세 분석", href: p("/market-insights") },
            { id: "sales-info", label: "분양정보", href: p("/sales-info") },
          ],
        },
        {
          id: "permit-reg",
          label: "인허가·규제",
          icon: <IconRegulation />,
          children: [
            { id: "permits", label: "인허가 가능성", href: p("/permits") },
            { id: "regulations", label: "개발 규제", href: p("/regulations") },
          ],
        },
        { id: "cost", label: "공사비 분석", href: p("/analytics/cost"), icon: <IconCost /> },
      ],
    },
    {
      id: "land-finance",
      title: "토지·자금",
      items: [
        {
          id: "land-schedule",
          label: "토지조서",
          href: p("/land-schedule"),
          icon: <IconProject />,
          children: [
            { id: "registry-analysis", label: "등기부등본 열람", href: p("/registry-analysis") },
            { id: "desk-appraisal", label: "AI 시세추정 보고서", href: p("/desk-appraisal") },
          ],
        },
        { id: "investment", label: "투자 수익성 (ROI)", href: p("/analytics/investment"), icon: <IconROI /> },
        { id: "auction", label: "경매·공매", href: p("/auction"), icon: <IconAuction /> },
        // 공공입찰(나라장터)은 경매·공매와 같은 '사업 획득 채널'이라 토지·자금에 둔다(IA 정합).
        { id: "g2b", label: "공공입찰 (나라장터)", href: p("/g2b"), icon: <IconAuction /> },
      ],
    },
    {
      id: "execution",
      title: "실행",
      items: [
        {
          id: "sales",
          label: "분양 현장 관리",
          href: p("/sales"),
          icon: <IconProject />,
          children: [
            { id: "sales-sites", label: "내 분양 현장(현장앱)", href: p("/sales/sites") },
            { id: "sales-projection", label: "분양관리요약(관리자)", href: p("/sales/projection") },
          ],
        },
      ],
    },
    {
      id: "design",
      title: "설계 참고",
      items: [
        { id: "design-studio", label: "AI 설계도면(CAD)", href: p("/design-studio"), icon: <IconDesign /> },
        { id: "design-audit", label: "AI 설계분석", href: p("/design-audit"), icon: <IconPermit /> },
        { id: "deliberation-review", label: "AI 심의분석 엔진", href: p("/deliberation-review"), icon: <IconRegulation /> },
        { id: "bim-studio", label: "3D 모델·공사물량(BIM·적산)", href: p("/bim-studio"), icon: <IconCost /> },
        { id: "meeting-rooms", label: "프로젝트 회의방", href: p("/meeting-rooms"), icon: <IconProject /> },
        { id: "design-refs", label: "표준설계 라이브러리", href: p("/settings/design-references"), icon: <IconDesign /> },
      ],
    },
    // 자산 운영(임대·임차인/임차인포털/시설유지보수/디지털트윈)은 준공 후 운영 단계로 현재 코어
    // 워크플로우(개발→분양)와 단절·미성숙해 네비에서 숨긴다. 라우트·컴포넌트는 보존(향후 복원 시
    // 아래 블록 주석 해제). assetOpsOnly 게이팅도 그대로 유지돼 있어 복원 즉시 운영역할에만 노출됨.
    // {
    //   id: "asset-ops",
    //   title: "자산 운영",
    //   assetOpsOnly: true,
    //   items: [
    //     { id: "lease", label: "임대·임차인 관리", href: p("/operations/lease"), icon: <IconProject /> },
    //     { id: "tenant", label: "임차인 포털", href: p("/tenant"), icon: <IconProject /> },
    //     { id: "maintenance", label: "시설 유지보수", href: p("/maintenance"), icon: <IconSRE /> },
    //     { id: "digital-twin", label: "디지털 트윈", href: p("/digital-twin"), icon: <IconDesign /> },
    //   ],
    // },
    {
      id: "admin",
      title: "관리",
      adminOnly: true,
      items: [
        { id: "settings", label: "관리자 설정", href: p("/settings"), icon: <IconSRE /> },
        { id: "users", label: "사용자 관리", href: p("/settings/users"), icon: <IconSRE /> },
        { id: "billing", label: "과금 금액 설정", href: p("/settings/billing"), icon: <IconSRE /> },
        { id: "lists", label: "편집 목록 관리", href: p("/settings/lists"), icon: <IconSRE /> },
      ],
    },
  ];
}

// ── 순수 헬퍼(활성 판정·자동 펼침) — 결정론, DOM/네트워크 무관(vitest) ──

const HOME_RE = /^\/[a-z]{2}(-[A-Z]{2})?$/;

/** 리프 활성 판정 — 정확 일치 또는 하위경로(홈 '/{locale}'은 모든 경로의 접두라 정확 일치만). */
export function isHrefActive(href: string | undefined, pathname: string): boolean {
  if (!href) return false;
  if (href === pathname) return true;
  if (HOME_RE.test(href)) return false;
  return pathname.startsWith(href + "/");
}

/** 노드가 활성 경로를 포함하는가(자신 또는 임의 후손). */
export function nodeHasActive(node: NavNode, pathname: string): boolean {
  if (isHrefActive(node.href, pathname)) return true;
  return (node.children ?? []).some((c) => nodeHasActive(c, pathname));
}

/** 자동 펼침할 그룹 노드 id 집합 — 자신 또는 후손이 활성인 그룹(그룹 자체 페이지 진입도 펼침). */
export function activeGroupIds(sections: NavSection[], pathname: string): string[] {
  const ids: string[] = [];
  const walk = (node: NavNode) => {
    const kids = node.children ?? [];
    if (kids.length && nodeHasActive(node, pathname)) ids.push(node.id);
    kids.forEach(walk);
  };
  for (const s of sections) s.items.forEach(walk);
  return ids;
}

/** 자동 펼침할 섹션 id 집합 — 활성 항목을 가진 섹션. */
export function activeSectionIds(sections: NavSection[], pathname: string): string[] {
  return sections
    .filter((s) => s.items.some((n) => nodeHasActive(n, pathname)))
    .map((s) => s.id);
}
