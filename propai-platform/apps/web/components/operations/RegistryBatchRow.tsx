"use client";

/**
 * 일괄 등기분석 결과의 **한 행**.
 *
 * 거대 클라이언트(`RegistryAnalysisWorkspaceClient`) 안에 인라인으로 있던 것을 뽑았다.
 * 이유는 스타일이 아니라 **검증**이다 — 인라인 상태에서는 이 행을 렌더해서 태울 방법이
 * 없어(스토어·api-client·일괄 실행 상태가 전부 필요) 소스 grep 으로만 잠글 수 있었고,
 * 실제로 변이 감사에서 이 행의 렌더 변이가 **전부 생존**했다(2026-08-24, 11건 중 8건).
 * 순수 컴포넌트로 분리하면 픽스처 하나로 직접 렌더해 잠글 수 있다.
 *
 * 이 컴포넌트는 **판정하지 않는다** — `isAnalyzed`·`rowReason`(lib/registry-analyze.ts)이
 * 유일한 판정자다. 화면과 집계가 서로 다른 기준으로 말하지 않게 하기 위함이다.
 */

import { AlertTriangle } from "lucide-react";

import { isAnalyzed, rowReason, type BatchOutcome } from "@/lib/registry-analyze";

/** 안전성 등급 배지 색. 알 수 없는 등급은 중립색으로 — 임의로 위험/안전에 몰지 않는다. */
const GRADE_CLASS: Record<string, string> = {
  안전: "border-[var(--status-success)]/30 bg-[var(--status-success)]/10 text-[var(--status-success)]",
  주의: "border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 text-[var(--status-warning)]",
  위험: "border-[var(--status-error)]/30 bg-[var(--status-error)]/10 text-[var(--status-error)]",
};

export type RegistryBatchRowItem = BatchOutcome & {
  result?:
    | (BatchOutcome["result"] & {
        ai?: { generated?: boolean; failure_reason?: string; safety_grade?: string; summary?: string } | null;
        fetched?: { select_note?: string | null } | null;
      })
    | null;
};

export function RegistryBatchRow({
  item,
  onDetail,
}: {
  item: RegistryBatchRowItem;
  onDetail?: () => void;
}) {
  // ★등급은 **분석이 실제로 나온 건에만** 칠한다. LLM 폴백도 `safety_grade:"주의"` 를 담아
  //   오므로 존재 여부로 칠하면 **아무것도 판정하지 않은 건이 "안전성 주의"로** 보인다
  //   (라이브 2026-08-24 오산 내삼미동 448-2·347-8 — 등기 PDF 는 정상 발급됐다).
  //   없는 판정을 지어내는 것이자, 동시에 진짜 사유를 덮는 것이다.
  const analyzed = isAnalyzed(item);
  const grade = analyzed ? item.result?.ai?.safety_grade : undefined;
  const selectNote = item.result?.fetched?.select_note;

  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px]" data-testid="batch-row">
      <span
        className="min-w-[150px] flex-1 truncate font-semibold text-[var(--text-primary)]"
        title={item.jibun}
      >
        {item.jibun}
      </span>

      {grade ? (
        <span
          data-testid="row-grade"
          className={`rounded-full border px-2 py-0.5 font-bold ${
            GRADE_CLASS[grade] || "border-[var(--line-strong)] text-[var(--text-secondary)]"
          }`}
        >
          안전성 {grade}
        </span>
      ) : (
        /* ★사유를 **보여 준다** — 종전엔 `message` 를 존재 여부로만 써서 "미확보"/"실패"
           두 글자로 뭉갰다(사유는 응답에 있었다). 등기는 받았는데 권리분석만 실패한 건은
           `ai.failure_reason` 에 사유가 실려 온다 — `rowReason` 이 그것까지 읽는다. */
        <span
          className="max-w-[55%] truncate text-[var(--text-hint)]"
          data-testid="row-reason"
          title={rowReason(item)}
        >
          {rowReason(item)}
        </span>
      )}

      {analyzed && item.result?.ai?.summary && (
        <span
          data-testid="row-summary"
          className="hidden max-w-[40%] truncate text-[var(--text-secondary)] sm:inline"
        >
          {item.result.ai.summary}
        </span>
      )}

      {/* 요청과 다른 물건을 조회했을 수 있다는 고지는 목록 행에서도 보여야 한다 —
          '상세'를 눌러야만 보이면 일괄 분석에서 조용히 묻힌다. */}
      {selectNote && (
        <span
          data-testid="row-select-note"
          title={selectNote}
          className="inline-flex items-center gap-1 rounded-full border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/10 px-2 py-0.5 font-bold text-[var(--status-warning)]"
        >
          <AlertTriangle className="size-3" aria-hidden />
          물건 확인 필요
        </span>
      )}

      {item.result && (
        <button
          type="button"
          onClick={onDetail}
          className="rounded-lg bg-[var(--surface-strong)] px-2 py-0.5 font-bold text-[var(--accent-strong)]"
        >
          상세
        </button>
      )}
    </div>
  );
}
