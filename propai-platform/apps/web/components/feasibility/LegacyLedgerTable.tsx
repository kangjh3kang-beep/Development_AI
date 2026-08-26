/**
 * 간략 수지 원장 — **실무 양식** 표(3단 계층 · 수량×단가 · 근거 · 검산).
 *
 * ## 왜 별도 표인가
 *
 * 기존 비용분해는 축별 합계 5줄이다(토지·공사·금융·제경비·부담금). 실무 수지표는 그렇게
 * 읽히지 않는다 — **한 행마다 「수량 × 단가 = 금액」과 「왜 이 값인가」**가 나란히 있고,
 * 맨 아래에 **합계가 맞는지 스스로 확인한 결과**가 붙는다.
 *
 * ## ★없는 값을 0 으로 그리지 않는다
 *
 * 백엔드가 `null` 로 주는 것은 **모른다**는 뜻이다. `0` 으로 그리면 화면이 *"영 원"* 이라고
 * **주장**하게 된다. 여기서는 `—` 로 그리고, 근거·비고로 왜 없는지 말한다.
 */
"use client";

import { Fragment, useState } from "react";

/* ── 계약(백엔드 `legacy_ledger`) ─────────────────────────────────────── */
export interface LedgerItem {
  key: string;
  label: string;
  amount_won: number | null;
  qty: number | null;
  qty_unit: string | null;
  /** 「무엇의 수량인가」 — **단위가 아니다**(단위 자리에 넣으면 숫자에 문장이 달라붙는다). */
  qty_label?: string | null;
  unit_price: number | null;
  unit_price_unit: string | null;
  basis: string | null;
  /** `data` = 값이 어디서 왔는가 · `structural` = 이 행이 무엇인가. 둘은 다른 주장이다. */
  basis_kind: "data" | "structural" | null;
  note: string | null;
  added: boolean;
  share_pct: number | null;
}
export interface LedgerGroup {
  key: string; label: string; items: LedgerItem[];
  subtotal_won: number | null; share_pct: number | null;
}
export interface LedgerSection {
  key: string; label: string; groups: LedgerGroup[]; total_won: number | null;
}
export interface LedgerCheck {
  key: string; label: string;
  ledger_won: number | null; engine_won: number | null; diff_won: number | null;
  /** ★`UNKNOWN` 은 `OK` 가 아니다 — 판정 불가를 「괜찮다」로 그리지 않는다. */
  verdict: "OK" | "ERROR" | "UNKNOWN";
  note: string | null;
}
export interface LedgerHeaderItem {
  key: string; label: string; value: string | number | null;
  unit: string | null; is_numeric: boolean;
}
export interface LegacyLedger {
  /** 제원 — 원본 양식 상단 블록. **채울 수 없는 항목은 아예 오지 않는다**(빈 행 금지). */
  header?: LedgerHeaderItem[] | null;
  sections: LedgerSection[];
  checks: LedgerCheck[];
  coverage: {
    items: number; with_qty: number; with_unit_price: number; with_basis: number;
    qty_pct: number | null; unit_price_pct: number | null; basis_pct: number | null;
  };
  share_basis_won: number | null;
  share_basis_label: string;
}

/* ── 표기 — 값 없으면 `—`(무목업 정직표기) ─────────────────────────────── */
const DASH = "—";
/**
 * 금액 표기 — ★**행 단위 표에서는 「억」 하나로 못 쓴다.**
 *
 * 기존 요약 카드 관례(`eok`, 억 단위 소수1)를 그대로 옮겼더니 **실재하는 450만원이 `0억`**
 * 으로 그려졌다(적대 리뷰 중6). 인입·소방 등 수백만~수천만원 행은 이 표의 **정상 모집단**이다.
 * 푸터가 *"없는 값은 0 이 아니라 —"* 라고 선언하는데 정작 있는 값이 0 으로 보이면 그 선언이 거짓이 된다.
 */
const eok = (v: number | null): string => {
  if (v == null || !Number.isFinite(v)) return DASH;
  const a = Math.abs(v);
  if (a >= 1e8) return `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억`;
  if (a >= 1e4) return `${(v / 1e4).toLocaleString(undefined, { maximumFractionDigits: 0 })}만원`;
  return `${Math.round(v).toLocaleString()}원`;  // 0 은 「0원」 — 「모름」(—)과 구별된다
};
const numStr = (v: number | null): string =>
  v == null || !Number.isFinite(v) ? DASH : Math.round(v).toLocaleString();
const pctStr = (v: number | null): string =>
  v == null || !Number.isFinite(v) ? DASH : `${v.toFixed(1)}%`;

/** 수량 × 단가 — 둘 중 하나라도 없으면 **그 자리를 비운다**(반쪽 산식을 만들지 않는다). */
function calcText(it: LedgerItem): string {
  if (it.qty == null || it.unit_price == null) return DASH;
  // ★단위는 숫자에 **붙이고**, 라벨은 괄호로 **떼어 놓는다.** 라이브 실측(2026-08-26)에서
  //   둘을 섞어 `19,027,218,768토지비 + 공사비 × 0.06737` 이 화면에 나갔다.
  const label = it.qty_label ? `(${it.qty_label}) ` : "";
  return `${label}${numStr(it.qty)}${it.qty_unit ?? ""} × ${numStr(it.unit_price)}${
    it.unit_price_unit ? ` ${it.unit_price_unit}` : ""
  }`;
}

const VERDICT_STYLE: Record<LedgerCheck["verdict"], { label: string; cls: string }> = {
  OK: { label: "OK", cls: "bg-[var(--status-success)]/10 text-[var(--status-success)]" },
  ERROR: { label: "ERROR", cls: "bg-[var(--status-danger)]/10 text-[var(--status-danger)]" },
  // ★판정 불가를 초록으로 그리지 않는다 — 강등 시나리오가 「괜찮다」로 보이면 안 된다.
  UNKNOWN: { label: "판정 불가", cls: "bg-[var(--surface-muted)] text-[var(--text-secondary)]" },
};

export default function LegacyLedgerTable({ ledger }: { ledger: LegacyLedger | null | undefined }) {
  const [showBasis, setShowBasis] = useState(false);
  if (!ledger || !ledger.sections?.length) return null;

  const cov = ledger.coverage;
  const hasError = ledger.checks.some((c) => c.verdict === "ERROR");

  return (
    <section
      data-testid="legacy-ledger"
      className="rounded-xl border border-[var(--line)] bg-[var(--surface)] overflow-hidden"
    >
      <header className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-[var(--line)]">
        <h3 className="text-sm font-bold text-[var(--text-primary)]">간략 수지분석(실무 양식)</h3>
        <button
          type="button"
          onClick={() => setShowBasis((v) => !v)}
          aria-expanded={showBasis}
          aria-controls="legacy-ledger-table"
          className="ml-auto text-xs px-2 py-1 rounded-md border border-[var(--line)] text-[var(--text-secondary)]"
        >
          {showBasis ? "근거 숨기기" : "근거 보기"}
        </button>
      </header>

      {/* ── 제원 — 표 위에 「어느 사업의 수지인가」를 먼저 보인다 ── */}
      {ledger.header && ledger.header.length > 0 && (
        <dl
          data-testid="legacy-ledger-header"
          className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1.5 px-4 py-3 border-b border-[var(--line)] text-xs"
        >
          {ledger.header.map((h) => (
            <div key={h.key} className="flex flex-col">
              <dt className="text-[10px] text-[var(--text-tertiary)]">
                {h.label}
                {h.unit ? ` (${h.unit})` : ""}
              </dt>
              <dd className={`text-[var(--text-primary)] ${h.is_numeric ? "tabular-nums" : ""}`}>
                {h.is_numeric && typeof h.value === "number"
                  ? h.value.toLocaleString(undefined, { maximumFractionDigits: 1 })
                  : String(h.value ?? DASH)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <div className="overflow-x-auto">
        <table id="legacy-ledger-table" className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-[var(--surface-soft)] text-[var(--text-secondary)]">
              <th className="text-left px-3 py-2 font-semibold">구 분</th>
              <th className="text-right px-3 py-2 font-semibold">금 액</th>
              <th className="text-right px-3 py-2 font-semibold">구성비</th>
              <th className="text-left px-3 py-2 font-semibold">산출내역(수량 × 단가)</th>
              {showBasis && <th className="text-left px-3 py-2 font-semibold">근 거</th>}
            </tr>
          </thead>
          <tbody>
            {/* ★섹션 합계를 **자기 섹션 뒤**에 둔다. 초안은 그룹 루프와 합계 루프가 분리돼
                합계 3행이 표 **맨 아래에 몰렸고**, 「세전이익」 아래에 「매출 합계」가 오는
                기괴한 순서가 됐다 — 3단 계층이 이 표의 존재 이유인데 화면에서 무너졌다. */}
            {ledger.sections.map((sec) => (
              <Fragment key={`sec-${sec.key}`}>
              {sec.groups.map((g) => (
                // ★키 없는 <> 는 React 가 행을 잘못 재조정한다(경고가 실제로 났다).
                <Fragment key={`${sec.key}-${g.key}`}>
                  {g.items.map((it, idx) => (
                    <tr key={`${sec.key}-${g.key}-${it.key}`} className="border-t border-[var(--line)]">
                      <td className="px-3 py-2">
                        <span className="text-[var(--text-tertiary)]">
                          {idx === 0 ? `${sec.label} · ${g.label}` : ""}
                        </span>
                        <span className="block text-[var(--text-primary)]">
                          {it.label}
                          {it.added && <span className="ml-1 text-[var(--accent-strong)]">(추가)</span>}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">{eok(it.amount_won)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-[var(--text-secondary)]">
                        {pctStr(it.share_pct)}
                      </td>
                      <td className="px-3 py-2 text-[var(--text-secondary)]">{calcText(it)}</td>
                      {showBasis && (
                        <td className="px-3 py-2 text-[var(--text-tertiary)]">
                          {it.basis ?? DASH}
                          {/* ★구조근거는 「이 행이 무엇인가」만 답한다 — 데이터근거와 구별해 표시한다. */}
                          {it.basis_kind === "structural" && (
                            <span className="ml-1 text-[10px] opacity-70">(산식 설명 · 데이터 근거 미확보)</span>
                          )}
                          {it.note && <span className="block opacity-80">{it.note}</span>}
                        </td>
                      )}
                    </tr>
                  ))}
                  <tr key={`${sec.key}-${g.key}-sub`} className="bg-[var(--surface-soft)]/50">
                    <td className="px-3 py-1.5 text-right font-semibold text-[var(--text-secondary)]">
                      {g.label} 소계
                    </td>
                    <td className="px-3 py-1.5 text-right font-bold tabular-nums">{eok(g.subtotal_won)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-[var(--text-secondary)]">
                      {pctStr(g.share_pct)}
                    </td>
                    <td className="px-3 py-1.5" colSpan={showBasis ? 2 : 1} />
                  </tr>
                </Fragment>
              ))}
              <tr key={`${sec.key}-total`} className="border-t-2 border-[var(--line-strong)]">
                <td className="px-3 py-2 text-right font-bold">{sec.label} 합계</td>
                <td className="px-3 py-2 text-right font-bold tabular-nums">{eok(sec.total_won)}</td>
                <td className="px-3 py-2" colSpan={showBasis ? 3 : 2} />
              </tr>
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── 검산 — 원장 합산 ↔ 엔진 산출 ─────────────────────────────── */}
      <div className="px-4 py-3 border-t border-[var(--line)]">
        <p className="text-xs font-semibold text-[var(--text-secondary)] mb-2">
          {/* ★과대주장 금지(적대 리뷰 차단) — 이 검산들은 대부분 **항등식**이라
              「엔진이 맞는가」가 아니라 「원장이 엔진을 옮기다 흘렸는가」만 본다. */}
          합계 전파 점검 — 이 표는 산출 엔진을 <b>참조만</b> 합니다. 아래는{" "}
          <b>원장이 엔진 값을 옮기다 흘렸는지</b>를 봅니다(엔진 값 자체의 정오는 보지 않습니다).
        </p>
        <ul data-testid="legacy-ledger-checks" className="space-y-1">
          {ledger.checks.map((c) => (
            <li key={c.key} className="flex flex-wrap items-center gap-2 text-xs">
              <span
                data-testid={`ledger-check-${c.key}`}
                // ★TS 유니온은 JSON 런타임을 막지 못한다 — 백엔드가 네 번째 verdict 를 내면
                //   `undefined.cls` 로 패널 전체가 죽는다. 모르면 「판정 불가」로 접는다.
                className={`px-1.5 py-0.5 rounded font-bold ${(VERDICT_STYLE[c.verdict] ?? VERDICT_STYLE.UNKNOWN).cls}`}
              >
                {(VERDICT_STYLE[c.verdict] ?? VERDICT_STYLE.UNKNOWN).label}
              </span>
              <span className="text-[var(--text-primary)]">{c.label}</span>
              <span className="text-[var(--text-tertiary)] tabular-nums">
                원장 {eok(c.ledger_won)} · 엔진 {eok(c.engine_won)}
                {c.diff_won != null && c.diff_won !== 0 && ` · 차이 ${numStr(c.diff_won)}원`}
              </span>
              {c.note && <span className="text-[var(--text-tertiary)]">({c.note})</span>}
            </li>
          ))}
        </ul>
        {hasError && (
          <p data-testid="legacy-ledger-drift-warning" className="mt-2 text-xs text-[var(--status-danger)]">
            ★ 원장 합계가 엔진 값과 어긋납니다 — 옮기는 과정에서 흘렸다는 뜻입니다.
            이 표의 숫자를 의사결정에 쓰기 전에 원인을 확인하십시오.
          </p>
        )}
      </div>

      {/* ── 커버리지 — 우리가 지금 어디까지 답할 수 있는지 스스로 신고 ──────── */}
      <footer className="px-4 py-2 border-t border-[var(--line)] text-[11px] text-[var(--text-tertiary)]">
        <span data-testid="legacy-ledger-coverage">
          항목 {cov.items}개 중 수량 {cov.with_qty}({pctStr(cov.qty_pct)}) · 단가{" "}
          {cov.with_unit_price}({pctStr(cov.unit_price_pct)}) · 근거 {cov.with_basis}(
          {pctStr(cov.basis_pct)})
        </span>
        <span className="block mt-0.5">구성비 기준: {ledger.share_basis_label}</span>
        <span className="block mt-0.5">
          ★ 산출 근거가 없는 항목은 <b>0 원이 아니라 {DASH}</b> 로 표기됩니다(값을 지어내지 않음).
        </span>
      </footer>
    </section>
  );
}
