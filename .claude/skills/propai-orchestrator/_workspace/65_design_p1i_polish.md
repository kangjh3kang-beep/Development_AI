# Phase 1-I — 분양 현장앱 디자인 폴리시 (sales-app)

목표: Phase 1에서 구축한 분양 현장앱(sales-app, 설치형 PWA) 화면의 세련도·가독성·직관성 극대화.
제약: **기능 무파괴**(엔드포인트·props·상태로직 불변, 시각/레이아웃/마이크로인터랙션만 개선), **다크 모드 기본**, **100% 디자인 토큰**(하드코딩 저대비 금지), push·배포 금지.

---

## 1. 조사 결과

### 디자인 토큰 (SSOT)
- 정의 위치: `packages/ui/src/styles/tokens.css` (앱 `app/layout.tsx`에서 `@propai/ui/styles/tokens.css` import).
- 가독성 보정 레이어: `apps/web/app/globals.css` 의 `:where(.dark) @layer utilities`(저대비 하드코딩 일괄 상향) — **존중·확장만**.
- 핵심 변수: 배경 `--background/--surface/--surface-strong/--surface-soft/--surface-muted`, 텍스트 `--text-primary/secondary/tertiary/hint`, 보더 `--line/--line-strong/--line-subtle`, 액센트 `--accent/--accent-strong(#3b82f6 다크)/--accent-soft`, 상태 `--status-success/warning/error/info`, 그림자 `--shadow-xs~2xl`, 라운드 `--radius-sm~2xl`, 트랜지션 `--ease-out-expo/--duration-fast/normal/slow`.

### 대상 컴포넌트(현황: 이미 토큰 기반·모바일 인지 양호)
- `components/sales-app/`: SiteListClient, SiteWorkspaceClient(13탭), StaffOverviewPanel, SocialPanel, MarketProfilePanel, JobMarketPanel, CommissionDutchPay, TerminationCertPanel, ReferralSharePanel, InstallGuide, roleConfig.ts
- `components/sales/`: UnitLiveBoard(세대배치도), CrmPanel, CustomerCardDrawer, WorkLogPanel 등
- `components/desk/`: DeskCheckin, VisitorStats

진단: 코드 일관성·토큰 사용이 이미 높음. 주요 갭은 (a)13탭 모바일 wrap 깨짐, (b)터치타깃 <44px, (c)카드 위계·hover 피드백 약함, (d)상태색이 컴포넌트별 raw Tailwind 산발, (e)빈상태/스켈레톤 톤 불일치.

---

## 2. 변경 파일 · 화면별 개선점

| 파일 | 개선 |
|------|------|
| `app/globals.css` | **sales-app 디자인시스템 레이어 신설**(`@layer components`, 전부 opt-in 클래스·100% 토큰): `.sa-tabbar`(가로스크롤·스냅·좌우페이드), `.sa-tab`(터치타깃 44px·활성 data-active), `.sa-seg/.sa-seg__item`(세그먼트 컨트롤), `.sa-card`(hover lift+active press), `.sa-chip --success/warning/error/info/accent/muted`(토큰 의미색 칩), `.sa-dot`(상태 도트), `.sa-skeleton`(셔머 로딩), `.sa-empty/.sa-empty__icon`(빈상태 일러스트), `.sa-chatbar`(하단 고정+세이프에어리어), `.sa-bubble-me`(말풍선 그림자) |
| `sales-app/roleConfig.ts` | `SalesTabDef.icon` 추가 + 13탭 전부 직관 아이콘(순수 데이터·표시용) |
| `sales-app/SiteWorkspaceClient.tsx` | 탭바를 **가로 스크롤 sticky 탭바**(`.sa-tabbar/.sa-tab`)+아이콘+ARIA(role=tab/aria-selected)로 교체. 헤더 액션버튼 터치타깃 40px·active scale. 에러/로딩 토큰화(`--status-error`/`.sa-skeleton`) |
| `sales-app/SiteListClient.tsx` | 현장 카드 위계 강화(제목 15px·개발유형 노출·진입 CTA 화살표 hover 이동), 상태칩 의미색(OPEN=success/PREP=warning/CLOSED=muted), 헤더 아이콘 배지, 빈상태→`.sa-empty`, 스켈레톤→`.sa-skeleton`, 에러 토큰화 |
| `sales/UnitLiveBoard.tsx` | 통계 5칸 위계화(분양률=accent 주지표 강조, 나머지 의미색 도트), 툴바 sticky+backdrop, 토스트 토큰 의미색+아이콘+aria-live, 빈상태→`.sa-empty`, 로딩→`.sa-skeleton` |
| `sales-app/SocialPanel.tsx` | 말풍선 꼬리(rounded-br/bl-md)+내 말풍선 그림자, 입력바 하단 고정(`.sa-chatbar` 세이프에어리어)·전송/첨부 버튼 44px·aria-label |
| `sales-app/StaffOverviewPanel.tsx` | scope 토글→세그먼트 컨트롤(`.sa-seg`)+ARIA, 스켈레톤·에러 토큰화 |
| `sales/CrmPanel.tsx` | 현장별/통합 토글→세그먼트 컨트롤(`.sa-seg`)+ARIA |

---

## 3. 디자인시스템 일관화 방식 · 토큰 준수
- **단일 출처(`@layer components`)**: 탭/세그먼트/칩/카드/스켈레톤/빈상태/채팅바를 클래스로 정의 → 화면 간 톤 자동 통일. 컴포넌트는 클래스만 부착(마크업·로직 무관).
- **opt-in 원칙**: 새 클래스는 명시 부착한 곳에만 적용 → 기존 마크업·다른 화면 무영향(회귀 0).
- **색상 100% 토큰**: 신규 색은 전부 `var(--*)` 또는 `color-mix(in srgb, var(--status-*) n%, ...)`. 하드코딩 저대비/파스텔·흰글자 버튼 옅은배경 없음. 활성 탭/버튼은 `--accent-strong`(#3b82f6) + 흰 글자(AA-large 대비 보장).
- **globals.css 보정 레이어 존중**: 기존 `:where(.dark) @layer utilities` 미수정, 신규 레이어는 그 위에 추가만.

---

## 4. 기능 무파괴 검증 (git diff)
- **import 보존**: 변경 8파일 diff에서 `import`/`apiClient`/`salesApi`/`from "..."` 추가·삭제 라인 **0건**(linter import 삭제 함정 회피 확인).
- **호출/props/상태 불변**: `onClick/onChange/onKeyDown/setTab/setScope/loadBoard/doHold/api.*/apiClient.*` 등 핸들러·엔드포인트 호출 라인 변경 0건. 탭 활성 판정 `tab === t.key`는 inline className→`data-active`/`aria-selected`로 위치만 이동(동일 표현식, 기능 동치).
- 변경은 className·래퍼 div·표시용 아이콘·ARIA 속성에 한정.

---

## 5. 접근성
- 탭바 `role="tablist"`+탭 `role="tab"`/`aria-selected`, 세그먼트 동일 패턴.
- 터치타깃: 탭 44px, 채팅 전송/첨부 44px, 헤더 액션 40px(WCAG 2.5.5 권장 충족).
- 토스트 `aria-live="polite"`, 입력/첨부 `aria-label`, 장식 아이콘 `aria-hidden`.
- 대비: 활성=accent-strong+흰글자, 상태색은 토큰(다크/라이트 AA 보장). `prefers-reduced-motion`은 globals 전역 규칙이 셔머/트랜지션 무력화.

---

## 6. tsc / eslint + import 보존
- eslint(변경 8파일 한정, `--no-cache`): **EXIT 0**, 경고 0. (리포 전체 lint는 기존 3701 errors가 있으나 본 변경과 무관·pre-existing.)
- tsc(`pnpm run type-check`, 전체, `.next/cache` 정리+typegen+`tsc --noEmit`): **EXIT 0**.
- import·기능 라인 무변경: git diff로 확인(§4).

---

## 7. 커밋
- 메시지: `style(sales-app): Phase1-I 디자인 폴리시 — 현장앱 디자인시스템·핵심화면 가독/직관·모바일 우선(기능 무변경)`
- 해시: `ac89a117ebe0905b67a0cf4de0eceab3c5e77ad4` (8 files, +314/-98). push·배포 미수행(요구대로).

---

## 8. 미진 · 후속
- 추가 폴리시 후보(이번 미적용, 동일 시스템으로 확장 가능): MarketProfilePanel/JobMarketPanel(구인구직 카드), CommissionDutchPay(더치페이 표), TerminationCertPanel(증명서), ReferralSharePanel(퍼널 통계 막대), WorkLogPanel(업무일지), DeskCheckin/VisitorStats(데스크) — 동일 `.sa-*` 클래스 부착으로 톤 통일 권장.
- 세대배치도 raw Tailwind 상태색(COLOR 맵 emerald/amber/rose)은 기능·가독 양호하여 보존(globals 보정 레이어가 대비 보장). 차후 `.sa-chip` 의미색으로 통일 가능.
- CrmPanel/CustomerCardDrawer의 등급·이력 칩 raw 색도 동일하게 차후 토큰 통일 가능.
- 신규 npm 패키지 추가 0건.
