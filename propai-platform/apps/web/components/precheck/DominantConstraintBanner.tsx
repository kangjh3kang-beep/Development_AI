"use client";

/**
 * 지배 제약 배너 — 필지 상세 최상단(사통맵 v2 W1).
 *
 * 설계사·디벨로퍼가 필지를 열자마자 얻어야 하는 답은 하나다: **"무엇이 발목인가."**
 * 값은 전부 서버 산정(regulation/dominant_constraint)이고, 이 컴포넌트는 표시만 한다
 * (프론트에서 severity를 다시 판정하거나 높이를 계산하지 않는다 — SSOT 이중화 금지).
 *
 * ★정직 표기 두 곳(이 컴포넌트의 존재 이유):
 *   ① `height.incomplete`면 숫자 옆에 **"일부 미반영"** 배지 — 고도지구·비행안전구역처럼
 *      지정은 됐지만 플랫폼이 수치를 못 가진 항목이 있어 그 숫자가 최종이 아니다.
 *   ② 제약이 0건이면 **아무것도 렌더하지 않는다**(빈 배너는 노이즈이자 거짓 안심).
 */

import { AlertTriangle, Ruler } from "lucide-react";

import type { DominantConstraint } from "@/lib/satong-map-layers";

/** severity → 색. protection_zone_severity SSOT의 5등급을 그대로 받는다(새 등급 정의 금지). */
function severityColor(severity: string | null | undefined): string {
  switch (severity) {
    case "극히 높음":
      return "var(--status-error)";
    case "높음":
      return "var(--status-error)";
    case "중간":
      return "var(--status-warning)";
    case "보통":
      return "var(--status-warning)";
    default:
      return "var(--text-hint)";
  }
}

export function DominantConstraintBanner({
  constraint,
}: {
  constraint?: DominantConstraint | null;
}) {
  const headline = constraint?.headline || null;
  const height = constraint?.height ?? null;
  const heightItems = height?.items ?? [];
  // 말할 것이 없으면 렌더하지 않는다(빈 배너 금지 — 서버도 None을 주지만 이중 방어).
  if (!headline && heightItems.length === 0) return null;

  const ranked = constraint?.ranked ?? [];
  const nextUp = ranked.slice(1, 3);

  return (
    <div
      data-testid="dominant-constraint-banner"
      className="mt-3 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3"
    >
      {headline ? (
        <>
          <div className="flex items-center gap-1.5">
            <AlertTriangle
              className="size-3.5 shrink-0"
              style={{ color: severityColor(constraint?.severity) }}
              aria-hidden
            />
            <span className="text-[11px] font-black uppercase tracking-[0.14em] text-[var(--text-hint)]">
              지배 제약
            </span>
            {constraint?.severity ? (
              <span
                className="rounded-full px-1.5 py-px text-[10px] font-black"
                style={{
                  color: severityColor(constraint.severity),
                  border: `1px solid ${severityColor(constraint.severity)}`,
                }}
              >
                {constraint.severity}
              </span>
            ) : null}
          </div>
          <p
            data-testid="dominant-constraint-headline"
            className="mt-1 break-keep text-[13px] font-bold leading-snug text-[var(--text-primary)]"
          >
            {headline}
          </p>
          {nextUp.length > 0 ? (
            <p className="mt-1 break-keep text-[11px] font-semibold text-[var(--text-hint)]">
              그다음: {nextUp.map((r) => r.name).join(" · ")}
            </p>
          ) : null}
        </>
      ) : null}

      {heightItems.length > 0 ? (
        <div
          data-testid="dominant-constraint-height"
          className={`${headline ? "mt-2 border-t border-[var(--border-muted)] pt-2" : ""}`}
        >
          <div className="flex items-center gap-1.5">
            <Ruler className="size-3.5 shrink-0 text-[var(--text-hint)]" aria-hidden />
            <span className="text-[11px] font-black uppercase tracking-[0.14em] text-[var(--text-hint)]">
              높이 상한
            </span>
            {height?.governing_m != null ? (
              <>
                <span className="font-mono text-[13px] font-black text-[var(--text-primary)]">
                  {height.governing_m}m
                </span>
                {height.governing_source ? (
                  <span className="text-[10px] font-bold text-[var(--text-hint)]">
                    ({height.governing_source}가 지배)
                  </span>
                ) : null}
              </>
            ) : (
              // 수치 보유 항목이 하나도 없으면 숫자를 만들지 않는다(추정 금지).
              <span className="text-[11px] font-bold text-[var(--text-hint)]">
                수치 미보유 — 조례 확인 필요
              </span>
            )}
            {height?.incomplete ? (
              <span
                data-testid="dominant-constraint-height-incomplete"
                className="rounded-full border border-[var(--status-warning)] px-1.5 py-px text-[10px] font-black text-[var(--status-warning)]"
                title="수치를 보유하지 않은 높이 제약이 있어 이 값이 최종이 아닙니다"
              >
                일부 미반영
              </span>
            ) : null}
          </div>
          <ul className="mt-1 space-y-0.5">
            {heightItems.map((item, i) => (
              <li
                key={`${item.source}-${i}`}
                className="break-keep text-[11px] font-semibold text-[var(--text-secondary)]"
              >
                · {item.source}{" "}
                {item.limit_m != null ? (
                  <span className="font-mono font-bold">{item.limit_m}m</span>
                ) : (
                  <span className="text-[var(--text-hint)]">지정됨</span>
                )}
                {[item.basis, item.note].filter(Boolean).length > 0 ? (
                  // 근거(basis)와 한계(note)를 **둘 다** 보여준다 — 정북일조의 "직사각 근사"
                  //   같은 한계 문구를 떨어뜨리면 근사값이 확정처럼 읽힌다.
                  <span className="text-[var(--text-hint)]">
                    {" — "}
                    {[item.basis, item.note].filter(Boolean).join(" · ")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export default DominantConstraintBanner;
