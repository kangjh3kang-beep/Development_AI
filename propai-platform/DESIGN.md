# Design.md — 사통팔땅 (PropAI) 통합 디자인 시스템 v3.0

> 부동산개발 전주기 AI 자동화 플랫폼 **사통팔땅(PropAI)**의 단일 디자인 기준(source of truth).
> v3.0은 실제 제작된 화면 12종(랜딩·메인·관제 홈·지도·CAD·BIM·CAD/BIM 엔진·수지분석·적산·토지조서·법규·보고서)에서 검증된 패턴을 지침으로 역반영한 판이다.
>
> **두 컨텍스트**를 하나의 체계로 통합한다:
> - **Part A — 브랜드/랜딩** (Warm Amber): 마케팅 페이지, 소개, 영업자료. 레퍼런스: Hiteect·Arcbuild·ARC.
> - **Part B — 앱 내부 "Nexus Geo-Intelligence"** (다크 기본 + 화이트 파스텔 라이트): 지도 워크스페이스, 수지분석, CAD/BIM 등 제품 UI.
>
> 판단 기준: **로그인 전 화면 = Part A / 로그인 후 작업 화면 = Part B.**

---

# 0. 공통 파운데이션 (Shared Foundations)

## 0.1 디자인 원칙

1. **콘텐츠가 주인공** — 랜딩에선 건축 사진, 앱에선 지도·데이터. UI 크롬은 최소화.
2. **대담한 타이포, 절제된 색** — 위계는 타이포 스케일로. 색은 중성 베이스 + 컨텍스트별 액센트 1색.
3. **여백은 재료다** — 밀도보다 호흡. 정보를 채워 넣지 않는다.
4. **구조적 그리드** — 도면처럼 정렬·모듈·반복이 드러나야 한다.
5. **번호와 라벨** — 서비스·프로세스·단계는 `01/02/03` 넘버링과 라벨 pill로.
6. **뺄 수 없는 이유 검증** — "넣을 이유"가 아니라 "뺄 수 없는 이유"가 있어야 요소가 존재한다.
7. **산출물 중심 동선** — 기능 나열이 아니라 "무엇을 만들까요?"로 시작한다. 모든 화면은 입력→분석→산출물 흐름 위에 놓인다.
8. **수치는 근거와 함께** — 모든 데이터 뷰에 출처·갱신일·참고용 고지를 붙인다. AI 산출물은 반드시 표시한다.

## 0.2 공통 타이포 전략

| 역할 | 폰트 | 비고 |
|---|---|---|
| 디스플레이/헤드라인 (영문) | **Space Grotesk** | 기하학적·기술적 인상. 양쪽 컨텍스트 공통 |
| 본문/UI (한글 포함) | **Pretendard** | 한글 UI 기본. Noto Sans는 Pretendard로 수렴 |
| 데이터/수치 | **JetBrains Mono** | 지번·PNU·좌표·면적·금액·시각 등 숫자 정렬 |

- 한글 헤드라인은 Space Grotesk가 커버하지 못하므로 **Pretendard 600–700**을 사용.
- Inter·Roboto·Arial·Fraunces 금지.

## 0.3 공통 규칙

- 간격은 4px 단위 스케일: `4 / 8 / 16 / 24 / 32 / 40 / 64 / 96 / 128`.
- 요소 배치는 항상 `flex`/`grid` + `gap`. 인라인 흐름 + margin 나열 금지.
- 본문 12px(인쇄 12pt) 미만 금지, 터치 타깃 44px 미만 금지 (단, 밀도 높은 데이터 테이블 내 보조 버튼은 24px까지 허용).
- `text-wrap: pretty`. 디스플레이 텍스트 줄바꿈은 의도적으로.
- 이모지 금지. SVG로 그린 가짜 건축·지도 일러스트 금지 — 실사진·실데이터·플레이스홀더만. (단, **데이터 시각화**로서의 SVG — 지적 폴리곤, 평면도, 아이소메트릭 매스, 차트, 단면 다이어그램 — 는 허용이자 권장.)

## 0.4 공통 아이콘 지침

- **라인(outline) 아이콘만.** 스트로크 `1.5px`, 라운드 캡/조인, 24×24 그리드.
- 세트: **Lucide** 단일 세트. 혼용 금지.
- 색: `currentColor` 상속 기본.
- 크기: `13–15px`(버튼 내 인라인) / `16–18px`(단독·카드) / `20px`(레일 버튼 내부) / `36–48px`(원형·사각 컨테이너).
- 허용 텍스트 글리프: `↗ → ← ↑ ↓ ▾ ▲ ▼ ✓ ✕ ▦ ◆ ★ + −` — 방향·확정·삭제·증감 의미로만.
- **의미 규칙**: 업로드는 화살표 위(↑), 다운로드는 화살표 아래(↓). 혼동 금지.
- 금지: filled/duotone/3D/그라디언트 아이콘, 이모지 대용, 장식용 아이콘.

## 0.5 단위·수치 표기 (검증된 규칙)

- **면적은 ㎡/평 병행 표기**: `8,019㎡ (2,425.7평)` — 평 = ㎡ × 0.3025, 소수 1자리.
- 금액 단위는 문맥 고정: 총괄 = 억 (소수 1자리) · 내역/표 = 만원 또는 원 (천 단위 콤마).
- 수치는 항상 JetBrains Mono + 단위는 작게(Pretendard, 뮤트 컬러) 분리.
- 비율은 소수 1자리(`78.4%`), 법규 한도는 `현재값 / 한도` 병기 (`248.0% / 250%`).
- PNU·문서고유번호·좌표·시각(HH:MM:SS)은 mono 고정.

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
| `--paper` | `#F4F4F2` | 페이지 배경 (따뜻한 오프화이트) |
| `--white` | `#FFFFFF` | 카드, 라이트 섹션 |

### 액센트 (확정: Warm Amber)

| 토큰 | HEX | 용도 |
|---|---|---|
| `--accent` | `#C8873F` | CTA hover, 넘버링, 라벨 글리프, 활성 상태 |
| `--accent-soft` | `#E8C79A` | 액센트 위 보조 톤, 골든아워 하이라이트 |
| `--accent-deep` | `#9C6A2E` | 라이트 배경 위 액센트 텍스트 (대비 확보) |

### 배색 규칙 (60/30/10)

- **60%** `--paper`/`--white` · **30%** `--ink`/`--ink-soft` · **10% 이하** `--accent`.
- 허용 대비(WCAG AA): `ink on paper/white` · `white on ink` · `graphite on paper`(16px+) · `accent on ink` · `ink on accent`.
- 금지: `accent` 텍스트 on 라이트 배경(→ `accent-deep`) · `accent` 넓은 면 · `graphite on ink`(→ `rgba(255,255,255,.55)`) · 액센트 2색 병용 · 그라디언트 배경.
- 섹션 배경은 `paper`/`white`/`ink` 3종만. 라이트↔다크 교차로 챕터감, 다크는 1–2개 섹션.
- 사진/영상 위 텍스트는 단방향 스크림(ink 계열 0.6 이하)으로 대비 확보.

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
| Label | 12–13px | 600 | 0.08em (영문 UPPERCASE) | 1.2 |

## A3. 레이아웃·섹션 패턴

- 12컬럼, gutter 24px, max-width 1440px, 좌우 여백 64–80px.
- 대표 섹션: ① Hero ② Services/모듈(다크 + 넘버링 초대형 리스트) ③ Why(2컬럼 + 지표 카드) ④ 인터랙티브 패널(보고서 생성 등) ⑤ CTA/푸터(다크).

### A3.1 히어로 영상 패턴 (검증)
- 풀블리드 배경 영상: 건축·도시 형성 타임랩스 (`autoplay` `muted` `loop` `playsinline`).
- **JS 재생 킥 필수**: 로드 후 `video.play().catch(()=>{})`를 0/500/1500ms에 재시도 (autoplay 속성만으론 미재생 사례 대응).
- 스크림: `linear-gradient(to top, rgba(14,14,16,.55~.6), rgba(14,14,16,.05~.08) 45~50%)`.
- 영상 위 요소: 좌상 라벨 pill + 초대형 헤드라인 / 좌하 CTA + 보조 카피 / 우하 지표 카운터.
- CDN 임시 URL은 배포 전 반드시 로컬 에셋(`public/`)로 교체 + poster 지정.

## A4. 컴포넌트 (랜딩)

- **Primary 버튼(pill)**: `--ink` 배경/`--white` 텍스트, radius 999px, 우측 `↗`. hover: `--accent` 배경/`--ink` 텍스트.
- **Secondary**: transparent + `1px --line` 보더.
- **라벨 pill**: `1px --line` 보더 + radius 999px + `▦`(accent) 글리프 1개.
- **카드**: radius 16–20px, `1px --line` 보더 우선, 이미지 상단 + 정보 하단, 우상단 원형 `↗`.
- **지표 카드**: Space Grotesk 44px 수치 + 단위 소형 + 설명 1문장 (Why 섹션 3열).
- **인터랙티브 선택 카드**: 선택 시 `--white` 배경 + `--accent` 보더 + `--accent-deep` 넘버 (보고서 생성 패널 검증).
- **넘버링 리스트**: `01`(accent) + 초대형 항목명 + `1px --line` 구분선.

## A5. 모션 (랜딩)

- 진입: fade + `translateY(16px)`, 600ms, `cubic-bezier(.2,.8,.2,1)`. 진입 1회 + hover만; 무한 반복 모션은 히어로 영상 1곳 제한.
- 이미지 hover `scale(1.03)` 700ms, 컨테이너 `overflow:hidden`. 스크롤재킹 금지.

---

# Part B — 앱 내부 "Nexus Geo-Intelligence"

제품 UI 전용. 성격: 기술적·권위적·HUD. **다크가 기본**, 화이트 파스텔 라이트 테마와 1:1 토큰 대응.
스타일: 글래스모피즘 + 코퍼레이트 모던 — 고투명 패널 + 백드롭 블러로 지도·캔버스 위 고밀도 정보를 오버레이.

## B1. 색상 토큰 (다크 ↔ 라이트 1:1)

### 서피스

| 토큰 | 다크 | 라이트 (파스텔) | 용도 |
|---|---|---|---|
| `--background-deep` | `#0a0c10` | `#ECF0F6` | 지도/캔버스 보이드 |
| `--surface` | `#11131b` | `#F6F7FB` | 기본 배경 |
| `--surface-panel` | `#111318` | `#FFFFFF` | 사이드 패널·헤더 |
| `--surface-container` | `#1c1f27` | `#F0F2F8` | 카드·인풋 |
| `--surface-container-high` | `#282a32` | `#E7EAF2` | 상승 컨테이너·프로그레스 트랙 |
| `--surface-elevated` / `--border-muted` | `#282e39` | `#E2E5EE` | 보더 기본 |
| `--outline-variant` | `#434655` | `#D2D7E4` | 인풋·버튼 보더 |
| `--on-surface` | `#e1e1ee` | `#2A2E3B` | 기본 텍스트 |
| `--on-surface-variant` | `#c3c5d8` | `#555B6E` | 보조 텍스트 |
| `--outline` (뮤트 텍스트) | `#8d90a1` | `#8A90A4` | 라벨·캡션 |

### 액센트·기능색

| 토큰 | 다크 | 라이트 | 용도 |
|---|---|---|---|
| `--primary` | `#135bec` | `#7C98F2` | 핵심 액션, 활성, 선택 하이라이트 |
| `--on-primary` | `#e2e6ff` | `#FFFFFF` | 프라이머리 위 텍스트 |
| `--primary-dim` | `#b4c5ff` | `#5570DE` | 서피스 위 프라이머리 텍스트 |
| `--secondary` | `#4cd7f6` | `#3BA8C4` | 누적선·창호 등 보조 시각화 |
| `--tertiary` | `#ffb95f` | `#C88A3C` | Part A 브릿지 톤 · 위험 인프라 |
| `--ai-accent` | `#a855f7` | `#9356DC` | **AI 생성·추론 전용** |
| `--status-success` | `#22c55e` | `#3A9668` | 적합·완료·기지급 |
| `--status-warning` | `#f59e0b` | `#E9A436` | 조건부·협의중·미지급·변동감지 |
| `--status-error` | `#ef4444` | `#D05050` | 부적합·가압류·삭제 hover |

### 문서(종이) 팔레트 — 테마 불변

| 토큰 | HEX | 용도 |
|---|---|---|
| `--paper` | `#F7F6F1` | 등기부·보고서 문서 뷰 배경 |
| `--paper-ink` | `#1E1E22` | 문서 텍스트 |
| `--paper-line` | `#D5D2C6` | 문서 구분선(점선) |
| `--paper-section` | `#E9E7DE` | 【표제부】【갑구】 등 섹션 헤더 배지 |

### 배색 규칙

- 채도색 동시 사용 3종 이하 (데이터 시각화 제외). `--ai-accent`는 AI 산출물 표시·버튼에만.
- 상태색 의미 고정. 장식 사용 금지. **라이트 테마에서는 파스텔로 톤다운하되 의미 유지.**
- 글래스 패널: 다크 `rgba(22,25,32,.85)` / 라이트 `rgba(255,255,255,.88)` + `blur(12px)` + 1px `--border-muted`. 팝오버는 `.9`/`.94` + blur 24px.
- 알파 컬러도 테마별 쌍으로 관리 (예: 선택 행 다크 `rgba(19,91,236,.10)` ↔ 라이트 `rgba(124,152,242,.14)`).

## B2. 타이포 (앱)

| 역할 | 폰트 | 크기/두께 | 용도 |
|---|---|---|---|
| display-lg | Space Grotesk | 24–30px / 700 / -0.02em | KPI·메트릭 대형 수치 |
| headline-md | Space Grotesk | 14–18px / 600 | 패널·카드 제목 |
| **label-caps** | Space Grotesk | **10–11px / 700 / 0.1–0.14em UPPERCASE** | 섹션 라벨 — 모든 패널 최상단에 사용 (검증된 시그니처) |
| body-md | Pretendard | 13–14px / 400–500 / 150% | 본문 |
| body-sm | Pretendard | 11–12px / 400 / 140% | 보조·고지 |
| data-mono | JetBrains Mono | 11–13px / 400–500 | 수치 전반 |

## B3. 레이아웃 (앱 셸)

### B3.1 공통 셸 (전 화면 검증)
- **헤더 64px 고정**: 좌측 = 브랜드 블록(32px 사각 로고 `四` + "사통팔땅" + 모듈명 label-caps) + 세로 구분선 + **프로젝트 선택 필드**(폴더 아이콘 + PROJECT 라벨 + 프로젝트명 + ▾) / 우측 = 글로벌 네비(활성 = on-surface 600, 비활성 = 뮤트) + 상태 인디케이터 + 주 액션 버튼.
- **3열 워크스페이스**: 좌 패널 300–440px + 중앙 유동(지도/캔버스/대시보드) + 우 패널 360–500px. 각 패널 `overflow-y: auto`, 섹션 패딩 16px, 섹션 간 1px 보더 구분.
- 지도/캔버스 위 플로팅 컨트롤: 글래스, 가장자리 16–24px 이격.
- 40px 정방 그리드 오버레이: `linear-gradient` 2방향, 다크 `rgba(67,70,85,.14~.18)` / 라이트 `rgba(130,142,170,.16)`.
- 하단 상태바(엔진·문서 화면): mono 11px, 좌 = 버전·개체수, 우 = 예외(warning)·동기화 상태(success).

### B3.2 대시보드/홈 레이아웃
- max-width 1560–1600px 중앙 정렬, 패딩 24–32px, 섹션 간 40px.
- 히어로(관제): 좌 영상/이미지 카드(min 480px, 스크림 좌→우) + 우 380px 사이드 카드.
- 카드 그리드: KPI 4열 · 모듈 카드 2–3열 · 프로젝트 카드 2열.

## B4. 깊이·형태

- 깊이는 투명도 + 글로우: L0 캔버스 → L1 글래스(blur 12) → L2 활성 글로우(`0 0 16~24px primary/20~35%`) → L3 팝오버(blur 24).
- 라운드: 버튼/인풋/칩 4px · 카드 8–12px · 대형 카드/히어로 14–16px · pill(뱃지·GNB 탭) 999px.
- 그림자 금지 — 보더와 배경 대비로 위계 표현. 예외: 종이 문서 뷰(`0 8px 24px rgba(0,0,0,.4)` 다크 / `rgba(42,46,59,.15)` 라이트)와 활성 글로우.

## B5. 컴포넌트 패턴 라이브러리 (화면 검증 완료)

### B5.1 기본
- **버튼**: Primary = `--primary` 채움 + hover `translateY(-1px)` · Secondary = `--surface-container` + 1px `--outline-variant` · Ghost = transparent + hover 컨테이너 톤. AI 액션은 `--ai-accent` 채움.
- **인풋**: `--surface-container` 배경 + 1px `--outline-variant`, focus 시 primary 보더.
- **상태 칩**: 상태색 10–14% 배경 + 1px 상태색 보더 + 11px/600 텍스트. 의미: 적합/완료/기지급(success) · 조건부/협의중/변동감지(warning) · 부적합(error) · 미열람/미접촉(뮤트).
- **탭 전환(세그먼트)**: 컨테이너 배경 + 4px 패딩 pill 그룹, 활성 = primary 채움. `white-space: nowrap` 필수.

### B5.2 데이터 테이블 (편집형 — 수지분석표·적산 내역서 검증)
- 헤더 행: `--surface-panel` 배경 + label-caps 컬럼명. 수치 컬럼은 우측 정렬.
- 셀 편집: 투명 인풋 + focus 시 primary 보더 + 패널 배경. 수치 셀은 mono 우측 정렬.
- **행 조작 컬럼(우측 고정)**: `▲▼`(재배치) + `✕`(삭제, hover 시 error 15% 배경). 24px 소형 버튼 허용.
- **행 추가**: 소계 행 좌측에 `+ 항목 추가` (1px dashed `--outline-variant`, hover 시 primary).
- **자동 재계산**: 셀 수정 → 파생값(합계·소계·구성비·이익률) 즉시 갱신. 파생 셀은 편집 불가 표시(인풋 아님).
- 파생 관계 표기: 미지급 = 총금액 − 기지급 (기지급 success / 미지급 warning 컬러).
- 내보내기: CSV는 한글 BOM(`\uFEFF`) + CRLF. 파일명에 프로젝트·시나리오 포함.
- 열 폭: `grid-template-columns` 고정 px + `minmax(…,fr)` 혼합, 지번 등 식별자는 `white-space: nowrap`.

### B5.3 지도·캔버스
- 지적 폴리곤: 주변 필지 = 뮤트 채움 + 1px 보더 / 선택 필지 = primary 25–30% 채움 + 2.5px primary 보더 + 글로우 윤곽 / 후보 = 점선 보더.
- 용도지역 색면: success 7–12% + 점선 보더. 공시지가 패치: tertiary 10–16%.
- 데이터 배지(실거래·공매): 글래스 + 상태 도트 + mono 수치 + 뮤트 시점.
- **레이어 레일**(우측): 글래스 컨테이너 + 44px 아이콘 버튼 세로 스택. 활성 = primary 18–22% 배경, 팝오버 열림 = primary 채움 + 글로우. **팝오버는 한 번에 하나만.**
- 줌 컨트롤(+/−) 좌하단, 축척 표기 mono.
- 필지 팝업: 글래스 12px 라운드 + 핵심 속성 3–4행 + 출처 고지 푸터.

### B5.4 CAD/BIM
- 편집 툴바: 글래스 + 36px 아이콘 버튼(선택/벽체/문/창호/치수/단면), 활성 = primary 채움.
- 뷰 전환: `2D / 2D⇄3D / 3D` 세그먼트 — 실제 팬 표시 전환과 연동.
- **2D↔3D 정합**: 동일 SSOT 좌표계 — 선택 요소는 양쪽 동시 하이라이트(primary), 3D 상면에 2D 벽선 투영. 도면 라벨·치수는 SVG 좌표계 내부에 배치(절대배치 div 금지 — 리사이즈 시 어긋남).
- 실시간 법규 KPI 스트립: `현재값 / 한도` + 여유도별 보더(success/warning/error).
- 자연어·음성 명령 바(하단): 마이크 버튼 + 인풋 + `검증 후 적용`(ai-accent) + "LLM은 수치를 직접 생성하지 않습니다" 고지.
- 버전 컨트롤: `design_versions vNN` + 되돌리기/다시 실행.

### B5.5 문서·보고서
- **종이 문서 뷰**: `--paper` 배경 + 26–28px 패딩 + 문서 그림자. 등기부는 실제 서식 구조(표제부/갑구/을구, `【 】` 섹션 배지, 점선 행 구분). 권리 리스크(근저당·가압류)는 문서 밖 요약 카드로 별도 표시.
- 법조항 표기는 통용 표기(예: 건축법 제61조).
- 생성 이력·활동 로그: mono 시각 + 1문장, 상태 도트.

### B5.6 홈·대시보드
- **진행 스테퍼**: 완료 = success 채움 ✓ / 진행 = primary 20% + primary 보더 / 예정 = 뮤트 보더. 단계 사이 2px 연결바(완료 구간만 success).
- **KPI 카드**: label-caps 라벨 + display-lg 수치 + 단위 소형 + 보조 1줄. 주의 지표는 상태색 보더.
- **모듈/생성 허브 카드**: 아이콘 컨테이너 + 제목 + 설명 + `입력/결과` 2행 스펙 + 소요시간(mono) + hover 시 primary 보더 + `translateY(-2px)`.
- **Output Dock**: 대표 산출물 1개 = primary 채움 카드, 나머지 = 화이트/컨테이너 카드.
- 리스크 알림: 상태색 8–10% 배경 + 35–45% 보더 + 도트 + 발생시각·출처.

## B6. 데이터 무결성·고지 (필수)

- 모든 데이터 화면 하단: `출처 · 갱신일 · 참고용(법적 효력 없음)` 고지.
- 공공데이터 출처 표기: VWorld·국토교통부·공공데이터포털·인터넷등기소 등 구체 명시.
- 입력값 출처 태그: `실거래 연동`(success) / `표준품셈 기반`(success) / `주변 시세 −N%`(secondary) / `수동 입력`(뮤트).
- AI 산출물: `--ai-accent` 라벨/보더 + "AI" 뱃지. 면책 푸터: 경고 아이콘 + 1문장.

---

# C. 컨텍스트 브릿지 (A ↔ B)

1. **전환점**: 랜딩 CTA → 로그인/온보딩까지 Part A. 워크스페이스 진입부터 Part B.
2. **공유 자산**: Space Grotesk 라벨, Pretendard 본문, JetBrains Mono 수치, Lucide 아이콘, 4px 간격, 라벨 pill, 히어로 영상 패턴(A3.1 — 관제 홈 히어로에도 동일 적용).
3. **색 브릿지**: `--tertiary`가 Warm Amber의 앱 내 대응 톤 — 온보딩·요금제·마케팅 모달에 사용.
4. **금지**: 랜딩에 Nexus 블루/글래스 반입 금지, 앱 크롬에 Warm Amber 장식 반입 금지 (브릿지 지점 예외).

---

# D. 하지 말 것 (통합 안티패턴)

- ❌ 그라디언트 배경 남발, 다색 강조, 무지개색
- ❌ 드롭섀도 카드 (보더로 대체 — B4 예외 2종만)
- ❌ 둥근 모서리 + 좌측 컬러 보더 카드 클리셰
- ❌ 이모지, filled/duotone/혼용 아이콘, 장식용 아이콘, 스파클 FAB
- ❌ Inter/Roboto/Arial/Fraunces
- ❌ SVG로 그린 가짜 건축 일러스트 (데이터 시각화 SVG는 예외 — 0.3)
- ❌ 자리 채움용 통계·배지·구분선·무한 모션 (data slop)
- ❌ 12px 미만 본문 · 44px 미만 터치 타깃 (테이블 행 조작 버튼 예외 24px)
- ❌ `--ai-accent`의 비-AI 용도, 상태색의 장식적 사용
- ❌ 출처·참고용 고지 없는 데이터 화면
- ❌ 도면 위 라벨의 절대배치 div (SVG 좌표계 내부에)
- ❌ 배경·텍스트 동색 조합 (테마 변환 시 활성 pill 등 재검증 필수)
- ❌ 면적 단독 표기 (㎡/평 병행 — 0.5)

---

# E. 토큰 요약 (Copy-paste)

```css
:root, [data-theme="dark"] {
  /* ── Part B: 앱 (다크 기본) ── */
  --background-deep:#0a0c10; --surface:#11131b; --surface-panel:#111318;
  --surface-container:#1c1f27; --surface-container-high:#282a32;
  --surface-elevated:#282e39; --border-muted:#282e39;
  --outline:#8d90a1; --outline-variant:#434655;
  --on-surface:#e1e1ee; --on-surface-variant:#c3c5d8;
  --primary:#135bec; --on-primary:#e2e6ff; --primary-dim:#b4c5ff;
  --secondary:#4cd7f6; --tertiary:#ffb95f; --ai-accent:#a855f7;
  --status-success:#22c55e; --status-warning:#f59e0b; --status-error:#ef4444;
  --glass-bg:rgba(22,25,32,.85); --glass-bg-strong:rgba(22,25,32,.9);
}
[data-theme="light"] {
  --background-deep:#ECF0F6; --surface:#F6F7FB; --surface-panel:#FFFFFF;
  --surface-container:#F0F2F8; --surface-container-high:#E7EAF2;
  --surface-elevated:#E2E5EE; --border-muted:#E2E5EE;
  --outline:#8A90A4; --outline-variant:#D2D7E4;
  --on-surface:#2A2E3B; --on-surface-variant:#555B6E;
  --primary:#7C98F2; --on-primary:#FFFFFF; --primary-dim:#5570DE;
  --secondary:#3BA8C4; --tertiary:#C88A3C; --ai-accent:#9356DC;
  --status-success:#3A9668; --status-warning:#E9A436; --status-error:#D05050;
  --glass-bg:rgba(255,255,255,.88); --glass-bg-strong:rgba(255,255,255,.94);
}
:root {
  /* ── Part A: 랜딩 ── */
  --ink:#0E0E10; --ink-soft:#2A2A2E; --graphite:#6B6B70;
  --line:#E4E4E7; --paper-a:#F4F4F2; --white:#FFFFFF;
  --accent:#C8873F; --accent-soft:#E8C79A; --accent-deep:#9C6A2E;
  /* ── 문서(종이) — 테마 불변 ── */
  --paper:#F7F6F1; --paper-ink:#1E1E22; --paper-line:#D5D2C6; --paper-section:#E9E7DE;
  /* ── 공통 ── */
  --font-display:'Space Grotesk','Pretendard',sans-serif;
  --font-body:'Pretendard',sans-serif;
  --font-mono:'JetBrains Mono',monospace;
  --header-h:64px; --sidebar-w:400px; --gap:24px;
  --r-input:4px; --r-card:8px; --r-panel:12px; --r-hero:16px; --r-pill:999px;
  --ease:cubic-bezier(.2,.8,.2,1);
}
```

---

# F. 화면 인벤토리 (v3.0 기준 구현 레퍼런스)

| 화면 | 파일 | 핵심 패턴 |
|---|---|---|
| 랜딩 (아크폼) | `Landing Page.dc.html` | A3.1 영상 히어로, 넘버링 리스트 |
| 메인 (사통팔땅) | `PropAI Main.dc.html` | 보고서 생성 패널(A4 선택 카드) |
| 관제 홈 | `Satong Home v2 (Dark).dc.html` | B3.2, 생성 허브, Parcel Intake, Output Dock |
| 프로젝트 대시보드 | `Dashboard (Light).dc.html` | 스테퍼, KPI, 모듈 카드, 리스크 알림 |
| 멀티지도 | `Satong Map (Light).dc.html` | 레이어 레일, 지적 폴리곤, 팝오버 |
| CAD 스튜디오 | `CAD Studio (Light).dc.html` | 평면 SVG, AI 설계안, 법규 패널 |
| BIM 스튜디오 | `BIM Studio (Light).dc.html` | 모델 트리, 아이소메트릭, BOQ |
| CAD·BIM 엔진 | `CADBIM Engine (Light).dc.html` | L1–L5, 2D⇄3D 정합, 음성 명령 바 |
| 수지분석 | `Feasibility Studio (Light).dc.html` | B5.2 편집 테이블, 민감도, 현금흐름 |
| 적산 | `Cost Estimation (Light).dc.html` | 공종 WBS, 내역서 편집, 간접비 연동 |
| 토지조서·등기 | `Land Registry (Light).dc.html` | 징구현황 체크, ㎡/평, 종이 등기부 |
| 법규검토 | `Legal Review (Light).dc.html` | 판정 칩, 정북사선 단면, 로드맵 |
| 보고서 | `Report Studio (Light).dc.html` | 산출물 선택, 종이 표지, 생성 이력 |

*v3.0 — 2026-07-15. 화면 12종에서 검증된 패턴(앱 셸·편집 테이블·지도 레일·2D/3D 정합·종이 문서·단위 병기·고지 체계)을 지침으로 역반영. v2.0의 A/B 구조 유지.*
