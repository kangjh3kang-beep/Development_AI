"use client";

/**
 * FieldSourceBadge — 필드 단위 출처(provenance) 공용 칩.
 *
 * user(수동) = 파랑: 금융 모델링의 "직접 입력값 = 파랑" 색상 관행.
 * auto(자동) = 회색: 파이프라인 산출값 — 재분석 시 갱신될 수 있음을 알린다.
 *
 * 순수 presentational — 네트워크 호출·store 접근 없음. 출처 판정은 호출부
 * (useProjectContextStore.manualFields → getFieldProvenance)가 담당한다.
 * 디자인 토큰(CSS 변수)만 사용, title 안내문으로 의미를 설명한다.
 */

// store(useProjectContextStore)의 FieldSource와 구조 동일 — 의존 없이 단독 사용
// 가능하도록 로컬 정의(구조적 타이핑으로 상호 호환).
export type FieldSource = "auto" | "user";

const SOURCE_META: Record<FieldSource, { label: string; cls: string; title: string }> = {
  user: {
    label: "수동",
    cls: "border-[var(--status-info)]/40 bg-[var(--status-info)]/10 text-[var(--status-info)]",
    title: "사용자가 직접 수정한 값 — 재분석·자동 갱신이 이 값을 덮어쓰지 않습니다. 초기화하면 자동 값으로 되돌아갑니다.",
  },
  auto: {
    label: "자동",
    cls: "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-tertiary)]",
    title: "파이프라인 분석이 산출한 값 — 재분석 시 자동으로 갱신됩니다.",
  },
};

/** FieldProvenance.updatedAt(epoch ms) → 로컬 절대시각. 비정상 값이면 미표기(가짜값 금지). */
function stampedAt(updatedAt?: number): string | null {
  if (updatedAt == null || !Number.isFinite(updatedAt)) return null;
  const d = new Date(updatedAt);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

export function FieldSourceBadge({
  source,
  updatedAt,
  className = "",
}: {
  source: FieldSource;
  /** manualFields stamp의 updatedAt(epoch ms) — 전달 시 title에 수정 시각을 덧붙인다. */
  updatedAt?: number;
  className?: string;
}) {
  const meta = SOURCE_META[source];
  // 런타임에 알 수 없는 source가 들어오면 출처를 단정하지 않고 미표시(정직성).
  if (!meta) return null;

  const at = stampedAt(updatedAt);
  const title = at ? `${meta.title} (수정 시각: ${at})` : meta.title;

  return (
    <span
      title={title}
      aria-label={`값 출처: ${meta.label}`}
      className={`inline-flex shrink-0 cursor-help items-center rounded-full border px-1.5 py-0.5 text-[9px] font-bold leading-none ${meta.cls} ${className}`}
    >
      {meta.label}
    </span>
  );
}
