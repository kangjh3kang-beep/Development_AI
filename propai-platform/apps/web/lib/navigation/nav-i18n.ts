/**
 * 내비게이션 라벨 로케일 사전 — **한 곳에서만 번역한다.**
 *
 * ★왜 생겼나(2026-08-16 실측): `route-registry.ts` 는 내비게이션 SSOT 인데 라벨이
 *   **한국어 하드코딩**이었다(항목 43/44 · 섹션 8/8). `buildPrimaryRegistrySections(locale)`
 *   은 `locale` 을 받으면서도 그걸 **`href` 에만** 썼다(`localizedHref`) — 라벨에는 쓰지 않았다.
 *   결과: `/en`·`/zh-CN` 로 들어온 사용자에게 **하위 내비게이션 전체가 한국어**로 나왔다.
 *
 *   e2e `project-release.spec.ts` 가 이걸 잡고 있었다. `getByRole("link", {name:"Finance"})`
 *   가 실패했고 실제 DOM 은 `link "금융분석"` 이었다(prod 빌드 로컬 재현으로 확인).
 *   "스펙이 낡았다"로 닫았으면 **실사용자에게 보이는 결함을 스펙 쪽에 덮었을** 것이다.
 *
 * ★설계: 기존 `public/locales/<로케일>/common.json` 의 `nav` 사전과 **겹치지 않는 별도 맵**이다.
 *   그쪽은 33개 키를 갖지만 레지스트리 id 와는 **3개만 겹쳤다**(실측) — 서로 다른 이름공간이라
 *   합치면 조용한 오매핑이 생긴다. 여기서는 **레지스트리 id 를 그대로 키로** 쓴다.
 *
 * ★ko 는 담지 않는다. 레지스트리의 `label` 이 곧 한국어 원문이고 **폴백**이다 —
 *   번역이 빠진 항목은 한국어로 나오되, 아래 회귀망이 그 누락을 빨강으로 만든다
 *   (`__tests__/nav-i18n.coverage.test.ts` 가 레지스트리에서 **파생**해 전수 검사한다).
 */

/** 번역이 필요한 로케일(ko 는 레지스트리 label 이 원문이므로 제외). */
export type TranslatedLocale = "en" | "zh-CN";

/** 레지스트리 항목 id → 로케일별 라벨. */
export const NAV_ITEM_LABELS: Record<string, Record<TranslatedLocale, string>> = {
  // ── 관제 ──────────────────────────────────────────────
  center: { en: "Analysis Center", "zh-CN": "中央分析中心" },
  precheck: { en: "90-Second Feasibility Check", "zh-CN": "90秒可行性诊断" },
  "comprehensive-analysis": { en: "Comprehensive Site Analysis", "zh-CN": "综合用地分析" },
  team: { en: "Subscription & Team", "zh-CN": "订阅与团队管理" },

  // ── 프로젝트 ──────────────────────────────────────────
  projects: { en: "Projects", "zh-CN": "项目" },
  "land-rights": { en: "Land & Rights", "zh-CN": "土地与权利" },
  "land-schedule": { en: "Land Schedule", "zh-CN": "土地清册" },
  "registry-analysis": { en: "Property Registry Lookup", "zh-CN": "不动产登记簿查询" },
  "desk-appraisal": { en: "AI Desk Appraisal Report", "zh-CN": "AI 估值报告" },
  "parcel-survey-quote": { en: "Pre-Issuance Cost Estimate", "zh-CN": "签发前费用估算" },
  investment: { en: "Investment Returns", "zh-CN": "投资收益" },

  // ── 적산·시공비 ───────────────────────────────────────
  cost: { en: "Cost Estimation & Construction Cost", "zh-CN": "造价与施工费管理" },

  // ── 시장·획득 ─────────────────────────────────────────
  "market-sales": { en: "Market & Sales", "zh-CN": "市场与销售" },
  "market-insights": { en: "Market & Price Analysis", "zh-CN": "市场行情分析" },
  "quick-survey": { en: "Quick Sales Feasibility Survey", "zh-CN": "简易销售可行性调查" },
  "realtx-report": { en: "Actual Transaction Filings", "zh-CN": "实际成交申报明细" },
  "market-ai": { en: "Conversational Market AI", "zh-CN": "对话式市场分析 AI" },
  "sales-info": { en: "Presale Information", "zh-CN": "销售信息" },
  acquisition: { en: "Business Acquisition", "zh-CN": "业务获取" },
  g2b: { en: "Public Bidding", "zh-CN": "公共招标" },
  auction: { en: "Auction Analysis", "zh-CN": "拍卖分析" },

  // ── 설계 센터 ─────────────────────────────────────────
  "design-studio": { en: "AI Design Drawings (CAD)", "zh-CN": "AI 设计图纸 (CAD)" },
  "design-audit": { en: "AI Design Review", "zh-CN": "AI 设计分析" },
  "deliberation-review": { en: "AI Deliberation Engine", "zh-CN": "AI 审议分析引擎" },
  "bim-studio": { en: "3D Model & Quantities", "zh-CN": "3D 模型与工程量" },
  "meeting-rooms": { en: "Project Meeting Rooms", "zh-CN": "项目会议室" },
  "design-refs": { en: "Standard Design Library", "zh-CN": "标准设计库" },
  "permit-reg": { en: "Permits & Regulations", "zh-CN": "许可与法规" },
  permits: { en: "Permit Feasibility", "zh-CN": "许可可行性" },
  // ★이 항목은 **회귀망이 잡아 추가됐다.** 내가 손수 뽑은 목록(43건)에 없었다 —
  //   레지스트리에서 파생해 전수 검사했기에 드러났다(목록형이었으면 그대로 새어 나갔다).
  regulations: { en: "Development Regulations", "zh-CN": "开发法规" },
  esg: { en: "ESG Analysis", "zh-CN": "ESG 分析" },

  // ── 분양 관리 ─────────────────────────────────────────
  "sales-mgmt": { en: "Sales Site Management", "zh-CN": "销售现场管理" },
  "sales-sites": { en: "My Sales Sites (Field App)", "zh-CN": "我的销售现场（现场应用）" },
  "sales-projection": { en: "Sales Summary (Admin)", "zh-CN": "销售管理摘要（管理员）" },

  // ── 마이페이지 ────────────────────────────────────────
  mypage: { en: "Account Summary", "zh-CN": "我的账户概览" },
  "mypage-coins": { en: "Credits & Payments", "zh-CN": "代币充值与支付记录" },
  "mypage-usage": { en: "AI Usage History", "zh-CN": "AI 使用记录" },
  "mypage-profile": { en: "Profile", "zh-CN": "个人资料管理" },
  "mypage-privacy": { en: "Privacy & Terms", "zh-CN": "隐私与条款" },
  "mypage-security": { en: "Account Security", "zh-CN": "账户安全" },

  // ── 관리 ──────────────────────────────────────────────
  settings: { en: "Admin Settings", "zh-CN": "管理员设置" },
  users: { en: "User Management", "zh-CN": "用户管理" },
  billing: { en: "Billing Rates", "zh-CN": "计费金额设置" },
  lists: { en: "Editorial List Management", "zh-CN": "编辑列表管理" },
  "learning-approval": { en: "AI Learning Example Approval", "zh-CN": "AI 学习案例审批" },
};

/** 섹션 id → 로케일별 제목. */
export const NAV_SECTION_TITLES: Record<string, Record<TranslatedLocale, string>> = {
  control: { en: "Control", "zh-CN": "管控" },
  projects: { en: "Projects", "zh-CN": "项目" },
  "cost-mgmt": { en: "Cost & Construction", "zh-CN": "造价与施工" },
  "market-acquisition": { en: "Market & Acquisition", "zh-CN": "市场与获取" },
  "design-center": { en: "Design Center", "zh-CN": "设计中心" },
  "sales-management": { en: "Sales Management", "zh-CN": "销售管理" },
  my: { en: "My Page", "zh-CN": "我的页面" },
  admin: { en: "Admin", "zh-CN": "管理" },
};

/**
 * 라이프사이클 단계 라벨 — **같은 결함이 두 번째 자리에도 있었다**(2026-08-16).
 *
 * `lib/lifecycle-stages.ts` 의 `STAGE_META[].label` 도 한국어 하드코딩이고,
 * 그 옆의 `stageRoute(locale, …)` 는 `locale` 을 **경로에만** 쓴다 — route-registry 와
 * 글자 그대로 같은 형태다. 프로젝트 상세의 진행레일(`LifecycleProgressRail`)이 이걸
 * 그리므로 `/en` 프로젝트 화면의 단계 링크가 전부 한국어였다.
 *
 * ★한 자리를 고칠 때 형제·미러를 함께 스윕한다 — 레지스트리만 고쳤으면 화면의
 *   절반은 그대로 한국어였고, 나는 "고쳤다"고 보고했을 것이다(실제로 그럴 뻔했다:
 *   레지스트리 봉합 후 e2e 를 다시 돌려 **DOM 이 안 바뀐 것**을 보고서야 알았다).
 */
export const STAGE_LABELS: Record<string, Record<TranslatedLocale, string>> = {
  "site-analysis": { en: "Site Analysis", "zh-CN": "用地分析" },
  legal: { en: "Legal Review", "zh-CN": "法规审查" },
  design: { en: "Design", "zh-CN": "设计" },
  bim: { en: "BIM", "zh-CN": "BIM" },
  construction: { en: "Construction Plan", "zh-CN": "施工计划" },
  feasibility: { en: "Feasibility", "zh-CN": "收支分析" },
  finance: { en: "Finance", "zh-CN": "金融分析" },
  esg: { en: "ESG", "zh-CN": "ESG" },
  permit: { en: "Permit", "zh-CN": "许可" },
  report: { en: "Report", "zh-CN": "报告" },
  operations: { en: "Operations", "zh-CN": "运营" },
};

function isTranslated(locale: string): locale is TranslatedLocale {
  return locale === "en" || locale === "zh-CN";
}

/** 라이프사이클 단계 라벨을 로케일로 옮긴다. 규칙은 `resolveNavLabel` 과 같다. */
export function resolveStageLabel(
  stage: string,
  koLabel: string,
  locale: string,
): string {
  if (!isTranslated(locale)) return koLabel;
  return STAGE_LABELS[stage]?.[locale] ?? koLabel;
}

/**
 * 라벨을 로케일로 옮긴다. 번역이 없으면 **한국어 원문을 그대로** 돌려준다 —
 * 화면이 비거나 id 가 새어 나오는 것보다 낫다(누락은 회귀망이 잡는다).
 */
export function resolveNavLabel(id: string, koLabel: string, locale: string): string {
  if (!isTranslated(locale)) return koLabel;
  return NAV_ITEM_LABELS[id]?.[locale] ?? koLabel;
}

/** 섹션 제목을 로케일로 옮긴다. 규칙은 `resolveNavLabel` 과 같다. */
export function resolveNavSectionTitle(id: string, koTitle: string, locale: string): string {
  if (!isTranslated(locale)) return koTitle;
  return NAV_SECTION_TITLES[id]?.[locale] ?? koTitle;
}
