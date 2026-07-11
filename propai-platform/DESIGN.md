# Design.md — PropAI 통합 디자인 시스템 (v2.0)

> 부동산개발 전주기 AI 자동화 플랫폼(PropAI·사통팔땅)의 단일 디자인 기준(source of truth).
> **두 컨텍스트**를 하나의 체계로 통합한다:
> - **Part A — 브랜드/랜딩** (Warm Amber): 마케팅 페이지, 소개, 영상자료.
> - **Part B — 앱 내부 "Nexus Geo-Intelligence"** (Deep Space Dark 기본 + 라이트 파스텔): 지도 워크스페이스, 수지분석, CAD/BIM 등 제품 UI.
>
> 판단 기준: **사용자가 로그인 전에 보는 화면 = Part A / 로그인 후 업무 화면 = Part B.**
> 구현 참조: 토큰 정본 `_workspace/design_handoff/tokens.v2.css` · 화면 스펙 = 핸드오프 screens/*.dc.html 21종.

---

# 0. 공통 파운데이션 (Shared Foundations)

## 0.1 디자인 원칙
1. **콘텐츠가 주인공** — 랜딩에선 건축 사진, 앱에선 지도·데이터. UI 크롬은 최소화.
2. **대담한 타이포, 절제된 색** — 위계는 타이포 스케일로. 색은 중성 베이스 + 컨텍스트별 액센트 1색.
3. **여백은 재료다** — 밀도보다 호흡. 정보를 채워 넣지 않는다.
4. **구조적 그리드** — 도면처럼 정렬·모듈·반복이 드러나야 한다.
5. **번호와 라벨** — 서비스·프로세스·단계는 `01/02/03` 넘버링과 라벨 pill로.
6. **뺄 수 없는 이유 검증** — "넣은 이유"가 아니라 "뺄 수 없는 이유"가 있어야 요소가 존재한다.

## 0.2 공통 타이포 전략
| 역할 | 폰트 | 비고 |
|---|---|---|
| 디스플레이/헤드라인(영문) | **Space Grotesk** | 기하학적·기술적 인상. 양쪽 컨텍스트 공통 |
| 본문/UI(한글 포함) | **Pretendard** | 한글 UI 기본. 본문은 Noto Sans 대신 Pretendard로 수렴 |
| 데이터/수치 | **JetBrains Mono** | 지번·좌표·면적·금액 등 숫자 정렬(Part B 중심) |

- 한글 헤드라인은 Space Grotesk가 커버하지 못하므로 **Pretendard 600**을 사용.
- Inter·Roboto·Arial·Fraunces 금지.

## 0.3 공통 규칙
- 간격은 4px 단위 스케일: `4 / 8 / 16 / 24 / 32 / 40 / 64 / 96 / 128`.
- 요소 배치는 항상 `flex`/`grid` + `gap`. 인라인 흐름 + margin 나열 금지.
- 본문 12px(인쇄 12pt) 미만 금지, 터치 타깃 44px 미만 금지.
- `text-wrap: pretty`. 디스플레이 텍스트 줄바꿈은 의도적으로.
- 이모지 금지. SVG로 그린 가짜 건축/지도 일러스트 금지 — 실사진·실데이터·플레이스홀더만.

## 0.4 공통 아이콘 지침
- **라인(outline) 아이콘만.** 스트로크 `1.5px`, 라운드 캡/조인, 24×24 그리드.
- 세트: **Lucide** 단일 세트(양쪽 컨텍스트 공통). 혼용 금지.
- 색: `currentColor` 상속 기본. 독립 색 지정은 `ink/graphite/accent`(A) 또는 `on-surface/outline/primary`(B)만.
- 크기: `16px`(인라인·라벨) / `20px`(버튼 내부) / `24px`(단독) / `40–48px`(원형 컨테이너).
- 허용 텍스트 글리프: `→ ↗ ← ✕ ✦ ● ◦` 7종. 그 외 특수문자 장식 금지.
- 금지: filled/duotone/3D/그라데이션 아이콘, 이모지 대용, 의미 없는 장식 아이콘.

---

# Part A — 브랜드/랜딩 (Warm Amber)

## A1. 색상

### 중성 팔레트
| 토큰 | HEX | 용도 |
|---|---|---|
| `--ink` | `#0E0E10` | 본문 텍스트, 다크 섹션 배경 |
| `--ink-soft` | `#2A2A2E` | 카드/다크 블록 배경 |
| `--graphite` | `#6B6B70` | 보조 텍스트, 캡션 |
| `--line` | `#E4E4E7` | 구분선, 보더 |
| `--paper` | `#F4F4F2` | 페이지 배경(따뜻한 오프화이트) |
| `--white` | `#FFFFFF` | 카드, 라이트 섹션 |

### 액센트 (황색: Warm Amber)
| 토큰 | HEX | 용도 |
|---|---|---|
| `--accent` | `#C8873F` | CTA hover, 넘버링, 라벨 글리프, 활성 상태 |
| `--accent-soft` | `#E8C79A` | 액센트 위 보조 톤, 골드 아워 하이라이트 |
| `--accent-deep` | `#9C6A2E` | 라이트 배경 위 액센트 텍스트(대비 확보) |

### 배색 규칙 (60/30/10)
- **60%** `--paper`/`--white`(밝힘) · **30%** `--ink`/`--ink-soft`(다크 섹션·텍스트) · **10% 이하** `--accent`.
- 허용 대비(WCAG AA): `ink on paper/white` · `white on ink` · `graphite on paper`(16px+) · `accent on ink` · `ink on accent`.
- 금지: `accent` 텍스트 on 라이트 배경(→ `accent-deep`) · `accent` 넓은 면 · `graphite on ink`(→ `rgba(255,255,255,.55)`) · 액센트 2색 병용 · 그라데이션 배경.
- 섹션 배경은 `paper`/`white`/`ink` 3종만. 라이트↔다크 교차로 챕터감, 다크는 1–2개 섹션.
- 사진 위 텍스트는 단방향 스크림(ink 계열 0.5 이하)으로 대비 확보. 스크림이 이미지 초점을 가리지 않게.

## A2. 타이포 스케일 (랜딩)
| 역할 | 크기 | 두께 | 자간 | 행간 |
|---|---|---|---|---|
| Display | 96–140px | 600 | -0.03em | 0.95 |
| H1 | 56–72px | 600 | -0.02em | 1.0 |
| H2 | 36–44px | 600 | -0.01em | 1.1 |
| H3 | 24–28px | 500 | 0 | 1.2 |
| Body L | 18–20px | 400 | 0 | 1.5 |
| Body | 16px | 400 | 0 | 1.6 |
| Caption | 13–14px | 500 | 0 | 1.4 |
| Label | 12–13px | 600 | 0.08em(영문 UPPERCASE) | 1.2 |

1920px 슬라이드/랜딩에서 24px 미만 본문 금지. 넘버링(`01`)은 `--graphite` 또는 `--accent`.

## A3. 레이아웃·섹션 패턴
- 12컬럼, gutter 24px, max-width 1440px, 좌우 여백 64–80px.
- 대표 섹션: ① Hero(이미지/영상 + 대형 헤드라인 + CTA pill) ② Services(다크 + 넘버링 리스트) ③ Why(2컬럼 + 스탯/이미지 그리드) ④ Projects(카드 갤러리 + `1/N` 인디케이터) ⑤ CTA/푸터(다크).

## A4. 컴포넌트 (랜딩)
- **Primary 버튼(pill)**: `--ink` 배경/`--white` 텍스트, radius 999px, padding 14–20px/24–36px, 우측 `→`. hover: `--accent` 배경/`--ink` 텍스트.
- **Secondary**: transparent + `1px --line` 보더.
- **라벨 pill**: `1px --line` 보더 + radius 999px + `✦`(accent) 글리프 1개. 예: `✦ 서비스`.
- **카드**: radius 16–20px, `1px --line` 보더 우선(그림자는 hover/모달 상태 표현에만), 이미지 상단 + 정보 하단, 우상단 상태 `↗`.
- **이미지**: radius 16–24px, 실제 건축 사진(히어로 16:9~21:9, 카드 4:5·3:2).
- **넘버링 리스트**: `01`(accent) + 대형 항목명 + `1px --line` 구분선.

## A5. 모션 (랜딩)
- 진입: fade + `translateY(16px)`, 600ms, `cubic-bezier(.2,.8,.2,1)`. 진입 1회 + hover만; 무한 반복 모션은 히어로 1곳 제한.
- 이미지 hover `scale(1.03)` 700ms, 컨테이너 `overflow:hidden`. 스크롤재킹 금지.

---

# Part B — 앱 내부 "Nexus Geo-Intelligence"

제품 UI(지도 워크스페이스·수지분석·CAD/BIM·대시보드) 전용. 성격: 기술적·권위적·HUD.
스타일: **글래스모피즘 + 코퍼레이트 모던** — 고투명 패널 + 백드롭 블러로 지도 위 고밀도 정보를 오버레이.
**다크가 기본 테마**, `[data-theme="light"]`로 라이트 파스텔 전환(전 화면 다크/라이트 쌍 스펙 존재).

## B1. 색상 토큰 (다크 기본 — 라이트 파스텔 쌍은 tokens.v2.css 참조)

### 서피스 (정보 밀도 위계)
| 토큰 | HEX(다크) | 용도 |
|---|---|---|
| `--background-deep` | `#0a0c10` | 지도/캔버스 보이드(최하층) |
| `--surface` | `#11131b` | 기본 배경 |
| `--surface-panel` | `#111318` | 사이드 패널·헤더 |
| `--surface-container-low` | `#191b24` | 낮은 컨테이너 |
| `--surface-container` | `#1c1f27` | 카드·인풋 |
| `--surface-container-high` | `#282a32` | 상위 컨테이너 |
| `--surface-elevated` | `#282e39` | 최상위 패널 · `--border-muted` 겸용 |
| `--on-surface` | `#e1e1ee` | 기본 텍스트 |
| `--on-surface-variant` | `#c3c5d8` | 보조 텍스트 |
| `--outline` | `#8d90a1` | 강한 보더 |
| `--outline-variant` | `#434655` | 약한 보더 |

### 액센트·기능색
| 토큰 | HEX(다크) | 용도 |
|---|---|---|
| `--primary` | `#135bec` | 핵심 액션, 브랜딩, 활성/선택 상태 |
| `--primary-dim` | `#b4c5ff` | 다크 위 프라이머리 텍스트/힌트 |
| `--secondary` | `#4cd7f6` (Cyan) | 인프라 오버레이(관로 등) |
| `--tertiary` | `#ffb95f` (Amber) | 고압가스 등 위험 인프라 · **Part A 액센트와의 브릿지 키** |
| `--ai-accent` | `#a855f7` | AI 생성·추론 표시 전용 |
| `--status-success` | `#22c55e` | 성공 |
| `--status-warning` | `#f59e0b` | 경고 |
| `--status-error` | `#ef4444` | 오류 |

### 종이 문서 뷰 (등기부등본·보고서 미리보기 — 테마 불변)
`--paper #F7F6F1` · `--paper-ink #1E1E22` · `--paper-line #D5D2C6` · `--paper-section #E9E7DE`

### 배색 규칙 (앱)
- 데이터 시각화 외 채도는 동시 사용 3종 이하. `--ai-accent`는 AI 산출물 표시에만 — 일반 버튼·장식 금지.
- 상태색은 의미 고정(성공/경고/오류). 장식 목적 사용 금지.
- 글래스 패널: `rgba(22,25,32,.85)` + `backdrop-filter: blur(12px)` + `1px var(--border-muted)` 보더. 팝오버는 **한 번에 하나만**.
- 텍스트 대비: `on-surface on surface` 계열만. 채도색 위 텍스트는 각 `on-*` 페어 사용.
- **공공데이터 고지**: 모든 데이터 뷰 하단에 출처·갱신일·참고용 문구 표시(공용 컴포넌트).

## B2. 타이포 (앱)
| 역할 | 폰트 | 크기/두께 | 비고 |
|---|---|---|---|
| display-lg | Space Grotesk | 24–30px / 700 / -0.02em | 메트릭 대형 수치 |
| headline-md | Space Grotesk | 14–18px / 600 | 패널 제목 |
| body-md | Pretendard | 13–14px / 400 / 150% | 본문 |
| body-sm | Pretendard | 12px / 400 / 140% | 보조 |
| label-caps | Space Grotesk | 10px / 700 / 0.1em UPPERCASE | 섹션 라벨 |
| data-mono | JetBrains Mono | 11–13px / 500 | 지번·좌표·면적·금액 |

## B3. 레이아웃 (앱)
- **헤더 64px 고정**(브랜드 + 프로젝트 선택 필 + 글로벌 내비) + **좌측 dock 300–440px** + **우측 패널 300–500px** + 중앙 지도/캔버스 하이브리드.
- 지도 위 플로팅 컨트롤: 글래스 패널, 화면 가장자리 16–24px 이격. 40px 정방 그리드 오버레이(정렬 가이드).
- 사이드바: 섹션 간 24px, 카드 내부 패딩 16px의 엄격한 수직 리듬.

## B4. 깊이·라운드
- 깊이는 투명도 + 글로우로: L0 지도 → L1 글래스 패널(blur 12px) → L2 활성 글로우(`shadow-primary/20`) → L3 팝오버(90% 불투명 + blur 24px).
- 라운드: 인풋 `--r-input 4px` · 카드 `--r-card 8px` · 패널 `--r-panel 12px` · pill `--r-pill 999px`.

## B5. 컴포넌트 (앱)
- **버튼**: Primary는 `--primary` + hover 시 미세 상승. Glass 버튼은 `bg-white/10` hover.
- **인풋**: `--surface-container` 배경, focus 시 primary 보더.
- **상태 칩**: 상태색 10% 배경 + 1px 상태색 보더 + 11px/600 텍스트.
- **지도 오버레이**: 필지 경계는 점선, 선택 필지는 primary 채움+글로우, POI는 글로우 점.
- **메트릭 카드**: Space Grotesk 대형 수치 + Pretendard 라벨.
- **표 편집**(수지분석표·내역서): 투명 보더 인라인 인풋 → focus 시 보더+배경, 행 hover 하이라이트, 합계 행 자동 재계산.

---

# C. 컨텍스트 브릿지 (A ↔ B)
1. **전환점**: 랜딩 CTA → 로그인/온보딩까지 Part A. 워크스페이스 진입부터 Part B.
2. **공유 자산**: Space Grotesk 헤드라인, Pretendard 본문, Lucide 아이콘, 4px 간격 체계, 라벨 pill 패턴.
3. **색 브릿지**: Part B의 `--tertiary(#ffb95f)`가 Part A Warm Amber 계열의 앱 내 대응 키 → 브랜드 연속성이 필요한 지점(온보딩, 요금제, 마케팅 모달)에 사용.
4. **금지**: 랜딩에 Nexus 블루/글래스 패널 반입 금지, 앱 크롬에 Warm Amber 장식 반입 금지(브릿지 지점 예외).

---

# D. 하지 말 것 (통합 안티패턴)
- ❌ 그라데이션 배경 남발, 네온 강조, 무지개색
- ❌ 둥근 모서리 + 좌측 컬러 보더 카드 클리셰
- ❌ 이모지, filled/duotone/혼용 아이콘, 장식용 아이콘
- ❌ Inter/Roboto/Arial/Fraunces
- ❌ SVG로 그린 가짜 건축·지도 일러스트
- ❌ 자리 채움용 통계·배지·구분선·무한 모션 (data slop)
- ❌ 12px 미만 본문, 44px 미만 터치 타깃
- ❌ 정의되지 않은 섹션 배경색, 라이트 배경 위 `--accent` 원색 텍스트
- ❌ `--ai-accent`의 비-AI 용도 사용, 상태색의 장식적 사용
- ❌ 데모/가상 수치의 실화면 이식(무목업 — 실데이터 배선 또는 정직한 부재 표기)

---

# E. 토큰 요약 (Copy-paste)

```css
:root {
  /* ── Part A: 랜딩(마케팅 스코프 mkt-* 반입 권장) ── */
  --ink:#0E0E10; --ink-soft:#2A2A2E; --graphite:#6B6B70;
  --line:#E4E4E7; --paper:#F4F4F2; --white:#FFFFFF;
  --accent:#C8873F; --accent-soft:#E8C79A; --accent-deep:#9C6A2E;
  --r-card:18px; --r-pill:999px; --r-img:20px;
  --pad-x:72px; --maxw:1440px;
  /* ── 공통 ── */
  --gap:24px; --ease:cubic-bezier(.2,.8,.2,1);
}
/* Part B(앱) 전체 토큰(다크 기본 + [data-theme="light"] 파스텔)은
   _workspace/design_handoff/tokens.v2.css 를 정본으로 참조. */
```

---

*v2.0 — 랜딩(Warm Amber) + 앱(Nexus Geo-Intelligence 다크 기본/라이트 파스텔) 통합본. 원본: 디자인 핸드오프 1·2차 + 기존 propai-platform/DESIGN.md(Part B로 흡수).*
