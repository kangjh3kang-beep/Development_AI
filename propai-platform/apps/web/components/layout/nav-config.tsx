/**
 * 워크스페이스 내비게이션 단일 출처(SSOT) — IA 원칙(docs/design/navigation-ia-system.md) 구현.
 *
 * 최대 3계층: 섹션(L1) → 항목/그룹(L2) → 하위메뉴(L3). 관련 작업은 부모 아래 children으로 중첩한다
 * (나열식·"└" 문자 흉내 금지). 상단 워크스페이스 바·모바일 드로어가 이 트리 하나를 공통 구동한다.
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
import {
  buildPrimaryRegistrySections,
  type RegistryNavNode,
} from "@/lib/navigation/route-registry";

export type NavNode = {
  id: string;
  label: string;
  href?: string; // 리프이거나, 그룹이면서도 자체 페이지를 가질 때
  icon?: React.ReactNode;
  children?: NavNode[];
  // 자주 쓰지 않는 무거운 라우트는 registry에서 false로 지정해 뷰포트 프리페치를 막는다.
  prefetch?: false;
};

export type NavSection = {
  id: string;
  title: string;
  items: NavNode[];
  adminOnly?: boolean; // 관리자(admin/manager)만 노출
  assetOpsOnly?: boolean; // 자산운용/운영권한만 노출
};

const NAV_ICONS: Record<string, React.ReactNode> = {
  auction: <IconAuction />,
  cost: <IconCost />,
  dashboard: <IconDashboard />,
  design: <IconDesign />,
  market: <IconMarket />,
  permit: <IconPermit />,
  project: <IconProject />,
  regulation: <IconRegulation />,
  roi: <IconROI />,
  sre: <IconSRE />,
};

function toNavNode(node: RegistryNavNode): NavNode {
  return {
    id: node.id,
    label: node.label,
    href: node.href,
    icon: node.iconKey ? NAV_ICONS[node.iconKey] : undefined,
    prefetch: node.prefetch,
    children: node.children?.map(toNavNode),
  };
}

/** 로케일별 1차 네비게이션 트리(L1 섹션 → L2 항목/그룹 → L3 하위메뉴). */
export function buildPrimaryNav(locale: string): NavSection[] {
  return buildPrimaryRegistrySections(locale).map((section) => ({
    id: section.id,
    title: section.title,
    adminOnly: section.adminOnly,
    assetOpsOnly: section.assetOpsOnly,
    items: section.items.map(toNavNode),
  }));
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
