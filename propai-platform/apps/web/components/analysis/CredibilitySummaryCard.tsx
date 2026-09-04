/**
 * CredibilitySummaryCard — "이 보고서의 어디까지가 점검됐나"를 한 자리에서 정직하게 밝힌다.
 *
 * ## 이 카드가 존재하는 이유
 *
 * 사용자 요구는 "어떤 데이터가 정확하고 신빙성 높은지 판단할 수 있게 해달라"였다. 그런데
 * 점검 결과만 늘어놓으면 정반대 착시가 생긴다 — **지적이 없으면 다 맞는 줄 안다.** 실제로는
 * 점검 규칙이 보는 항목이 보고서의 일부뿐이고, 화면에서 사용자가 가장 열심히 읽는 AI 서술문은
 * 아예 점검 대상이 아니다. 그래서 이 카드의 가장 중요한 일은 지적을 보여주는 게 아니라
 * **점검 범위를 닫는 것**이다.
 *
 * ## 여기서 절대 안 하는 것
 *
 * - "8규칙 중 8개 실행" 같은 표기 — 규칙이 볼 자료가 없어 아무 일도 안 해도 실행으로 세어진다.
 *   대신 규칙별로 **볼 자료가 실제로 있었는지**를 프론트가 확인해 "적용 / 미판정"으로 나눈다.
 * - "검증 완료"·"N% 검증" — 비율을 낼 근거 자체가 백엔드에 없다(커버리지가 늘 비어 있음).
 * - 색만으로 심각도 전달 — 라벨 글자를 항상 함께 쓴다.
 */

"use client";

import { useState } from "react";
import { ShieldCheck, AlertTriangle, ChevronDown, ChevronUp } from "lucide-react";

import { FieldAuditIssue } from "@/components/analysis/FieldAuditNotice";
import type { CredibilityView } from "@/lib/field-audit";

/** 점검 대상이 아닌 것 — 사용자가 가장 오해하기 쉬운 지점이라 이름을 직접 부른다. */
const OUT_OF_SCOPE = "AI가 쓴 해석 문장, 인허가 가능성 판단, 사업 수지 계산";

export function CredibilitySummaryCard({
  view,
  parcelCount,
}: {
  view: CredibilityView;
  /** 선택된 필지 수. 2 이상이면 규칙이 대표필지 기준으로만 돌았음을 알린다. */
  parcelCount?: number;
}) {
  const [openScope, setOpenScope] = useState(false);

  if (view.state === "unavailable") {
    return (
      <div
        role="note"
        className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-4"
      >
        <h4 className="text-sm font-bold text-[var(--text-primary)]">자가검증 정보 없음</h4>
        <p className="mt-1 text-[11px] text-[var(--text-secondary)] leading-relaxed">
          이 보고서에는 플랫폼 자체 점검 결과가 담겨 있지 않습니다. 점검이 꺼져 있었는지,
          이전 버전으로 만들어진 결과인지는 화면에서 구분할 수 없습니다.
          <strong className="text-[var(--text-primary)]"> 지적이 없다는 뜻이 아닙니다.</strong>
        </p>
      </div>
    );
  }

  const applied = view.ruleStatuses.filter((r) => r.applicability === "applied").length;
  const undetermined = view.ruleStatuses.length - applied;
  const issueCount = view.issues.length;
  const multi = (parcelCount ?? 0) > 1;

  return (
    <div
      role="note"
      className={`rounded-2xl border p-4 ${
        view.hasHold || view.noRulesRan
          ? "border-[var(--status-error)]/50 bg-[var(--status-error)]/5"
          : "border-[var(--line)] bg-[var(--surface-strong)]"
      }`}
    >
      <div className="flex items-start gap-2">
        {view.hasHold || view.noRulesRan ? (
          <AlertTriangle className="size-5 shrink-0 text-[var(--status-error)]" aria-hidden />
        ) : (
          <ShieldCheck className="size-5 shrink-0 text-[var(--text-secondary)]" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-bold text-[var(--text-primary)]">
            플랫폼 자체 점검 결과
          </h4>
          {/* ★규칙이 하나도 안 돌았으면 다른 숫자를 말하기 전에 이것부터 말한다.
              이 경우 아래 '적용/미판정'은 의미가 없는데, 그대로 두면 "7개 적용·이상 없음"이라는
              가장 위험한 거짓 안심이 된다(적대검증 실측). 등록이 무성으로 깨졌을 때가 이 상태다. */}
          {view.noRulesRan ? (
            <p className="mt-1 text-[11px] leading-relaxed text-[var(--status-error)]">
              <strong>이 보고서에서는 점검 규칙이 하나도 실행되지 않았습니다.</strong>{" "}
              <span className="text-[var(--text-secondary)]">
                따라서 이상이 없다는 뜻이 아니며, 이 화면은 어떤 숫자도 점검하지 못했습니다.
                플랫폼 담당자 확인이 필요합니다.
              </span>
            </p>
          ) : (
            <p className="mt-1 text-[11px] text-[var(--text-secondary)] leading-relaxed">
              {issueCount > 0 ? (
                <>
                  점검 규칙이 <strong className="text-[var(--text-primary)]">{issueCount}건</strong>의
                  확인이 필요한 항목을 찾았습니다. 아래 각 섹션 안에 함께 표시했습니다.
                </>
              ) : (
                <>점검 규칙이 잡아낸 이상 항목은 없습니다.</>
              )}{" "}
              이 화면이 판별하는 규칙 {view.ruleStatuses.length}개 중{" "}
              <strong className="text-[var(--text-primary)]">{applied}개</strong>는 판단할 자료가
              있어 적용됐고,{" "}
              <strong className="text-[var(--text-primary)]">{undetermined}개</strong>는 볼 자료가
              없어 판정하지 못했습니다.
              {/* ★프론트 규칙 목록은 상수라 백엔드와 어긋날 수 있다. **양방향으로** 밝힌다 —
                  한쪽(늘어난 경우)만 고지하면 규칙이 줄어드는 과대안심 방향이 침묵한다. */}
              {view.rulesRegistered !== null &&
                view.rulesRegistered !== view.ruleStatuses.length && (
                  <>
                    {" "}플랫폼에 등록된 규칙은 {view.rulesRegistered}개로 이 화면이 아는 수와
                    다릅니다 — 표시된 적용/미판정 수를 그대로 믿지 마십시오.
                  </>
                )}
            </p>
          )}
        </div>
      </div>

      {/* ★가장 중요한 한 줄 — 지적 없음을 정확 보증으로 읽지 않게 범위를 닫는다. */}
      <p className="mt-3 rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-2.5 text-[10px] text-[var(--text-secondary)] leading-relaxed">
        이 점검은 정해진 규칙에 어긋나는 값을 찾는 것이고,{" "}
        <strong className="text-[var(--text-primary)]">{OUT_OF_SCOPE}</strong>은 점검 대상이
        아닙니다. 지적이 없다고 해서 모든 숫자가 맞다는 뜻은 아닙니다.
      </p>

      {view.executionShortfall && !view.noRulesRan && (
        <p className="mt-2 text-[10px] text-[var(--status-warning)] leading-relaxed">
          점검 규칙 {view.rulesRegistered}개 중 {view.rulesExecuted}개만 실행됐습니다 — 이 보고서의
          점검 범위가 평소보다 줄었습니다.
        </p>
      )}

      {multi && (
        <p className="mt-2 text-[10px] text-[var(--text-hint)] leading-relaxed">
          여러 필지를 함께 분석했지만, 점검 규칙은 대표 필지 기준으로만 돌았습니다. 필지별
          공시지가·용도지역·경사 차이는 개별로 점검되지 않았습니다.
        </p>
      )}

      {/* ★실제 지적은 **전부 여기서** 보여준다 — 섹션 인라인에만 두면 접힌 섹션 안에 숨는다.
          특히 '사용 보류 권고'(P0)가 접힘 안에 갇히면 사용자는 틀린 값을 그대로 쓴다.
          (섹션 매핑이 없는 지적도 자동으로 여기 포함되므로 조용히 사라지지 않는다.) */}
      {view.issues.length > 0 && (
        <div className="mt-3 space-y-2">
          {view.issues.map((f, i) => (
            <FieldAuditIssue key={`${f.code}:${f.field}:${i}`} finding={f} />
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpenScope((v) => !v)}
        aria-expanded={openScope}
        className="mt-3 inline-flex items-center gap-1 text-[10px] text-[var(--text-hint)] hover:text-[var(--text-secondary)]"
      >
        점검이 어떻게 쓰이는지 {openScope ? <ChevronUp className="size-3" aria-hidden /> : <ChevronDown className="size-3" aria-hidden />}
      </button>
      {openScope && (
        <p className="mt-2 text-[10px] text-[var(--text-hint)] leading-relaxed">
          이 점검은 결과를 관찰해 알려주기만 합니다. 분석을 중단시키거나 값을 자동으로 고치지
          않으며, 여기서 나온 지적이 플랫폼의 자동 학습에 반영되지도 않습니다. 표시된 내용은
          사용자가 직접 확인하는 데 쓰는 참고 정보입니다.
        </p>
      )}
    </div>
  );
}
