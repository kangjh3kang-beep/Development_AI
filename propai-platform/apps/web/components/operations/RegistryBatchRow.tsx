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

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { isAnalyzed, rowReason, type BatchOutcome } from "@/lib/registry-analyze";
import { isSignedUrlExpired, signedUrlExpiryDay } from "@/lib/signed-url";

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
        fetched?: {
          select_note?: string | null;
          /** 발급된 등기부 PDF 의 서명 URL(서버 보관·30일). 권리분석 실패와 **무관하게** 존재한다. */
          pdf_url?: string | null;
          /** 이미 발급받은 등기부를 재사용했는가(재발급 과금 없음). */
          reused_issue?: boolean;
          /** 그 등기부를 언제 발급했는가(ISO). 재사용 시 화면이 시점을 말할 수 있어야 한다. */
          issued_at?: string | null;
        } | null;
      })
    | null;
};

/** ISO 시각 → `YYYY-MM-DD`. 파싱 실패하면 **원문을 그대로** 둔다(지어내지 않는다). */
function issuedDay(iso?: string | null): string | null {
  const s = (iso || "").trim();
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toISOString().slice(0, 10);
}

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
  // ★등기부 PDF 는 **권리분석이 실패해도 발급돼 있다.** 종전엔 이 행에 링크가 없어,
  //   돈을 내고 받은 문서를 사용자가 열어 볼 방법이 목록에 없었다(상세를 눌러야 했다).
  const pdfUrl = (item.result?.fetched?.pdf_url || "").trim();
  // ★만료를 **누르기 전에** 안다. 서명 URL 의 토큰(JWT)에 `exp` 가 들어 있어 요청 없이 읽힌다.
  //   종전엔 만료된 링크도 살아 있는 것과 똑같이 그려, 누르면 JSON 오류 덩어리가 열렸다
  //   (라이브 실측: 저장 79건 중 표본 3건에서 2건 만료).
  //   ★못 읽으면 만료로 몰지 않는다 — 살아 있는 링크를 죽은 것으로 만들지 않는다.
  // ★시계는 **렌더 중에 읽지 않는다**(React 19 순수성 — 린터가 잡았다).
  //   마운트 후 한 번 읽고, 그 전까지는 `null` 이라 **만료로 몰지 않는다** —
  //   첫 페인트에 살아 있는 링크를 죽은 것으로 그리는 것보다 그쪽이 안전하다
  //   (이 모듈의 원칙과 같다: 모르면 감추지 않는다).
  const [nowMs, setNowMs] = useState<number | null>(null);
  useEffect(() => setNowMs(Date.now()), []);
  const pdfExpired = pdfUrl && nowMs !== null ? isSignedUrlExpired(pdfUrl, nowMs) : false;
  const pdfExpiryDay = pdfUrl ? signedUrlExpiryDay(pdfUrl) : null;
  const reusedDay = item.result?.fetched?.reused_issue
    ? issuedDay(item.result?.fetched?.issued_at)
    : null;

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

      {/* 이미 발급받은 등기부는 다시 발급하지 않는다 — 언제 발급분인지 밝힌다.
          조용히 옛 등기부를 보여 주면 그 자체가 거짓이 된다(등기는 변한다). */}
      {reusedDay && (
        <span
          data-testid="row-reused"
          title={`이미 발급받은 등기부를 재사용했습니다(재발급 과금 없음) — ${reusedDay} 발급분`}
          className="rounded-full border border-[var(--line)] px-2 py-0.5 text-[var(--text-hint)]"
        >
          {reusedDay} 발급분
        </span>
      )}

      {pdfUrl && !pdfExpired && (
        <a
          href={pdfUrl}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="row-pdf"
          className="rounded-md bg-[var(--accent-strong)] px-2 py-0.5 font-bold text-white"
        >
          PDF ↗
        </a>
      )}

      {pdfUrl && pdfExpired && (
        /* 죽은 링크를 살아 있는 것처럼 그리지 않는다. 대신 **왜 못 쓰는지**를 말한다. */
        <span
          data-testid="row-pdf-expired"
          title={`발급 링크가 ${pdfExpiryDay ?? "이전"}에 만료되었습니다 — 다시 발급해야 받을 수 있습니다`}
          className="rounded-md border border-[var(--line-strong)] px-2 py-0.5 text-[var(--text-hint)]"
        >
          PDF 만료{pdfExpiryDay ? ` · ${pdfExpiryDay}` : ""}
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
