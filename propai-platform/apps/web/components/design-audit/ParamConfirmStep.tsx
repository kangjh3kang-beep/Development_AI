"use client";

/**
 * ParamConfirmStep — 설계심사(DA-7) ⑵개요: 추출 필드 그리드(확인·수정).
 *
 * BriefUploadStep이 추출한 BriefField[]를 그리드로 보여주고 인라인 수정한다.
 *  - 출처 배지: 추출 직후 = '추출' 칩(개요서 원문 quote를 title 툴팁으로 부연),
 *    사용자가 값을 바꾸면 공용 FieldSourceBadge(source="user", '수동')로 전환.
 *    (FieldSourceBadge는 auto/user 2종만 지원하는 공용 부품이라 '추출' 라벨은
 *     이 화면 전용 칩으로 표기하되, 시각 규격은 FieldSourceBadge와 동일하게 맞춘다.)
 *  - 원래(추출) 값으로 되돌리면 다시 '추출'로 복귀 — 출처 전환 판정은 부모
 *    (DesignAuditWorkspace.handleFieldChange)가 extractedValue 대조로 수행한다.
 *
 * 순수 presentational — 네트워크 호출·store 접근 없음. 디자인 토큰만 사용.
 */

import { FieldSourceBadge } from "@/components/common/FieldSourceBadge";
import type { BriefField } from "./BriefUploadStep";

/** '추출' 출처 칩 — FieldSourceBadge와 동일 시각 규격(크기·radius·폰트). */
function ExtractedBadge({ quote }: { quote?: string | null }) {
  const title = quote?.trim()
    ? `개요서에서 추출된 값 — 원문: "${quote.trim()}"`
    : "개요서에서 추출된 값 — 수정하면 '수동'으로 표시됩니다.";
  return (
    <span
      title={title}
      aria-label="값 출처: 추출"
      className="inline-flex shrink-0 cursor-help items-center rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--accent-strong)]"
    >
      추출
    </span>
  );
}

export function ParamConfirmStep({
  fields,
  disabled = false,
  onChange,
}: {
  fields: BriefField[];
  disabled?: boolean;
  /** 필드 값 수정 콜백 — 출처(extracted/user) 전환 판정은 부모가 담당. */
  onChange: (key: string, value: string) => void;
}) {
  // 빈 결과 정직 표기 — 가짜 placeholder 필드를 만들지 않는다.
  if (fields.length === 0) {
    return (
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 text-xs text-[var(--text-hint)]">
        추출된 개요 필드가 없습니다. 위에서 개요 PDF/텍스트를 추출하거나, 이 단계를 건너뛰고
        진행할 수 있습니다(개요 없이 실행하면 개요 기반 검증 항목은 제한됩니다).
      </div>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {fields.map((f) => (
        <div
          key={f.key}
          className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3"
        >
          <div className="flex items-center justify-between gap-2">
            <span
              className="truncate text-[11px] font-semibold text-[var(--text-tertiary)]"
              title={f.label}
            >
              {f.label}
              {f.unit ? ` (${f.unit})` : ""}
            </span>
            {f.source === "user" ? (
              <FieldSourceBadge source="user" />
            ) : (
              <ExtractedBadge quote={f.quote} />
            )}
          </div>
          <input
            value={f.value}
            disabled={disabled}
            onChange={(e) => onChange(f.key, e.target.value)}
            placeholder="값 입력"
            title={
              f.quote?.trim()
                ? `개요서 원문: "${f.quote.trim()}"`
                : undefined
            }
            className="mt-1.5 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5 text-sm font-bold text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)] disabled:opacity-50"
          />
          {f.quote?.trim() && (
            <p
              className="mt-1 truncate text-[10px] text-[var(--text-hint)]"
              title={`개요서 원문: "${f.quote.trim()}"`}
            >
              ❝{f.quote.trim()}❞
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
