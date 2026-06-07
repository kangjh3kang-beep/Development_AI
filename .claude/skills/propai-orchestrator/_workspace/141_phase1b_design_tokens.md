# Phase1-B: 디자인 토큰화 · 다크모드 대비 보정

> 대상: `propai-platform/apps/web` (Next.js 16 · React 19 · Tailwind v4)
> 근거: `130_design_ux_audit.md` §1.2 (B-1·B-2 토큰 우회 하드코딩)
> 원칙: className/스타일 토큰만. 로직·구조·텍스트·import 불변. push/배포 없음.
> 작성일: 2026-06-07

---

## 0. 핵심 결론 — "감사 30건"의 실측 검증

감사가 지목한 `text-slate-900` 30건 등은 **대부분 다크대비 붕괴가 아님**을 grep+코드 확인으로 검증했다. 과도 변경을 피하고 **실제 붕괴분만** 치환했다.

| 분류 | 실측 | 처리 |
|------|------|------|
| `text-slate-900` + `dark:text-*` 페어링 있음 | 대다수 | **유지** (다크에서 dark 변형이 이김 — 정상) |
| `text-gray-900`/`text-gray-800` (페어 없음) on `bg-white`/`bg-gray-50` **라이트 아일랜드** 컴포넌트 | GresbScoreCard, ConversationalMarketPanel, LayerPanel | **유지** (배경도 하드코딩 라이트 → 텍스트 가독. 텍스트만 토큰화하면 오히려 깨짐. 전체 컴포넌트 개편=스코프 초과) |
| `text-black` on 명시적 `bg-white` Google 로그인 버튼 | AuthWorkspaceClient:829 | **유지** (브랜드 버튼, 의도적 흰 배경) |
| **`bg-white`(페어 없음) + `text-[var(--text-*)]` 토큰 텍스트** | **8건** | **치환** (다크에서 토큰 텍스트=거의 흰색인데 배경 강제 흰색 → 텍스트 증발. 진짜 붕괴) |
| 공유 헤더 `ModulePlaceholder` 인디고 (토큰 표면 위) | 3곳 | **치환** (전 단계 헤더에 비공식 2차 강조색 번짐) |
| `legal` 로딩 스피너 `border-teal-500` | 1곳 | **치환** (브랜드 accent의 오프토큰 하드코딩) |

핵심 붕괴 패턴: **`bg-white`(다크 미반응) × `text-[var(--text-primary/secondary)]`(다크에서 #e1e1ee 근백색)** = 흰 글자 on 흰 배경. globals.css 보정 레이어(text-slate-400/500/600만)도 못 잡는 영역.

---

## 1. 치환 목록 (파일 · 전 → 후)

### 1.1 `bg-white` → `bg-[var(--surface)]` (다크대비 붕괴 8건)
`--surface`: 라이트 `#ffffff` (시각 동일) / 다크 `#11131b` (토큰 텍스트와 대비 복원)

| 파일 | 전 | 후 |
|------|------|------|
| `components/agent/AgentTimeline.tsx:100` | `rounded-full bg-white ... text-[var(--text-secondary)]` | `bg-[var(--surface)]` |
| `components/pwa/PwaStatusCard.tsx:190` | `bg-white ... text-[var(--text-primary)]` (refresh 버튼) | `bg-[var(--surface)]` |
| `components/pwa/PwaStatusCard.tsx:214` | `bg-white ... text-[var(--text-primary)]` (install 버튼) | `bg-[var(--surface)]` |
| `components/projects/ProjectContractWorkspaceClient.tsx:560` | `<textarea ... bg-white ... text-[var(--text-primary)]>` | `bg-[var(--surface)]` |
| `components/drone/DefectHeatmap.tsx:128` | `bg-white ... text-[var(--text-secondary)]` | `bg-[var(--surface)]` |
| `components/analytics/WorkspaceQueryErrorCard.tsx:34` | `bg-white ... text-[var(--text-primary)]` (retry 버튼) | `bg-[var(--surface)]` |
| `app/offline/page.tsx:24` | `bg-white ... text-[var(--text-primary)]` (Link) | `bg-[var(--surface)]` |

### 1.2 `hover:bg-white` → `hover:bg-[var(--surface-strong)]` (1건)
| 파일 | 전 | 후 |
|------|------|------|
| `components/auth/KakaoCallbackWorkspaceClient.tsx:204` | `text-[var(--text-primary)] transition hover:bg-white` | `hover:bg-[var(--surface-strong)]` (호버 시 토큰 텍스트가 흰배경에 증발하던 것 복원) |

### 1.3 ModulePlaceholder 인디고 → `--chart-2` (공유 헤더, 3곳)
`--chart-2`: 라이트 `#6366f1` / 다크 `#818cf8` — 토큰 정의된 인디고 등가색. 전 단계 헤더 일관 + 라이트/다크 명도 보장.

| 파일 | 전 | 후 |
|------|------|------|
| `components/layout/ModulePlaceholder.tsx:24` | `bg-indigo-500` (좌하 글로우) | `bg-[var(--chart-2)]` |
| `:36` | `border-indigo-500/30 bg-indigo-500/10 text-indigo-500 dark:text-indigo-400` (statusLabel 칩) | `border-[var(--chart-2)]/30 bg-[var(--chart-2)]/10 text-[var(--chart-2)]` |
| `:52` | `to-indigo-500/10` (그라데이션) | `to-[var(--chart-2)]/10` |

### 1.4 legal 로딩 스피너 → `--accent` (1곳)
| 파일 | 전 | 후 |
|------|------|------|
| `app/[locale]/(dashboard)/projects/[id]/legal/page.tsx:18` | `border-teal-500 border-t-transparent` | `border-[var(--accent)] border-t-transparent` (teal=브랜드 accent, 시각 동일 + 토큰 정합) |

**총 9개 파일 / 11개 className 변경.**

---

## 2. 다크대비 보정 방식

- **신규 globals.css 보정 레이어 추가 안 함.** 기존 `:where(.dark)` 레이어(text-slate-400/500/600)에 `text-gray-900`/`text-black` 추가를 검토했으나, 명시도 (0,1,0)·소스순서 뒤라 **페어 없는 `text-gray-900`를 라이트 아일랜드(GresbScoreCard 등)에서도 강제 변경**해 깨뜨림 → 채택 안 함.
- 대신 **소스 레벨 외과적 치환**(붕괴 표면 `bg-white`만 토큰화)으로 회귀 위험 0.
- 토큰 신규 추가 없음(`--surface`/`--surface-strong`/`--chart-2`/`--accent` 모두 tokens.css 기존 정의).

---

## 3. 유지한 의미색 (의도적 미변경)

- **상태색** `bg-emerald-500`(성공)·`bg-amber-500`(경고)·`bg-red-500`(오류): 다크에서도 의도적 의미 전달, 붕괴 없음 → 유지.
- **라이트 아일랜드 컴포넌트**(GresbScoreCard, ConversationalMarketPanel, LayerPanel): 배경+텍스트 모두 하드코딩 라이트로 자기완결. `text-gray-900`/`text-gray-800` on `bg-gray-50`/`bg-white` 가독 정상 → 유지(텍스트만 토큰화 시 역붕괴).
- **AuthWorkspaceClient Google 버튼** `text-black on bg-white`: 브랜드 규격 → 유지.
- **`feasibility`/`agent/page.tsx` `text-slate-900 dark:text-*`**: 다크 페어 존재 → 유지.
- ModulePlaceholder 외 데코 `bg-white/5~10`(반투명 오버레이): 의도적 글래스 효과 → 유지.

---

## 4. 기능 불변 확인

- `git diff` 전수 확인: **11개 변경 전부 className 내 색상 토큰 치환만.** 로직·JSX 구조·핸들러·텍스트·prop 변경 0.
- **import 라인 변경 0** (린터 import 트랩 점검: 9개 파일 `git diff | grep import` → 변경 없음).
- 사전 존재하던 미커밋 변경(`ProjectConstructionWorkspaceClient`·`ProjectEsgWorkspaceClient`·`ProjectFinanceWorkspaceClient`·`useProjectContextStore`)은 **본 작업과 무관, 손대지 않음.** `git add`는 명시 9경로만.

## 5. 검증

- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0** (통과).
- push/배포 없음.
