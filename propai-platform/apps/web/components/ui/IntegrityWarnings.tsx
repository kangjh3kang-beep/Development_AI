/**
 * 법정초과 가드 경고(`integrity_warnings`) — **공용 렌더러**.
 *
 * ## 왜 생겼나 (2026-08-24)
 *
 * 백엔드에 `apply_legal_hotpath_guard`(법정 건폐·용적·층수 초과 + 완화근거 미확인 검출)가
 * 있고 **네 표면**이 그 결과를 응답에 싣는다:
 *
 *     routers/auto_zoning.py:2035              통합분석  ← `warnings` **바로 옆 줄**
 *     services/precheck/precheck_service.py    사전검토
 *     services/feasibility/rough_…orchestrator 개략수지
 *     services/land_intelligence/comprehensive 종합분석
 *
 * ★그런데 **프론트 소비처가 0** 이었다(실측: `integrity` 문자열이 무관한 것들뿐).
 *   가드는 검출해 놓고 **허공에 대고 경고**하고 있었다.
 *
 * ★★더 나쁜 것: 가드가 신뢰도를 강등하며 붙이는 문구가
 *   *"법정상한 초과 + 완화근거 미확인 — **integrity_warnings 참조**."* 다.
 *   **화면에 없는 것을 참조하라고 말한다** — 매달린 참조다.
 *
 * ## 왜 공용인가
 *
 * 네 표면이 같은 배열을 싣는다. 표면마다 따로 그리면 한 곳만 고쳐지고 나머지는 남는다
 * (이 저장소가 반복해 데인 형태). 한 곳을 고치면 전역이 따라오게 한다.
 *
 * ## 무날조
 *
 * 백엔드가 준 `note`·`claim` 을 **그대로** 싣는다. 프론트가 문구를 지어내지 않는다.
 * 배열이 비면(=검출 없음) **아무것도 그리지 않는다** — "이상 없음"이라고 단언하지도 않는다
 * (가드가 돌지 않았을 수도 있으므로 침묵과 무결을 구분해 주장하지 않는다).
 */
"use client";

export type IntegrityWarning = {
  /** 검출 유형(예: `층수제한초과`·`높이제한오표기`). */
  type?: string | null;
  /** 문제가 된 주장값(예: `5층`·`높이 25m`). */
  claim?: string | null;
  /** `high` 이면 근거 미제시(할루시네이션 의심), 그 외는 검토 필요. */
  severity?: string | null;
  /** 사람이 읽는 사유 — 백엔드 원문을 그대로 쓴다. */
  note?: string | null;
};

/** `high` 는 "근거가 없다"는 뜻이라 시각적으로 갈라 준다(나머지는 검토 권고). */
function isHigh(w: IntegrityWarning): boolean {
  return (w.severity || "").toLowerCase() === "high";
}

export function IntegrityWarnings({
  items,
  className = "",
}: {
  items: IntegrityWarning[] | null | undefined;
  className?: string;
}) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (list.length === 0) return null;

  const highCount = list.filter(isHigh).length;
  return (
    <div
      data-testid="integrity-warnings"
      className={
        "rounded-lg border border-[color-mix(in_srgb,var(--status-error)_35%,transparent)] " +
        "bg-[color-mix(in_srgb,var(--status-error)_8%,transparent)] p-2.5 " +
        className
      }
    >
      <p className="mb-1 text-[10px] font-black uppercase tracking-widest text-[var(--status-error)]">
        법정상한 초과 검출 · {list.length}건
        {highCount > 0 ? ` (근거 미확인 ${highCount}건)` : ""}
      </p>
      <ul className="space-y-1">
        {list.map((w, i) => (
          <li
            key={`integrity-${i}`}
            className="text-[10px] leading-relaxed text-[var(--text-secondary)]"
          >
            <span className={isHigh(w) ? "font-bold text-[var(--status-error)]" : "font-bold"}>
              {w.type || "법정초과"}
              {w.claim ? ` · ${w.claim}` : ""}
            </span>
            {w.note ? <span> — {w.note}</span> : null}
          </li>
        ))}
      </ul>
      {/* ★값을 몰래 깎지 않는다(무날조) — 위 수치는 그대로 두고 사실만 알린다. */}
      <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">
        위 수치는 보정하지 않고 그대로 표시합니다 — 완화근거(조례·지구단위계획)를 확인하세요.
      </p>
    </div>
  );
}
