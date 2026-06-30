# 네비게이션·정보구조(IA) 시스템 — 기본개념

> 모든 메뉴·서브메뉴·페이지 내 탐색이 따르는 **단일 기준**. 새 메뉴/기능을 추가할 때 이 문서의 규칙을
> 적용한다. 구현 참조: `apps/web/lib/navigation/route-registry.ts`(비시각 SSOT),
> `apps/web/components/layout/nav-config.tsx`(아이콘 매핑·활성 판정 헬퍼),
> `apps/web/components/layout/SidebarNav.tsx`(접이식 재귀 렌더러).

## 1. 핵심 원칙
1. **최대 3계층** — 섹션(L1) → 항목/그룹(L2) → 하위메뉴(L3). 4계층 이상 금지(깊으면 재분류).
2. **그룹화 우선(나열식 금지)** — 같은 분류의 작업은 부모 아래 `children`으로 중첩한다. `"└ "` 같은
   문자 prefix로 계층을 흉내내지 않는다(진짜 트리 노드로).
3. **접이식(accordion)** — L1 섹션·L2 그룹은 접기/펼치기. 활성 경로의 섹션·그룹은 자동 펼침,
   펼침 상태는 `localStorage`(`propai-nav-expanded`)에 기억.
4. **활성 경로 강조** — 현재 항목은 강조(accent), 조상 섹션/그룹도 트레일 강조.
5. **단일 출처(SSOT)** — 라우트·라벨·상태·범위·API 의존성은 `route-registry`에 정의한다.
   `nav-config`는 registry에 아이콘을 입혀 기존 SidebarNav 형식으로 변환한다. 데스크톱 사이드바·모바일
   드로어·사이트맵·대시보드 바로가기는 같은 registry에서 파생한다.
6. **공간 효율** — 섹션은 기본 펼침이되 L2 그룹은 기본 접힘(활성만 펼침)으로 길이를 압축. 항목이
   7개를 넘는 섹션은 L2 그룹으로 분할을 우선 검토.
7. **밀도·일관성** — 아이콘+라벨, 일정한 들여쓰기 + 커넥터 라인(L3), 문장형 라벨, 이모지·장식 노이즈
   금지(아이콘으로 대체). 한 줄 라벨은 truncate.

## 2. 데이터 모델

### RouteRegistryItem
```ts
type RouteRegistryItem = {
  id: string;
  label: string;
  sectionId: PrimaryNavSectionId;
  parentId?: string;
  path?: `/${string}`;
  order: number;
  iconKey?: string;
  status: "live" | "beta" | "placeholder" | "hidden";
  scope: "global" | "project" | "admin";
  lifecyclePhase: LifecyclePhase;
  adminOnly?: boolean;
  assetOpsOnly?: boolean;
  apiDependencies?: string[];
};
```
- registry는 비시각 데이터만 가진다. React 아이콘은 `nav-config`에서만 매핑한다.
- `status`가 `hidden`이 아니면서 `path`가 있는 항목은 사이트맵/완성도 검증 대상이다.
- `apiDependencies`는 향후 페이지별 live/mock/empty/error 상태 검증의 기준으로 사용한다.

### NavNode
```ts
type NavNode = {
  id: string;            // 안정 키(상태기억·테스트용)
  label: string;
  href?: string;         // 리프, 또는 자체 페이지를 가진 그룹
  icon?: React.ReactNode;
  children?: NavNode[];  // 있으면 L2 그룹(펼침/접힘)
};
type NavSection = {       // L1
  id: string; title: string; items: NavNode[];
  adminOnly?: boolean; assetOpsOnly?: boolean;  // 역할 게이팅
};
```
- 그룹 노드가 `href`도 가지면: 라벨 클릭=이동, 셰브론 클릭=펼침/접힘.
- 게이팅은 섹션 단위(`adminOnly`/`assetOpsOnly`) — 서버 tier(`/auth/is-admin`) 기반, 미확인 시 숨김.

## 3. 활성·자동펼침 규칙(결정론, 순수함수)
- `isHrefActive(href, path)`: 정확 일치 또는 하위경로(`path`가 `href + "/"`로 시작). 홈(`/{locale}`)은
  모든 경로의 접두이므로 **정확 일치만**(오활성 방지).
- `nodeHasActive(node, path)`: 자신 또는 임의 후손이 활성.
- `activeGroupIds`/`activeSectionIds`: 자동 펼침 대상. 그룹은 자신 또는 후손 활성 시 펼침.
- 모두 `nav-config.tsx`의 순수함수 — vitest(`nav-config.test.ts`)로 검증.

## 4. 현재 1차 네비 구조(통합 IA)
- **관제**: 중앙분석센터 · 90초 사업성 진단
- **프로젝트**: 프로젝트 관리 · [토지·권리 ▸ 토지조서/등기부등본 열람/AI 시세추정 보고서] · [사업성·비용 ▸ 투자 수익성/공사비 분석]
- **시장·획득**: [시장·분양 ▸ 시장·시세 분석/분양정보] · [사업 획득 ▸ 경매·공매/공공입찰] · [인허가·규제 ▸ 인허가 가능성/개발 규제]
- **설계 센터**: AI 설계도면(CAD) · AI 설계분석 · AI 심의분석 엔진 · 3D 모델·공사물량 · 프로젝트 회의방 · 표준설계 라이브러리
- **운영 센터**(게이팅): 디지털 트윈 · 임대·임차인 관리 · 임차인 포털 · 시설 유지보수
- **관리**(게이팅): 관리자 설정 · 사용자 관리 · 과금 금액 설정 · 편집 목록 관리

## 5. 확장 지침(새 메뉴 추가 시)
1. 어느 L1 섹션에 속하는가? 없으면 새 섹션은 신중히(섹션 7개 이내 권장).
2. 관련 항목이 2개 이상이면 L2 그룹으로 묶는다(나열 금지).
3. `route-registry`에 먼저 추가하고, 새 아이콘 키가 필요할 때만 `nav-config`의 아이콘 매핑을 수정한다.
4. id는 안정적·유일하게. 라벨은 문장형·이모지 금지.
5. **페이지 내 탭/서브내비도 같은 개념**(섹션→항목→하위)을 따른다. 프로젝트 상세 탭 등 후속 화면은
   동일 NavNode 개념을 재사용해 일관 구조를 유지한다.

## 6. 설계 센터 페이지 셸
- 설계 센터 L1에 속한 독립 페이지는 `DesignCenterPageFrame`을 사용한다.
- 페이지 상단은 큰 랜딩 히어로가 아니라 **작업 상태 헤더 + 핵심 메트릭 + sibling tab**으로 구성한다.
- sibling tab은 `route-registry`의 `design-center` 항목에서 파생한다. 사이드바와 별개로 현재 설계센터 안에서
  다음 작업으로 이동하는 짧은 경로를 제공한다.
- 프로젝트 선택이 필요한 화면은 `DesignCenterEmptyState`를 사용해 같은 빈 상태, 같은 프로젝트 CTA를 제공한다.
- 내부 워크스페이스는 기존 기능을 유지하되 중복 페이지 히어로는 숨기거나 제거한다.
