/**
 * Platform route registry.
 *
 * This is the non-visual source of truth for primary IA, sitemap generation,
 * route status audits, and later dashboard shortcuts. Visual navigation maps
 * these records to icons in components/layout/nav-config.tsx.
 */

export type RouteStatus = "live" | "beta" | "placeholder" | "hidden";
export type RouteScope = "global" | "project" | "admin";
export type LifecyclePhase =
  | "control"
  | "intake"
  | "project"
  | "land-rights"
  | "market"
  | "acquisition"
  | "business"
  | "design"
  | "operations"
  | "admin";

export type PrimaryNavSectionId =
  | "control"
  | "projects"
  | "market-acquisition"
  | "design-center"
  | "operations-center"
  | "admin";

export interface PrimaryNavSectionMeta {
  id: PrimaryNavSectionId;
  title: string;
  order: number;
  adminOnly?: boolean;
  assetOpsOnly?: boolean;
}

export interface RouteRegistryItem {
  id: string;
  label: string;
  sectionId: PrimaryNavSectionId;
  order: number;
  parentId?: string;
  path?: `/${string}`;
  iconKey?: string;
  status: RouteStatus;
  scope: RouteScope;
  lifecyclePhase: LifecyclePhase;
  adminOnly?: boolean;
  assetOpsOnly?: boolean;
  prefetch?: false;
  apiDependencies?: string[];
}

export interface RegistryNavNode extends RouteRegistryItem {
  href?: string;
  children?: RegistryNavNode[];
}

export interface RegistryNavSection extends PrimaryNavSectionMeta {
  items: RegistryNavNode[];
}

export const PRIMARY_NAV_SECTIONS: PrimaryNavSectionMeta[] = [
  { id: "control", title: "관제", order: 10 },
  { id: "projects", title: "프로젝트", order: 20 },
  { id: "market-acquisition", title: "시장·획득", order: 30 },
  { id: "design-center", title: "설계 센터", order: 40 },
  { id: "operations-center", title: "운영 센터", order: 50, assetOpsOnly: true },
  { id: "admin", title: "관리", order: 60, adminOnly: true },
];

export const PRIMARY_ROUTE_REGISTRY: RouteRegistryItem[] = [
  {
    id: "center",
    label: "중앙분석센터",
    sectionId: "control",
    order: 10,
    path: "/",
    iconKey: "dashboard",
    status: "live",
    scope: "global",
    lifecyclePhase: "control",
    apiDependencies: ["/dashboard/kpi", "/projects"],
  },
  {
    id: "precheck",
    label: "90초 사업성 진단",
    sectionId: "control",
    order: 20,
    path: "/precheck",
    iconKey: "permit",
    status: "live",
    scope: "global",
    lifecyclePhase: "intake",
    apiDependencies: ["/precheck"],
  },
  {
    id: "comprehensive-analysis",
    label: "종합 부지분석",
    sectionId: "control",
    order: 30,
    path: "/analysis",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "control",
    apiDependencies: ["/analysis"],
  },
  {
    id: "projects",
    label: "프로젝트 관리",
    sectionId: "projects",
    order: 10,
    path: "/projects",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "project",
    apiDependencies: ["/projects"],
  },
  {
    id: "land-rights",
    label: "토지·권리",
    sectionId: "projects",
    order: 20,
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
  },
  {
    id: "land-schedule",
    label: "토지조서",
    sectionId: "projects",
    parentId: "land-rights",
    order: 10,
    path: "/land-schedule",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
    apiDependencies: ["/land-schedule"],
  },
  {
    id: "registry-analysis",
    label: "등기부등본 열람",
    sectionId: "projects",
    parentId: "land-rights",
    order: 20,
    path: "/registry-analysis",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
    apiDependencies: ["/registry/analyze"],
  },
  {
    id: "desk-appraisal",
    label: "AI 시세추정 보고서",
    sectionId: "projects",
    parentId: "land-rights",
    order: 30,
    path: "/desk-appraisal",
    status: "live",
    scope: "global",
    lifecyclePhase: "land-rights",
    apiDependencies: ["/desk-appraisal"],
  },
  {
    id: "business-analysis",
    label: "사업성·비용",
    sectionId: "projects",
    order: 30,
    iconKey: "roi",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
  },
  {
    id: "investment",
    label: "투자 수익성",
    sectionId: "projects",
    parentId: "business-analysis",
    order: 10,
    path: "/analytics/investment",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/analytics/investment"],
  },
  {
    id: "cost",
    label: "공사비 분석",
    sectionId: "projects",
    parentId: "business-analysis",
    order: 20,
    path: "/analytics/cost",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/analytics/cost"],
  },
  {
    id: "market-sales",
    label: "시장·분양",
    sectionId: "market-acquisition",
    order: 10,
    iconKey: "market",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
  },
  {
    id: "market-insights",
    label: "시장·시세 분석",
    sectionId: "market-acquisition",
    parentId: "market-sales",
    order: 10,
    path: "/market-insights",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/market"],
  },
  {
    id: "sales-info",
    label: "분양정보",
    sectionId: "market-acquisition",
    parentId: "market-sales",
    order: 20,
    path: "/sales-info",
    status: "live",
    scope: "global",
    lifecyclePhase: "market",
    apiDependencies: ["/presale"],
  },
  {
    id: "acquisition",
    label: "사업 획득",
    sectionId: "market-acquisition",
    order: 20,
    iconKey: "auction",
    status: "live",
    scope: "global",
    lifecyclePhase: "acquisition",
  },
  {
    id: "auction",
    label: "경매·공매",
    sectionId: "market-acquisition",
    parentId: "acquisition",
    order: 10,
    path: "/auction",
    status: "live",
    scope: "global",
    lifecyclePhase: "acquisition",
    apiDependencies: ["/auction"],
  },
  {
    id: "g2b",
    label: "공공입찰",
    sectionId: "market-acquisition",
    parentId: "acquisition",
    order: 20,
    path: "/g2b",
    status: "live",
    scope: "global",
    lifecyclePhase: "acquisition",
    apiDependencies: ["/g2b"],
  },
  {
    id: "permit-reg",
    label: "인허가·규제",
    sectionId: "market-acquisition",
    order: 30,
    iconKey: "regulation",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
  },
  {
    id: "permits",
    label: "인허가 가능성",
    sectionId: "market-acquisition",
    parentId: "permit-reg",
    order: 10,
    path: "/permits",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/permits"],
  },
  {
    id: "regulations",
    label: "개발 규제",
    sectionId: "market-acquisition",
    parentId: "permit-reg",
    order: 20,
    path: "/regulations",
    status: "live",
    scope: "global",
    lifecyclePhase: "business",
    apiDependencies: ["/regulations"],
  },
  {
    id: "design-studio",
    label: "AI 설계도면(CAD)",
    sectionId: "design-center",
    order: 10,
    path: "/design-studio",
    iconKey: "design",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/design"],
  },
  {
    id: "design-audit",
    label: "AI 설계분석",
    sectionId: "design-center",
    order: 20,
    path: "/design-audit",
    iconKey: "permit",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/design-audit"],
  },
  {
    id: "deliberation-review",
    label: "AI 심의분석 엔진",
    sectionId: "design-center",
    order: 30,
    path: "/deliberation-review",
    iconKey: "regulation",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/deliberation-review"],
  },
  {
    id: "bim-studio",
    label: "3D 모델·공사물량",
    sectionId: "design-center",
    order: 40,
    path: "/bim-studio",
    iconKey: "cost",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/bim"],
  },
  {
    id: "meeting-rooms",
    label: "프로젝트 회의방",
    sectionId: "design-center",
    order: 50,
    path: "/meeting-rooms",
    iconKey: "project",
    status: "live",
    scope: "global",
    lifecyclePhase: "design",
    apiDependencies: ["/collaboration"],
  },
  {
    id: "design-refs",
    label: "표준설계 라이브러리",
    sectionId: "design-center",
    order: 60,
    path: "/settings/design-references",
    iconKey: "design",
    status: "live",
    scope: "admin",
    lifecyclePhase: "design",
    prefetch: false,
    apiDependencies: ["/design-references"],
  },
  {
    id: "digital-twin",
    label: "디지털 트윈",
    sectionId: "operations-center",
    order: 10,
    path: "/digital-twin",
    iconKey: "design",
    status: "beta",
    scope: "global",
    lifecyclePhase: "operations",
    assetOpsOnly: true,
    apiDependencies: ["/digital-twin"],
  },
  {
    id: "lease",
    label: "임대·임차인 관리",
    sectionId: "operations-center",
    order: 20,
    path: "/operations/lease",
    iconKey: "project",
    status: "beta",
    scope: "global",
    lifecyclePhase: "operations",
    assetOpsOnly: true,
    apiDependencies: ["/lease"],
  },
  {
    id: "tenant",
    label: "임차인 포털",
    sectionId: "operations-center",
    order: 30,
    path: "/tenant",
    iconKey: "project",
    status: "beta",
    scope: "global",
    lifecyclePhase: "operations",
    assetOpsOnly: true,
    apiDependencies: ["/tenant"],
  },
  {
    id: "maintenance",
    label: "시설 유지보수",
    sectionId: "operations-center",
    order: 40,
    path: "/maintenance",
    iconKey: "sre",
    status: "beta",
    scope: "global",
    lifecyclePhase: "operations",
    assetOpsOnly: true,
    apiDependencies: ["/maintenance"],
  },
  {
    id: "settings",
    label: "관리자 설정",
    sectionId: "admin",
    order: 10,
    path: "/settings",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/settings"],
  },
  {
    id: "users",
    label: "사용자 관리",
    sectionId: "admin",
    order: 20,
    path: "/settings/users",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/auth/users"],
  },
  {
    id: "billing",
    label: "과금 금액 설정",
    sectionId: "admin",
    order: 30,
    path: "/settings/billing",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/billing"],
  },
  {
    id: "lists",
    label: "편집 목록 관리",
    sectionId: "admin",
    order: 40,
    path: "/settings/lists",
    iconKey: "sre",
    status: "live",
    scope: "admin",
    lifecyclePhase: "admin",
    adminOnly: true,
    prefetch: false,
    apiDependencies: ["/settings/lists"],
  },
];

export function localizedHref(locale: string, path: RouteRegistryItem["path"]): string | undefined {
  if (!path) return undefined;
  if (path === "/") return `/${locale}`;
  return `/${locale}${path}`;
}

export function buildPrimaryRegistrySections(locale: string): RegistryNavSection[] {
  const childrenByParent = new Map<string, RegistryNavNode[]>();
  const topLevelBySection = new Map<PrimaryNavSectionId, RegistryNavNode[]>();

  const nodes = PRIMARY_ROUTE_REGISTRY.map<RegistryNavNode>((item) => ({
    ...item,
    href: localizedHref(locale, item.path),
  }));

  for (const node of nodes) {
    if (node.parentId) {
      const children = childrenByParent.get(node.parentId) ?? [];
      children.push(node);
      childrenByParent.set(node.parentId, children);
    } else {
      const sectionItems = topLevelBySection.get(node.sectionId) ?? [];
      sectionItems.push(node);
      topLevelBySection.set(node.sectionId, sectionItems);
    }
  }

  const attachChildren = (node: RegistryNavNode): RegistryNavNode => {
    const children = (childrenByParent.get(node.id) ?? [])
      .sort((a, b) => a.order - b.order)
      .map(attachChildren);
    return children.length ? { ...node, children } : node;
  };

  return [...PRIMARY_NAV_SECTIONS]
    .sort((a, b) => a.order - b.order)
    .map((section) => ({
      ...section,
      items: (topLevelBySection.get(section.id) ?? [])
        .sort((a, b) => a.order - b.order)
        .map(attachChildren),
    }));
}

export function visibleRouteRegistryItems(): RouteRegistryItem[] {
  return PRIMARY_ROUTE_REGISTRY.filter((item) => item.status !== "hidden" && Boolean(item.path));
}
