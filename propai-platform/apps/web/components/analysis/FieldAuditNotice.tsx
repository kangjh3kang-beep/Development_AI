/**
 * FieldAuditNotice — 자가검증 지적을 해당 섹션 안에 붙이는 인라인 고지.
 *
 * ## 표기 원칙 (전부 실측 근거로 정해진 것)
 *
 * - **새 배지(알약형 칩)를 만들지 않는다.** 이 보고서 화면은 이미 배지가 19종이라 직전
 *   캠페인에서 인터페이스가 무너진 임계(9종)의 두 배다. 여기서는 테두리 상자 + 글자만 쓴다.
 * - **심각도를 색으로만 말하지 않는다.** 색을 못 보는 사용자에게도 "사용 보류 권고"/"확인 필요"
 *   라는 **글자**가 먼저 읽혀야 한다.
 * - **"차단"이라고 쓰지 않는다.** 이 점검은 관측 전용이라 실제로 아무것도 막지 않는다.
 *   대신 P0는 "사용 보류 권고"로, 무엇을 대신 봐야 하는지까지 적는다.
 * - **항상 뜨는 방법론 고지(시세 추정·분양가 점추정)는 경고가 아니라 회색 각주**다. 매번
 *   경고색으로 칠하면 진짜 이상이 떴을 때 같이 묻힌다.
 */

"use client";

import { AlertTriangle, Info } from "lucide-react";

import {
  copyFor,
  SEVERITY_META,
  type AuditFinding,
} from "@/lib/field-audit";

/** 기대/산출값을 한 줄로 — 값이 없으면 그 줄을 만들지 않는다(빈 괄호 금지). */
function ExpectedObserved({ finding }: { finding: AuditFinding }) {
  const expected = finding.expected;
  const observed = finding.observed;
  const has = (v: unknown) => v !== null && v !== undefined && String(v).trim() !== "";
  if (!has(expected) && !has(observed)) return null;
  return (
    <p className="mt-1 text-[10px] text-[var(--text-hint)] leading-relaxed">
      {has(observed) && <>표시된 값: {String(observed)}</>}
      {has(observed) && has(expected) && " · "}
      {has(expected) && <>규칙 기준: {String(expected)}</>}
    </p>
  );
}

/**
 * 지적 1건. P0/P1은 경고 상자, P2(각주 대상 외)는 조용한 상자.
 */
export function FieldAuditIssue({ finding }: { finding: AuditFinding }) {
  const meta = SEVERITY_META[finding.severity] ?? SEVERITY_META.P2;
  const copy = copyFor(finding);
  const strong = meta.holdValue;

  return (
    <div
      role="note"
      className={`rounded-lg border p-3 ${
        strong
          ? "border-[var(--status-error)]/40 bg-[var(--status-error)]/5"
          : "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/5"
      }`}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          className={`size-4 shrink-0 ${
            strong ? "text-[var(--status-error)]" : "text-[var(--status-warning)]"
          }`}
          aria-hidden
        />
        <div className="min-w-0">
          <p className="text-[11px] font-bold text-[var(--text-primary)]">
            <span className={strong ? "text-[var(--status-error)]" : "text-[var(--status-warning)]"}>
              {meta.label}
            </span>
            {" · "}
            {copy.headline}
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-secondary)] leading-relaxed">
            {copy.action}
          </p>
          <ExpectedObserved finding={finding} />
          {copy.raw && (
            <p className="mt-1 text-[10px] text-[var(--text-hint)]">
              (점검 원문 그대로 — 쉬운 설명 준비 중)
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * 상시 방법론 각주 — "이 숫자는 이렇게 만들어졌다"를 그 자리에서 알린다.
 * 경고가 아니므로 회색이고, 카운터에도 들어가지 않는다.
 */
export function FieldAuditNote({ finding }: { finding: AuditFinding }) {
  const copy = copyFor(finding);
  return (
    <div role="note" className="flex items-start gap-2 text-[10px] text-[var(--text-hint)]">
      <Info className="size-3.5 shrink-0 mt-0.5" aria-hidden />
      <span className="leading-relaxed">
        {copy.headline} — {copy.action}
      </span>
    </div>
  );
}

/**
 * 섹션 하나에 붙는 **방법론 각주**. 없으면 아무것도 렌더하지 않는다(빈 상자를 남겨
 * "점검 통과"처럼 보이게 하지 않는다).
 *
 * ★실제 지적(P0/P1)은 여기가 아니라 상단 요약 카드가 맡는다. 섹션 카드는 접힐 수 있어서
 *   지적을 섹션 안에만 두면 **'사용 보류 권고'가 접힘 안에 갇혀 사용자가 못 본다.**
 *   (구현 중 실제로 이 상태가 만들어져 회귀락에 걸렸다.) 각주는 해당 숫자 옆에서 읽어야
 *   의미가 있으므로 섹션에 남긴다.
 */
export function FieldAuditNotice({ notes }: { notes: AuditFinding[] }) {
  if (notes.length === 0) return null;
  return (
    <div className="space-y-2">
      {notes.map((f, i) => (
        <FieldAuditNote key={`${f.code}:${f.field}:${i}`} finding={f} />
      ))}
    </div>
  );
}
