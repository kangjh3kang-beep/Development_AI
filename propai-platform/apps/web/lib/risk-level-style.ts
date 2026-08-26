/**
 * 종합 리스크 등급 → 배지 스타일. **SSOT 는 백엔드 사다리**
 * `app/services/regulation/protection_zone_severity.SEVERITY_ORDER`(5종)다.
 *
 * ★왜 `lib/` 에 있나: 1,500줄 클라이언트 패널 안에 있으면 순수 함수 테스트가
 *   `next/dynamic`·`apiClient`·지도 셸까지 통째로 임포트한다 — 그중 하나만 깨져도
 *   계약과 무관하게 락이 죽는다(적대 리뷰 지적).
 */

/**
 * ★**닫힌 톤 집합** — 등급표가 색 문자열을 **자유롭게 쓰지 못하게** 한다.
 *
 * 이게 없으면 *"5종이 서로 다른 색"* 이라는 계약이 **철자 비교**로 전락한다:
 * `"중간"` 을 `bg-green-500/20 text-green-400` 으로 바꾸면 문자열은 다른데
 * **실제 색은 `낮음` 과 거의 같다**(oklab Δ 0.0217 · `/20` 알파에서 ≈0.004).
 * 적대 리뷰가 그 변이로 **락 14개를 전부 통과**시켰다(2026-08-27).
 * 이제 그런 값은 타입이 거부한다 — 「초록」의 철자가 하나뿐이기 때문이다.
 *
 * 톤 이름은 **의미가 아니라 외관**으로 짓는다(`safe`·`low` 같은 의미 이름은
 * 등급 이름과 섞여 다음 사람을 헷갈리게 한다).
 */
const RISK_TONE = {
  green: "bg-[var(--status-success)]/20 text-[var(--status-success)]",
  yellow: "bg-yellow-400/20 text-yellow-300",
  amber: "bg-[var(--status-warning)]/20 text-amber-400",
  orange: "bg-orange-500/20 text-orange-400",
  red: "bg-[var(--status-error)]/20 text-[var(--status-error)]",
  /** 표에 없는 등급 — **안전색으로 낮추지 않는다.** */
  neutral: "bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
} as const;

export type RiskTone = keyof typeof RISK_TONE;

/**
 * 등급 → 톤. **키 집합의 SSOT 는 백엔드 `SEVERITY_ORDER` 5종**이고
 * `apps/api/tests/test_risk_level_label_parity.py` 가 그것을 강제한다.
 *
 * ★색 배치 근거(실측 · oklab 인접거리, 다크/라이트 동일):
 *   종전 배치는 `보통`(`--status-warning` `#f59e0b`)과 `중간`(amber-500)이
 *   **Δ 0.0000 — 같은 색**이었다. 사다리가 5단인데 색 정거장이 4개뿐이라 생긴 일이다.
 *   그래서 `보통` 을 yellow 쪽으로 한 칸 밀어 **다섯 정거장**을 만들었다:
 *     낮음→보통 0.2242 · 보통→중간 0.0789 · 중간→높음 0.0960 · 높음→극히높음 0.1042
 *     **인접 최소 0.0000 → 0.0789**(대조군: 사다리 양 끝 0.3638)
 *   ★`보통` 의 표시가 바뀐다 — 의도된 변경이다(그것을 안 바꾸면 `중간` 이 앉을 자리가 없다).
 */
export const RISK_LEVEL_TONE: Record<string, RiskTone> = {
  "낮음": "green",
  "보통": "yellow",
  "중간": "amber",
  "높음": "orange",
  "극히 높음": "red",
};

/** 표에 없는 등급이 받는 톤. **안전색이 아니다.** */
export const RISK_UNKNOWN_TONE: RiskTone = "neutral";

/**
 * 톤 → **글자색만** 주는 클래스. 배지(배경+글자)와 달리 **단색 하나**가 필요한 표면용이다
 * (`DominantConstraintBanner` 의 아이콘·테두리 칩).
 *
 * ★왜 CSS 변수 하나로 안 주나: 이 앱은 `@theme inline` 이라 Tailwind 팔레트가 **런타임 CSS
 *   변수로 나오지 않는다**(실측). 그래서 `var(--color-yellow-400)` 같은 인라인 색은 쓸 수 없고,
 *   **클래스**가 두 표면을 잇는 유일한 공용 축이다.
 * ★테두리는 `border-current` 로 글자색을 따라가게 한다 — 색을 두 번 적지 않는다.
 */
const RISK_TONE_TEXT: Record<RiskTone, string> = {
  green: "text-[var(--status-success)]",
  yellow: "text-yellow-300",
  amber: "text-amber-400",
  orange: "text-orange-400",
  red: "text-[var(--status-error)]",
  neutral: "text-[var(--text-hint)]",
};

/** 톤 → 글자색 클래스. */
export function riskToneTextClass(tone: RiskTone): string {
  return RISK_TONE_TEXT[tone];
}

/**
 * 등급 → 글자색 클래스. **미지 등급은 중립**(안전색 금지) — 배지와 **같은 판정**을 쓴다.
 *
 * ★이것이 있는 이유: 종전에 배너가 자기 `switch` 로 5등급을 **3색**으로 접었고
 *   (`극히 높음`=`높음`=error · `중간`=`보통`=warning), 배지가 5색이 되자 **같은 필지가
 *   화면 두 곳에서 다른 색**이 될 판이었다(동료 통합자 지적 · 2026-08-27).
 *   한 곳을 고치면 전역이 따라오게 — 이 저장소의 「전역 전파방지」 규율이다.
 */
export function riskLevelTextClass(level: unknown): string {
  const key = typeof level === "string" ? level.trim() : "";
  return riskToneTextClass(RISK_LEVEL_TONE[key] ?? RISK_UNKNOWN_TONE);
}

/** 톤 이름 → 클래스 문자열. 표 밖에서 색을 손으로 베끼지 않게 노출한다. */
export function riskToneClass(tone: RiskTone): string {
  return RISK_TONE[tone];
}

/** 톤 이름 전수(테스트가 중복 색을 검사할 때 쓴다). */
export function allRiskTones(): readonly RiskTone[] {
  return Object.keys(RISK_TONE) as RiskTone[];
}

/**
 * 리스크 등급 → 배지 클래스. **미지 등급은 중립**(안전색 금지).
 *
 * ★`typeof` 가드가 있는 이유: 소비처가 `result?.development_plans || {}` 로 받는
 *   **무타입 객체**라 `risk_level` 이 `any` 다. 종전 `표[x]` 는 무엇이 와도 안 던졌는데
 *   `x.trim()` 은 문자열 아닌 truthy 에서 **TypeError → 렌더 폭발**이 된다.
 *   백엔드 계약상 str 이지만(도달성 **미측정**) 견고성을 깎을 이유가 없다.
 */
export function riskLevelStyle(level: unknown): string {
  const key = typeof level === "string" ? level.trim() : "";
  return riskToneClass(RISK_LEVEL_TONE[key] ?? RISK_UNKNOWN_TONE);
}
