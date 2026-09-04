# 랜딩페이지·전역 디자인 리팩토링 계획 — 통합 디자인시스템 v2.0 적용

작성: 2026-07-12 · 보강: 2026-07-12(2차 핸드오프 반영) · 기준: origin/main 97334d45
입력: ①1차 핸드오프(DESIGN.md v2.0·Landing Page.dc.html·hero-skyline.js·자산 7종) ②**2차 핸드오프(앱 화면 패키지)** — screens/*.dc.html **핵심화면 10종×다크/라이트 21파일** + 정식 **tokens.css**(다크 기본·`[data-theme="light"]` 파스텔) + 적용 README ③현행 실측(전수 조사)
원칙: 기존 자산 재사용 · 무목업(데모 카피 이식 금지) · additive 우선 · --accent-strong 이름 불변 계약 존중
★2차 핸드오프 상세 분석은 §6 — P2 확장(P2a/P2b)·결정사항 갱신의 근거.

---

## 0. 실측 진단 (계획의 전제 — 전부 file:line 검증됨)

### 0-1. 핸드오프 요지
- **Part A(랜딩·브랜드, Warm Amber)**: --ink #0E0E10·--paper #F4F4F2·--accent #C8873F 계열, Space Grotesk/Pretendard/JetBrains Mono, Lucide 라인 1.5px, pill 버튼·라벨, 12컬럼/1440px/72px, 7섹션 랜딩(히어로 비디오 720px·서비스 다크 넘버링·Why·프로젝트 카드·CTA 88px), 모션 600ms 표준.
- **Part B(앱, Nexus Geo-Intelligence 다크)**: surface #0a0c10~#282e39·--primary #135bec·--secondary #4cd7f6(인프라)·--tertiary #ffb95f(위험 인프라·A↔B 브릿지)·--ai-accent #a855f7(**AI 산출물 표시 전용**), 글래스(85%+blur12), 깊이 L0~L3.
- 경계 기준: **로그인 전=Part A / 로그인 후=Part B**. 금지 목록(D장): 이모지·filled 아이콘·Inter/Roboto·그라데이션 남발·데이터 슬롭 등.

### 0-2. 현행 구조 5대 발견(리팩토링 성패 좌우)
1. **토큰 이중 SSOT + 캐스케이드 역전(최대 리스크)**: `packages/ui/src/styles/tokens.css`의 `.dark` 블록은 **이미 Nexus 팔레트**(#11131b·--accent #135bec — 주석에 "Nexus Geo-Intelligence" 명기)인데, `apps/web/app/globals.css`의 `:root`(사통팔땅 라이트 v3.0)가 import 순서+동률 명시도로 **전부 덮어씀**. 게다가 테마 부트스트랩 부재(ThemeToggle이 localStorage 쓰기만·읽기 0) → **항상 라이트 부팅**. 즉 Part B는 "적용"이 아니라 **"사문화된 반입분의 소생+보강"**.
2. **--accent-strong 불변 계약**: 1,553회/295파일 소비+로고 그라디언트 직결(Logo.tsx:8-9). 이름 변경 불가 — **값 교체만 가능**(교체 시 AA 대비 재검증 필수).
3. **Tailwind v4 + 죽은 tailwind.config.ts**: `@config` 미지시라 JS 설정 미로딩 → `darkMode:"class"` 미적용 → **`dark:` 유틸 14파일이 media-query로 오동작 중**(잠복 버그). v4 `@custom-variant dark` 신설 필요.
4. **폰트 실로드 0**: --font-sans/display/mono는 이름뿐(전부 OS 폴백). 단 var(--font-*) 소비 배선(body·h1-h6·mono 14곳)이 살아 있어 **next/font 연결만으로 전역 승계**.
5. **마케팅 표면 부재**: (marketing) 그룹·middleware 없음. `/{locale}`=(dashboard) 홈이 미인증 공개(사실상 랜딩 겸용, saas-* 잉크+라임 히어로). 로그인 화면은 cc-* 커맨드센터 셸.

### 0-3. 기타 실측
- Lucide 이미 표준(134파일)·타 아이콘 0. **이모지 618회/154파일** 잔존(D장 위반).
- public/landing 없음·비디오 사용 0·next/image 4파일 vs `<img>` 22회.
- propai-platform/DESIGN.md(158줄)=이미 Part B 스펙(본문폰트만 Noto Sans로 상이) → "교체"의 실체는 **Part A 추가+폰트 교정+v2.0 산문 규칙 통합**.
- 재사용 자산: AnimatedCounter·TiltCard·GridBackground·GlassCard·StreamingText(소비 0)·framer-motion 46파일·saas-* 히어로 패턴·i18n 3locale.

---

## 1. 목표 아키텍처

```
로그인 전(Part A Warm Amber)                로그인 후(Part B Nexus 다크)
┌────────────────────────────┐             ┌────────────────────────────┐
│ /{locale} 랜딩(신규 7섹션)   │──CTA/로그인──▶│ (dashboard) 워크스페이스     │
│ (auth) 로그인·가입·온보딩     │             │ 지도·분석·CAD/BIM·적산...    │
│ legal/*                     │             │                            │
│ 토큰: mkt-*(Part A 스코프)   │             │ 토큰: 전역 .dark=Part B 정본  │
└────────────────────────────┘             └────────────────────────────┘
        공유: Space Grotesk/Pretendard/JetBrains Mono·Lucide·4px 스케일·pill 패턴
        브릿지: --tertiary #ffb95f(앰버) = 온보딩·요금제·마케팅 모달의 연속성 포인트
```

- **랜딩 진입(권고안)**: URL 구조 불변 — `/{locale}` 서버 컴포넌트에서 **인증상태 분기**(세션 無→신규 LandingPage(Part A)·有→기존 대시보드 홈). 근거: 딥링크/SEO/기존 테스트/공유링크 무파괴, 핸드오프의 "로그인 전=A" 기준과 정확히 일치. (대안: /landing 별도 라우트+미인증 리다이렉트 — IA 변경 커서 비권고)
- **토큰 3계층**: ①Part A는 `(marketing)`/auth 스코프 전용 `mkt-*` 네임스페이스(전역 오염 0) ②Part B는 tokens.css `.dark`를 v2.0으로 보강해 **전역 정본** ③기존 semantic 이름(--accent-strong 등)은 **이름 유지·값만 단계 교체**(별칭 레이어).

---

## 2. 로드맵 (P0 선행 필수 → P1/P2 병렬 가능 → P3 캠페인 → P4 검증)

### P0 — 기반 정지작업 (1일 · 이것 없이는 어떤 팔레트 변경도 무반응/오동작)
1. **토큰 SSOT 단일화**: globals.css `:root`의 tokens.css 중복 토큰(--background·--surface·--accent-strong·--glass-* 등)을 tokens.css로 수렴·globals는 파생/유틸만 — 캐스케이드 역전 해소. 회귀가드: 수렴 전후 주요 화면 computed-style diff 스크립트.
2. **`@custom-variant dark (&:where(.dark, .dark *))`** 신설(globals.css) + 죽은 tailwind.config.ts 처분(삭제 또는 @config 명시 — 삭제 권고·config 참조 0 실측). `dark:` 유틸 14파일 동작 재확인.
3. **테마 부트스트랩**: `<html>` inline script(FOUC 방지)로 localStorage→class 복원. 기본 테마 결정 필요(§3-②).
4. **폰트 셋업**: next/font/local — Pretendard Variable(수급: 공식 woff2)·Space Grotesk(구글)·JetBrains Mono → 기존 var(--font-sans/display/mono)에 연결(소비처 무수정 전역 승계). Noto Sans 표기 제거(DESIGN.md 포함).
5. DESIGN.md v2.0 교체(핸드오프본 — 기존 Part B 내용과 정합 확인: --primary #135bec/--primary-dim #b4c5ff 재정의 반영), viewport themeColor 정합, **sw 캐시 bump**(배포 관례).

### P1 — 랜딩페이지 구현 (Part A · 2~3일)
1. **자산**: `download-assets.sh` → `apps/web/public/landing/`(CDN 임시 URL이라 **즉시 실행**). hero.mp4 poster 프레임 추출·용량 확인(과대 시 압축), `hero-skyline.js`를 React 컴포넌트(HeroSkylineCanvas)로 이식해 **비디오 실패/절약모드 폴백** 배선.
2. **컴포넌트 트리**(`components/marketing/`): MarketingNav / HeroSection(비디오+`play().catch` 킥+스크림) / ServicesSection(다크 넘버링 리스트) / WhySection(2컬럼+이미지 3) / ProjectsSection(카드 3+캐러셀 준비) / CtaFooter. 인라인 스타일 스펙 → Tailwind+`mkt-*` 토큰으로 변환(README 섹션별 수치 준수: 히어로 720px·H1 112px·서비스 64px·CTA 88px·radius/여백/hover 계약).
3. **★카피 정본 = 2차 핸드오프 PropAI Main.dc.html**(사통팔땅 브랜드·"땅부터 준공까지, AI로 사통팔땅!"·전주기 모듈 4행·Why 스탯 카드 3·보고서 생성 패널(주소입력+보고서 4종 선택)·CTA "다음 프로젝트, 주소만 입력하세요"). 1차 "아키퍼" 레퍼런스는 레이아웃 참고로 강등. **무목업 잔여 치환**: 누적 분석 필지 214,000+·정확도 96%·30초 등 무근거 수치는 실측치 치환 또는 제거(§3-④), 보고서 생성 패널은 실 엔드포인트(주소검색→보고서 허브) 배선 전제.
4. **배선**: `/{locale}` 인증분기(§1 권고안), CTA→(auth)/login·register, 네비 활성상태, i18n(ko 우선·en/zh 키만 준비).
5. **품질**: SEO 메타+OG 이미지, 반응형(1200px 미만 단일 컬럼 스택 — min-width 강제 대신 우아한 축소), prefers-reduced-motion 시 비디오 정지+모션 제거, 대비 AA(특히 accent 텍스트 on 라이트 금지→accent-deep), LCP 예산(poster 우선 로드).
6. (선택) 로그인 화면 Part A 브릿지: cc-* 셸 유지하되 앰버 포인트 1개 도입 — 별도 결정.

### P2a — 전역 토큰·테마 기반 (Part B · 1~2일) ★2차 핸드오프로 확정 강화
1. **핸드오프 tokens.css를 정본으로 반입**(참조본: `_workspace/design_handoff/tokens.v2.css`): 다크 기본(`:root`) + 라이트 파스텔(`[data-theme="light"]` — 완전한 라이트 팔레트 제공됨: surface #F6F7FB·primary #7C98F2/#5570DE 등). --secondary/--tertiary/--ai-accent/status·글래스 blur 12px(현행 14/20px 충돌 해소)·**종이 문서 뷰 토큰 4종**(--paper #F7F6F1·--paper-ink·--paper-line·--paper-section — 등기부·보고서 미리보기 전용)·radius 체계(--r-input 4/--r-card 8/--r-panel 12/--r-pill 999).
2. **테마 스위칭 규약 통일**: 핸드오프=`data-theme` 속성 vs 현행=`.dark` 클래스. 권고=`[data-theme]`를 정본으로 채택하되 `@custom-variant dark`를 `[data-theme="dark"]`·`.dark` 겸용 셀렉터로 선언해 기존 `dark:` 유틸·:where(.dark) 패치 호환 유지. 테마 부트스트랩(P0-3)도 data-theme 기준으로.
3. **--accent-strong 값 교체**(#3b82f6→#135bec 계열): 이름 불변·값만. 흰 텍스트 버튼 AA 재검증 + 로고 그라디언트 육안 확인. P0 SSOT 단일화 이후에만 유효.
4. **--ai-accent 사용 규칙 배선**: AI 산출물 표시 컴포넌트(VerificationBadge·ai_interpretation 카드·인터프리터 섹션·SeniorVerdictCard AI 서술부)에만 — 일반 버튼/장식 금지(D장). ※2차 핸드오프 화면들이 실사용례 제공(CAD "AI Design Generation" 패널·내역서 AI 단가이상 배지·AI Insight 카드·AI 수정 채팅).
5. **공공데이터 고지 공용 컴포넌트**(DataSourceNotice): "모든 데이터 뷰 하단 출처·갱신일·참고용 문구"(2차 README 계약) — 기존 evidence 계약{value,basis,source,…}과 정합, 화면별 중복 문자열 금지.
6. `:where(.dark)` 가독성 패치(globals:1555-1579) 재검토·흡수. 사이드바 전역 강제 없음(화면별 계약: 헤더 64px·좌 dock 300~440px·우 패널 300~500px).

### P2b — 앱 핵심화면 10종 리스킨 캠페인 (신설 · PR 연작 · 화면당 0.5~1일)
2차 핸드오프의 하이파이 스펙(다크/라이트 쌍)을 **기존 기능 자산에 시각·레이아웃만 입히는** 캠페인. README 지침 준수: 레이아웃/값은 스펙대로 옮기되 **기존 컴포넌트를 데이터 소스로 연결**(SVG 데모 필지→실 Kakao/VWorld 레이어·데모 수치→실 API), dc-script 상태 로직(재계산·토글·필터)은 이식 참고. ★화면 내 데모 데이터(정자동 178-1·수치 전부)는 스펙 예시일 뿐 이식 금지(무목업).

| 우선 | 핸드오프 화면 | 기존 대상 자산 | 비고 |
|---|---|---|---|
| 1 | Satong Map | SatongMapShell(레이어 11종 기배선) | 좌 400px dock·우 레이어 rail+단일 팝오버·산출물 dock — 시각 리스킨 중심 |
| 1 | Dashboard | (dashboard) 프로젝트 홈·라이프사이클 | 5단계 스테퍼·KPI 4·모듈 6·리스크/활동 — 스테퍼는 현행 10단계와 매핑 결정 |
| 1 | Feasibility Studio | 투자분석 워크플로우·§12 프리셋(PR#242) | ★수지분석표 편집 뷰(구분/항목/기지급/미지급/산출근거/구성비·행 재배치·CSV)=신규 UI, 백엔드는 기존 rough/cashflow 계약 |
| 2 | Cost Estimation | 적산관리 허브(PR#220) | 핸드오프 WBS 9종 표기 ↔ 현행 WB12 SSOT — **현행 12단계 유지**·시각만 채택. 내역서 인라인 편집·재계산은 기존 계약 위 리스킨 |
| 2 | Land Registry | 토지조서(PR#226)·등기 provider | **종이 문서 뷰**(paper 토큰) 신규 패턴·동의 4종 체크 매트릭스 |
| 2 | Legal Review | 법규검토 워크스페이스·정북사선 헬퍼 | 31항목 테이블+필터·일조사선 단면 다이어그램·인허가 로드맵 |
| 3 | Report Studio | 통합 보고서 엔진(ReportModel 3렌더러) | 종류 4·섹션 체크·PDF/DOCX/PPTX·종이 미리보기·이력 |
| 3 | CAD Studio | DesignStudio·Konva·seed-design | AI 설계안 A/B/C·법규 게이지·AI 수정 채팅(기존 인터프리터 배선) |
| 3 | BIM Studio | 3D IFC/glb·QtoBreakdown | 모델트리 표시토글·충돌(Clash) 패널·BOQ 요약 |

- 캠페인 규약: 화면당 독립 PR(worktree)·기능 무변경(시각 diff만)·양테마 스크린샷 첨부·기존 계약(additive) 불변. 데모 수치 유입 CI 가드(예: "정자동 178-1" grep).

### P3 — 정리 캠페인 (별도 PR 연작 · 기계적)
1. **이모지 618회/154파일 → Lucide 치환**(D장): 기존 feat/emoji-to-svg-icons 브랜치 이력 재활용 검토, 도메인별 배치 PR(의미 아이콘만·장식 삭제).
2. `<img>` 22회 → next/image(랜딩 제외 후순위).
3. **안티패턴 가드**: CI grep 게이트(이모지 신규 유입·Inter/Roboto 폰트 선언·filled 아이콘 import) + DESIGN.md D장 링크.

### P4 — 검증·배포 (1일)
- 시각 회귀: 주요 20화면 스크린샷 전후 대조(agent-browser), 다크/라이트 양 테마.
- Lighthouse(랜딩 LCP/CLS — 비디오 poster·폰트 swap), axe 대비 검사.
- tsc·eslint·vitest 전체 무회귀, sw bump, A1 재빌드+라이브검증(랜딩 렌더·인증분기·비디오 재생·폴백 캔버스·기존 워크스페이스 무회귀).

---

## 3. 사용자 결정 — ★전건 확정(2026-07-12 사용자 회신): ①인증분기 ②다크 기본 ③accent-strong=P2a 일괄 ④PropAI Main 정본(무근거 수치 치환) ⑤P2b=맵/대시보드/수지 선행. 구현 착수 승인됨.
1. **랜딩 진입 방식**: 권고=인증분기(URL 불변). 대안=별도 라우트.
2. ~~앱 기본 테마~~ → **다크 기본 확정**(2차 핸드오프 tokens.css가 다크를 `:root` 기본으로 명시·라이트 파스텔은 `[data-theme="light"]` 전환). 잔여 확인: **라이트 파스텔이 기존 사통팔땅 라이트 테마를 대체**하는지(권고=대체 — 화면 21종이 파스텔 기준으로 설계됨).
3. **--accent-strong 값 교체 시점**: P2a 일괄(권고·SSOT 단일화 후 안전) vs 화면군 점진.
4. ~~랜딩 카피~~ → **PropAI Main.dc.html로 확정**(사통팔땅 브랜드·"땅부터 준공까지, AI로 사통팔땅!"·전주기 모듈 4행·보고서 생성 패널). 잔여: ★무근거 수치 3종 처리 — "누적 분석 필지 214,000+"·"법규 자동검토 정확도 96%"·"수지분석 30초"는 실측치로 치환 또는 검증 불가 시 제거/정성 표현(무목업).
5. **(신규) P2b 리스킨 캠페인 우선순위·범위 승인**: §P2b 표의 1→2→3 순 권고. 전 화면 일괄 vs 우선군만 선행.

## 4. 규모·리스크 요약 (2차 반영 개정)
- P0 1일 → P1 2~3일 ∥ P2a 1~2일 → **P2b 5~8일(화면 10종 캠페인·병렬 가능)** → P4 1일. P3은 별도 캠페인. 총 **10~15일**(1차 계획 6~8일에서 P2b 신설로 확대).
- 최대 리스크=P0 토큰 수렴(전 화면 영향) — computed-style diff+시각회귀 게이트. 다음=accent-strong 값 교체(295파일)·폰트 실로드 리플로우·**테마 규약 이원화(data-theme vs .dark) 불완전 통일 시 화면별 테마 파편화**.
- 1차 자산(CDN 임시) 확보 완료. 2차 앱 화면은 외부 이미지 의존 0(전부 코드 렌더) — 자산 리스크 없음.

## 5. 산출물 목록(구현 시)
- 신규: components/marketing/ 7종·HeroSkylineCanvas·mkt 토큰 블록·@custom-variant dark(data-theme/.dark 겸용)·테마 부트스트랩·next/font 셋업·public/landing 자산 7종·**DataSourceNotice(공공데이터 고지)·PaperDocumentView(종이 문서 뷰)**·CI 안티패턴 게이트(+데모수치 가드)
- 수정: tokens.css(핸드오프 v2 정본 반입: 다크 기본+라이트 파스텔+paper+radius)·globals.css(:root 중복 제거)·app/[locale] 인증분기·DESIGN.md 교체·tailwind.config 삭제·P2b 대상 화면 10종 리스킨
- 문서: DESIGN.md v2.0(SSOT)·`_workspace/design_handoff/tokens.v2.css`(참조본)·시각회귀 기준 스크린샷 세트(양테마)

---

## 6. 2차 핸드오프(앱 화면 패키지) 보강 분석 — 2026-07-12

### 6-1. 구성
`screens/` 핵심화면 10종 × 다크/라이트 파스텔 쌍(21파일: Dashboard·Satong Map·CAD Studio·BIM Studio·Feasibility Studio·Cost Estimation·Land Registry·Legal Review·Report Studio·PropAI Main/Landing) + 정식 `tokens.css` + 적용 순서 README. 각 화면 하단 dc-script에 상호작용 로직(상태·재계산·토글·필터·CSV 다운로드) 포함 — **이식 참고 스펙**(그대로 배포용 아님).

### 6-2. 1차 계획을 바꾸는 신규 사실 6가지
1. **다크 기본 확정 + 완전한 라이트 파스텔 테마 제공**: tokens.css가 `:root,[data-theme="dark"]`=다크 기본, `[data-theme="light"]`=파스텔 라이트(surface #F6F7FB·primary #7C98F2·on-surface #2A2E3B 등 전 토큰 쌍). 1차 계획의 "라이트는 보조 유지" → **라이트도 핸드오프 파스텔로 교체**가 정합(결정 §3-②).
2. **테마 스위칭 규약이 `data-theme` 속성**: 현행 `.dark` 클래스와 상이 — P2a-2 통일안 필요(겸용 variant 권고).
3. **종이 문서 뷰 토큰 신설**(--paper #F7F6F1 계열): 등기부등본·보고서 미리보기의 독립 서피스. ★이름 충돌: Part A 랜딩 --paper(#F4F4F2)와 동명 — Part A는 mkt-* 스코프라 충돌 자동 회피(계획 유지 근거 강화).
4. **PropAI Main = 사통팔땅 실카피 랜딩**: 1차 "아키퍼" 레퍼런스를 대체. P1 카피 결정 대부분 해소. 잔여=무근거 수치 3종(§3-④).
5. **레이아웃 계약 구체화**: 헤더 64px 고정·좌 dock 300~440px·우 패널 300~500px·중앙 지도/캔버스 하이브리드·글래스는 rgba(22,25,32,.85)+blur12+border-muted·팝오버는 **한 번에 하나**·radius 4/8/12/999.
6. **공공데이터 고지 계약**: 모든 데이터 뷰 하단 "출처·갱신·참고용" 명문화 — 기존 evidence 계약과 접점, 공용 컴포넌트로 승격(P2a-5).

### 6-3. 충돌·주의 3건
- **WBS 개수**: 핸드오프 Cost Estimation=공종 9종 vs 현행 적산 WB12 SSOT(PR#220) — **현행 12단계 유지**, 시각 패턴만 채택(좌 트리·인라인 편집·간접비 요약). 스펙의 간접비율(산재 4.9%·일반관리 5%·이윤 4.5%)은 데모값 — 실 요율 엔진 유지.
- **Dashboard 스테퍼 5단계** vs 현행 라이프사이클 10단계 — 표시 축약 매핑(사전검토/토지확보/설계/인허가/시공·준공) 또는 현행 유지 결정 필요(P2b에서).
- **데모 데이터 오염 경로**: 화면 전반의 "정자동 178-1"·수지/단가/등기 수치는 전부 예시 — 리스킨 시 실 데이터 배선 필수 + CI 데모수치 가드(§P2b).

### 6-4. 적용 순서(2차 README)와 본 계획의 정합
README 제안(①DESIGN.md 교체 ②tokens.css 전역+Tailwind var 매핑 ③폰트 로드 ④화면 단위 재구현 ⑤공통 셸) ⊂ 본 계획 P0(①③)+P2a(②)+P2b(④⑤)와 1:1 — 단 본 계획은 그 전에 **캐스케이드 역전 해소(P0-1)를 선행**시킨다(이것 없이는 ②가 무반응 — 실측 근거).
