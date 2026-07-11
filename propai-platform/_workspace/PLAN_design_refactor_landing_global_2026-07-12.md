# 랜딩페이지·전역 디자인 리팩토링 계획 — 통합 디자인시스템 v2.0 적용

작성: 2026-07-12 · 기준: origin/main 97334d45 · 입력: 디자인 핸드오프(DESIGN.md v2.0·Landing Page.dc.html·hero-skyline.js·download-assets.sh·README) + 현행 실측(전수 조사)
원칙: 기존 자산 재사용 · 무목업(데모 카피 이식 금지) · additive 우선 · --accent-strong 이름 불변 계약 존중

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
3. **★무목업 카피 치환(필수)**: 레퍼런스의 데모 콘텐츠는 이식 금지 — "아키퍼"→사통팔땅/PropAI 브랜드, **가짜 리뷰 18,921개·가상 파트너 로고 5종·가상 프로젝트 3종 제거**. 대체: 서비스 4행=실제 모듈군(부지분석·설계/BIM·적산/수지·분양/운영), Why 3이미지=핸드오프 이미지 유지(일러스트성 브랜드 자산으로 정당), 프로젝트 카드=실 분석 사례 스크린샷 또는 "데모 프로젝트" 명시 라벨, 수치는 검증 가능한 것만(무근거 수치 0).
4. **배선**: `/{locale}` 인증분기(§1 권고안), CTA→(auth)/login·register, 네비 활성상태, i18n(ko 우선·en/zh 키만 준비).
5. **품질**: SEO 메타+OG 이미지, 반응형(1200px 미만 단일 컬럼 스택 — min-width 강제 대신 우아한 축소), prefers-reduced-motion 시 비디오 정지+모션 제거, 대비 AA(특히 accent 텍스트 on 라이트 금지→accent-deep), LCP 예산(poster 우선 로드).
6. (선택) 로그인 화면 Part A 브릿지: cc-* 셸 유지하되 앰버 포인트 1개 도입 — 별도 결정.

### P2 — 전역(Part B) 정합 (2~3일)
1. tokens.css `.dark`를 v2.0 Part B로 보강: --secondary #4cd7f6·--tertiary #ffb95f·--ai-accent #a855f7·status 3종·글래스 blur 12px 정렬(현행 14/20px 충돌 해소)·surface 누락분. 라이트 테마는 보조로 유지(사통팔땅 라이트 자산 보존).
2. **--accent-strong 값 교체**(#3b82f6→#135bec 계열): 이름 불변·값만. 흰 텍스트 버튼 AA 재검증(#135bec on white=AA 통과 확인 필요) + 로고 그라디언트 육안 확인. 교체는 P0 SSOT 단일화 이후에만 유효.
3. **--ai-accent 사용 규칙 배선**: AI 산출물 표시 컴포넌트(VerificationBadge·ai_interpretation 카드·인터프리터 섹션·SeniorVerdictCard AI 서술부)에만 적용 — 일반 버튼/장식 금지(D장). 소비처 목록화 후 일괄.
4. 사이드바 440px는 **전역 강제하지 않음**(현행은 상단 네비 체계) — 지도 워크스페이스 좌측 컬럼(380px)의 440px 확대만 검토 항목으로.
5. `:where(.dark)` 가독성 패치(globals:1555-1579) 재검토·흡수.

### P3 — 정리 캠페인 (별도 PR 연작 · 기계적)
1. **이모지 618회/154파일 → Lucide 치환**(D장): 기존 feat/emoji-to-svg-icons 브랜치 이력 재활용 검토, 도메인별 배치 PR(의미 아이콘만·장식 삭제).
2. `<img>` 22회 → next/image(랜딩 제외 후순위).
3. **안티패턴 가드**: CI grep 게이트(이모지 신규 유입·Inter/Roboto 폰트 선언·filled 아이콘 import) + DESIGN.md D장 링크.

### P4 — 검증·배포 (1일)
- 시각 회귀: 주요 20화면 스크린샷 전후 대조(agent-browser), 다크/라이트 양 테마.
- Lighthouse(랜딩 LCP/CLS — 비디오 poster·폰트 swap), axe 대비 검사.
- tsc·eslint·vitest 전체 무회귀, sw bump, A1 재빌드+라이브검증(랜딩 렌더·인증분기·비디오 재생·폴백 캔버스·기존 워크스페이스 무회귀).

---

## 3. 사용자 결정 필요 (구현 착수 전)
1. **랜딩 진입 방식**: 권고=인증분기(URL 불변). 대안=별도 라우트.
2. **앱 기본 테마**: Part B는 다크 전제 — 권고=**앱 다크 기본**(라이트 옵션 유지). 현행은 항상 라이트 부팅이라 체감 변화 큼.
3. **--accent-strong 값 교체 시점**: P2 일괄(권고·SSOT 단일화 후 안전) vs 화면군 점진.
4. **랜딩 카피 확정**: 브랜드 표기(사통팔땅/PropAI 병기?)·서비스 4행 문안·프로젝트 카드 소재(실 사례 캡처 확보 가능 여부).

## 4. 규모·리스크 요약
- 총 6~8일(P0 1·P1 2~3·P2 2~3·P4 1·P3은 캠페인). P1과 P2는 P0 이후 병렬 가능(파일 소유 분리: marketing/* vs tokens/globals).
- 최대 리스크=P0 토큰 수렴(전 화면 영향) — computed-style diff+시각회귀로 게이트. 다음=accent-strong 값 교체(295파일 체감)·폰트 실로드 리플로우.
- 핸드오프 자산 CDN URL은 임시 — **P1 착수와 무관하게 자산 다운로드는 즉시 수행 권장**.

## 5. 산출물 목록(구현 시)
- 신규: components/marketing/ 7종·HeroSkylineCanvas·mkt 토큰 블록·@custom-variant dark·테마 부트스트랩 스크립트·next/font 셋업·public/landing 자산 7종·CI 안티패턴 게이트
- 수정: tokens.css(.dark 보강·정본화)·globals.css(:root 중복 제거)·app/[locale] 인증분기·DESIGN.md 교체·tailwind.config 삭제
- 문서: DESIGN.md v2.0(SSOT)·시각회귀 기준 스크린샷 세트
