# 68 — 부지분석 "AI 해석" 아코디언 부각 (클릭 유도 CTA)

## 1. 대상 컴포넌트 · 아코디언 위치
- **표준 컴포넌트:** `propai-platform/apps/web/components/analysis/AnalysisVerdict.tsx`
  - 검증 배지 + AI 해석을 단일 카드로 결합하는 표준 컴포넌트(앱 3곳에서 재사용).
  - 부지분석은 `components/pipeline/SiteAnalysisDetail.tsx:334`에서
    `interpretationTitle="AI 부지분석 해석"` + `sectionLabels`(10섹션)로 이 컴포넌트를 호출.
- **아코디언 토글 로직:** `const [open, setOpen] = useState(defaultOpen)` (AnalysisVerdict.tsx)
  - 기존: 접힘 시 작은 텍스트 링크("✦ AI 부지분석 해석 [N개 섹션] … 해석 보기/접기")만 노출 → 클릭 유도 약함.

## 2. 변경 파일
- `components/analysis/AnalysisVerdict.tsx` (단일 파일, +80 / -30)
  - 부지분석 외 이 컴포넌트를 쓰는 모든 화면의 AI 해석 노출이 함께 개선됨(표준화 효과).

## 3. 부각 방식
- **접힘 = CTA 카드:** `min-h-[64px]`(터치타깃 ≥44px 충족) 카드.
  - ✨ 아이콘 배지(`bg-[var(--accent-strong)]` + `shadow-glow`) + `animate-ping` 펄스(은은하게, opacity-20).
  - 라벨 `{interpretationTitle}` + `{N}개 섹션` 칩.
  - **프리뷰:** 첫 섹션 본문 160자 `line-clamp-2`(없으면 "종합요약·용적·시세·입지·개발계획 등" 폴백) → "내용이 더 있다" 암시.
  - 보조문 "탭하여 AI 상세 해석 보기" + 쉐브론 `▾`(hover 시 살짝 내려감).
  - 강조 테두리 `border-[var(--accent-strong)]/40` + `bg-[var(--accent-soft)]`, hover/focus 상태.
- **펼침:** 기존 10섹션 그대로 + "접기 ▴" 버튼. 헤더 위계 소폭 강화(섹션 제목 10px→11px, 타이틀 11px→13px).
- **토큰만 사용:** `--accent-strong/--accent-soft/--surface-soft/--surface-muted/--text-primary/--text-secondary/--text-hint/--line/--shadow-sm/--shadow-glow`. 하드코딩 색 0(아이콘 글자만 white-on-accent = 의도된 고대비).

## 4. 기능 무파괴 · 접근성
- 데이터/호출/normalize 로직 무변경 — 마크업·클래스만 변경.
- 토글: `setOpen(true)`/`setOpen(false)`로 분기(각 분기는 한 상태에서만 렌더 → 기존 토글과 동일 동작).
- `aria-expanded` 양쪽 분기 정확 표기, `<button type="button">` 유지, `focus-visible:ring` 추가.
- 펄스는 전역 `@media (prefers-reduced-motion: reduce)`(globals.css:230)가 애니메이션 비활성 → 모션 민감 사용자 존중.

## 5. tsc / eslint / import 보존
- `tsc --noEmit` EXIT 0.
- `eslint AnalysisVerdict.tsx` EXIT 0.
- git diff: 삭제된 import 0(`useMemo`/`useState`/`VerificationBadge` 유지). 린터 import 삭제 함정 회피.

## 6. 커밋
- 메시지: `style(site-analysis): AI 해석 아코디언 부각 — 클릭 유도 CTA·프리뷰·쉐브론(직관성)`
- 해시: (본문 하단 참조)

## 7. 미진점
- `line-clamp-2`/`animate-ping`은 Tailwind v4 빌트인 — 프로덕션 빌드에서 클래스 purge 미발생 확인 권장(코드베이스 내 기존 사용처 존재하여 안전).
- 펼침 전환 애니메이션(height collapse)은 미적용(과한 모션 지양). 필요 시 후속.
- push/배포 금지 준수 — 로컬 커밋까지만.
