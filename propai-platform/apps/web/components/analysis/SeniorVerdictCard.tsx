"use client";

/**
 * SeniorVerdictCard — 시니어 전문가 자문 verdict 공용 표시 카드(DRY·재사용).
 *
 * 백엔드 consultation_hook(attach_senior_consultation[_multi])가 분석 응답에 첨부하는
 * 표준 evidence 계약을 렌더한다. 종합분석·인허가·규제·시장 등 어느 분석 패널이든 동일 카드로
 * verdict(PASS/WARN/BLOCK)·도메인별 정량판정·근거(citation)·정직 고지를 노출한다.
 *
 * 백엔드 표준계약(senior_consultation):
 *   { verdict, evaluations[], citations[], needs_expert_review, honest_notes, consultations[] }
 *   consultations[] 각 항목: { agent_key, name_ko, verdict, evaluations[], citations[],
 *                              confidence_label, needs_expert_review, honest_notes[], license_gate }
 *
 * 정직·무목업: 자문이 없거나(consultations 비었음) verdict='unavailable'이면 렌더하지 않는다
 * (구 응답·미가용에서 빈 카드 노이즈 방지). 보조 자문이므로 본 분석을 가리지 않는다.
 */

import { useId, useState } from "react";

export interface SeniorEvaluation {
  rule_id?: string;
  label?: string;
  value?: number | null;
  unit?: string;
  verdict?: string; // PASS | WARN | BLOCK
  threshold?: string;
  basis?: string;
  detail?: string;
}

export interface SeniorIracStep {
  rule_id?: string;
  issue?: string; // 쟁점(I)
  rule?: string; // 규칙(R)
  basis?: string; // 법령 근거
  application?: string; // 적용(A)
  conclusion?: string; // 결론(C)
}

export interface SeniorReasoning {
  mode?: string; // structured(결정론) | llm
  irac_steps?: SeniorIracStep[];
}

export interface SeniorConsultationDomain {
  agent_key?: string;
  name_ko?: string;
  maturity?: string;
  verdict?: string | null; // PASS | WARN | BLOCK | null
  evaluations?: SeniorEvaluation[];
  citations?: string[];
  confidence_label?: string | null;
  needs_expert_review?: boolean;
  high_risk?: boolean;
  license_gate?: string | null;
  honest_notes?: string[];
  // 풍성화(additive) — 백엔드 include_reasoning 시에만 존재. 없으면 기존 렌더 그대로(무회귀).
  reasoning?: SeniorReasoning | null;
  risk_warnings?: string[];
  checklist?: string[];
}

export interface SeniorConsultation {
  verdict?: string | null; // 종합 PASS | WARN | BLOCK | unavailable | null
  evaluations?: SeniorEvaluation[];
  citations?: string[];
  needs_expert_review?: boolean;
  honest_notes?: string;
  consultations?: SeniorConsultationDomain[];
}

const VERDICT_BADGE: Record<string, { label: string; token: string }> = {
  PASS: { label: "충족", token: "var(--status-success)" },
  WARN: { label: "경고", token: "var(--status-warning)" },
  BLOCK: { label: "차단", token: "var(--status-error)" },
};

function Badge({ token, children }: { token: string; children: React.ReactNode }) {
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{
        color: token,
        background: `color-mix(in srgb, ${token} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${token} 38%, transparent)`,
      }}
    >
      {children}
    </span>
  );
}

function VerdictBadge({ verdict, prefix }: { verdict?: string | null; prefix?: string }) {
  if (!verdict || !VERDICT_BADGE[verdict]) return null;
  const b = VERDICT_BADGE[verdict];
  return (
    <Badge token={b.token}>
      {prefix ? `${prefix} ` : ""}
      {b.label}
    </Badge>
  );
}

export function SeniorVerdictCard({
  consultation,
  title = "시니어 전문가 자문",
  defaultOpen = false,
}: {
  consultation?: SeniorConsultation | null;
  title?: string;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();

  const domains = (consultation?.consultations ?? []).filter((d) => d && d.agent_key);
  // 자문 미가용/없음 → 렌더 생략(정직·노이즈 방지).
  if (!consultation || consultation.verdict === "unavailable" || domains.length === 0) {
    return null;
  }

  const overall = consultation.verdict;
  const hasVerdict = overall && VERDICT_BADGE[overall];

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 p-3 text-left transition-colors hover:bg-[var(--surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)] sm:p-4"
        aria-expanded={open}
        aria-controls={panelId}
      >
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-[13px] font-bold text-[var(--text-primary)]">{title}</span>
          {hasVerdict ? (
            <VerdictBadge verdict={overall} prefix="종합" />
          ) : (
            <span className="text-[10px] text-[var(--text-secondary)]">정성 자문(정량 verdict 입력 없음)</span>
          )}
          {consultation.needs_expert_review ? (
            <Badge token="var(--status-warning)">전문가 검토 권장</Badge>
          ) : null}
        </div>
        <span className="shrink-0 text-[11px] text-[var(--text-secondary)]">{open ? "접기 ▲" : "자세히 ▼"}</span>
      </button>

      {open ? (
        <div id={panelId} className="space-y-3 border-t border-[var(--line)] p-3 sm:p-4">
          {domains.map((d, i) => (
            <div
              key={d.agent_key ?? i}
              className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/40 p-3"
            >
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-semibold text-[var(--text-primary)]">
                  {d.name_ko ?? d.agent_key}
                </span>
                <VerdictBadge verdict={d.verdict} />
                {d.confidence_label ? (
                  <span className="text-[10px] text-[var(--text-secondary)]">{d.confidence_label}</span>
                ) : null}
                {d.high_risk ? <Badge token="var(--status-error)">고위험</Badge> : null}
              </div>

              {/* 정량 판정(evaluations) — 실수치 PASS/WARN/BLOCK */}
              {(d.evaluations ?? []).length > 0 ? (
                <ul className="space-y-1">
                  {(d.evaluations ?? []).map((e, j) => (
                    <li
                      key={e.rule_id ?? j}
                      className="flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--text-secondary)]"
                    >
                      <VerdictBadge verdict={e.verdict} />
                      <span className="font-medium text-[var(--text-primary)]">{e.label}</span>
                      {e.value != null ? (
                        <span>
                          {e.value}
                          {e.unit ?? ""}
                        </span>
                      ) : null}
                      {e.threshold ? <span className="opacity-80">(기준 {e.threshold})</span> : null}
                      {e.detail ? <span className="opacity-70">— {e.detail}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : null}

              {/* 근거(citation) */}
              {(d.citations ?? []).length > 0 ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {(d.citations ?? []).slice(0, 8).map((c, k) => (
                    <span
                      key={c || k}
                      title={c}
                      className="max-w-full truncate rounded border border-[var(--line)] bg-[var(--surface-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              ) : null}

              {/* IRAC 판단 체인(풍성화) — 쟁점→규칙(법령 근거)→적용→결론. 백엔드 결정론 산출. */}
              {Array.isArray(d.reasoning?.irac_steps) && (d.reasoning?.irac_steps ?? []).length > 0 ? (
                <details className="mt-2">
                  <summary className="cursor-pointer text-[11px] font-semibold text-[var(--text-primary)]">
                    판단 체인 {(d.reasoning?.irac_steps ?? []).length}건 (쟁점→규칙→적용→결론)
                  </summary>
                  <ol className="mt-1.5 space-y-2">
                    {(d.reasoning?.irac_steps ?? []).map((s, k) => (
                      <li
                        key={s.rule_id || k}
                        className="break-keep rounded border border-[var(--line)] bg-[var(--surface-soft)] p-2 text-[11px] leading-relaxed text-[var(--text-secondary)]"
                      >
                        {s.issue ? (
                          <p>
                            <span className="font-semibold text-[var(--text-primary)]">쟁점</span> {s.issue}
                          </p>
                        ) : null}
                        {s.rule ? (
                          <p>
                            <span className="font-semibold text-[var(--text-primary)]">규칙</span> {s.rule}
                            {s.basis ? <span className="opacity-80"> (근거: {s.basis})</span> : null}
                          </p>
                        ) : null}
                        {s.application ? (
                          <p>
                            <span className="font-semibold text-[var(--text-primary)]">적용</span> {s.application}
                          </p>
                        ) : null}
                        {s.conclusion ? (
                          <p>
                            <span className="font-semibold text-[var(--text-primary)]">결론</span> {s.conclusion}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </details>
              ) : null}

              {/* 실패모드 경고(풍성화) — 시니어가 경계하는 흔한 오판 */}
              {(d.risk_warnings ?? []).length > 0 ? (
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-[11px] font-semibold text-[var(--text-primary)]">
                    경계 실패모드 {(d.risk_warnings ?? []).length}건
                  </summary>
                  <ul className="mt-1 list-inside list-disc space-y-0.5">
                    {(d.risk_warnings ?? []).map((w, k) => (
                      <li key={w || k} className="break-keep text-[11px] text-[var(--text-secondary)]">
                        {w}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}

              {/* 점검 체크리스트(풍성화) */}
              {(d.checklist ?? []).length > 0 ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {(d.checklist ?? []).map((c, k) => (
                    <span
                      key={c || k}
                      className="rounded border border-[var(--line)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]"
                    >
                      ☑ {c}
                    </span>
                  ))}
                </div>
              ) : null}

              {/* 면허 책임 고지 */}
              {d.license_gate ? (
                <p className="mt-1.5 text-[10px] italic text-[var(--text-secondary)]">{d.license_gate}</p>
              ) : null}
            </div>
          ))}

          {/* 정직 고지(honest_notes) */}
          {consultation.honest_notes ? (
            <p className="text-[10px] text-[var(--text-secondary)]">※ {consultation.honest_notes}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
