"use client";

/**
 * SpecialParcelLegalPrelim — 특이토지 법규 '예비판정' 섹션(순수 presentational).
 *
 * 백엔드 special_parcel.factors[](apps/api/app/services/zoning/special_parcel.py — dict
 * passthrough)의 신규 산출을 additive로 노출한다:
 *   - forest_facts: DEM 평균경사도(평균경사도_pct·경사도_source·경사도_정확도한계)·입목축적
 *   - preliminary_assessment.slope: DEM값 vs 기준(조례 우선→별표4 25°) 3단 라벨 예비판정
 *   - preliminary_assessment.stocking: 입목축적 비율 vs 관할평균 150%(별표4) 예비판정
 *   - charge_notice: 농지보전부담금/대체산림자원조성비 산식·추정액·법령 링크
 *
 * ★정직성(면책 UX) — 이 섹션의 존재 이유:
 *   - 상단에 정직 배지를 항상 표시: 예비판정 존재 시 '확정 아님 · 공식조사 필요',
 *     부담금 고지만 있으면 '부담금 안내 · 확정 부과액 아님'(공식조사 불필요 요인 오도 방지).
 *   - DEM/API 조회값의 근사치 한계(경사도_정확도한계·limitations)를 값 옆에 동반.
 *   - 값 미확보 항목은 skip 사유를 그대로 표기(무날조 — 비율·판정 날조 금지).
 *   - developability(NEEDS_OFFICIAL_SURVEY 등)는 예비판정으로 변하지 않음을 disclaimer로 고지.
 *   - 법령 링크는 verified(law.go.kr 딥링크)만 클릭 가능(LegalRefChip이 무링크 텍스트 폴백).
 *
 * 데이터가 전혀 없으면 null 렌더(무목업 — 일상 특이부지 카드 표시 불변).
 * 네트워크 호출·store 접근 없음. 디자인 토큰(CSS 변수)만 사용.
 */

import { LegalRefChip } from "@/components/common/LegalRefChip";
import type { BackendLegalRef } from "@/lib/evidence/adaptEvidence";

// ── 백엔드 계약 타입(전부 옵셔널 — 부분응답/구버전 응답 방어) ──

export type ForestFacts = {
  평균경사도_pct?: number | null;
  경사도_source?: string | null;
  경사도_정확도한계?: string | null;
  입목축적_per_ha?: number | null;
  관할평균_입목축적_per_ha?: number | null;
  산지구분?: string | null;
  official_data_source?: string | null;
  [key: string]: unknown;
};

export type SlopePreliminary = {
  judgment?: string | null;
  value_pct?: number | null;
  value_deg?: number | null;
  criteria_deg?: number | null;
  criteria_pct?: number | null;
  criteria_source?: string | null;
  formula?: string | null;
  source?: string | null;
  caveats?: string[] | null;
  limitations?: string[] | null;
};

export type StockingPreliminary = {
  judgment?: string | null;
  입목축적_비율_pct?: number | null;
  criteria?: string | null;
  formula?: string | null;
  source?: string | null;
  limitations?: string[] | null;
};

export type PreliminaryAssessment = {
  slope?: SlopePreliminary | null;
  stocking?: StockingPreliminary | null;
  slope_skip_reason?: string | null;
  stocking_skip_reason?: string | null;
  disclaimer?: string | null;
};

export type ChargeNotice = {
  charge_name?: string | null;
  notice?: string | null;
  formula?: string | null;
  legal_ref_keys?: string[] | null;
  estimate?: number | null;
  estimate_note?: string | null;
};

/** special_parcel.factors[] 원소(객체형) — 이 컴포넌트가 소비하는 부분집합. */
export type SpecialParcelFactorLike = {
  category?: string | null;
  developability?: string | null;
  forest_facts?: ForestFacts | null;
  preliminary_assessment?: PreliminaryAssessment | null;
  charge_notice?: ChargeNotice | null;
  legal_refs?: BackendLegalRef[] | null;
  [key: string]: unknown;
};

/** factors에 이 섹션이 표시할 데이터(예비판정/부담금)가 하나라도 있는지. */
export function hasLegalPrelimData(
  factors?: Array<SpecialParcelFactorLike | string> | null,
): boolean {
  for (const f of factors ?? []) {
    if (!f || typeof f === "string") continue;
    if (f.preliminary_assessment || f.charge_notice) return true;
  }
  return false;
}

// ── 판정 라벨 → 시각 톤(백엔드 3단 라벨의 부분문자열 판정 — 라벨 원문은 그대로 표시) ──
type Tone = "success" | "warning" | "error";

function judgmentTone(judgment: string): Tone {
  if (judgment.includes("초과")) return "error";
  if (judgment.includes("경계")) return "warning";
  return "success"; // "예비 적합 가능성"
}

const TONE_CLASS: Record<Tone, string> = {
  success:
    "text-[var(--status-success)] bg-[color-mix(in_srgb,var(--status-success)_12%,transparent)] border-[color-mix(in_srgb,var(--status-success)_36%,transparent)]",
  warning:
    "text-[var(--status-warning)] bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] border-[color-mix(in_srgb,var(--status-warning)_36%,transparent)]",
  error:
    "text-[var(--status-error)] bg-[color-mix(in_srgb,var(--status-error)_12%,transparent)] border-[color-mix(in_srgb,var(--status-error)_36%,transparent)]",
};

function JudgmentBadge({ judgment }: { judgment: string }) {
  const tone = judgmentTone(judgment);
  return (
    <span
      data-tone={tone}
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[9px] font-black ${TONE_CLASS[tone]}`}
    >
      {judgment}
    </span>
  );
}

/** charge_notice.legal_ref_keys를 factor.legal_refs(verified 레지스트리 출력)에 조인. */
function chargeRefs(
  keys?: string[] | null,
  legalRefs?: BackendLegalRef[] | null,
): BackendLegalRef[] {
  const want = new Set((keys ?? []).filter(Boolean));
  if (want.size === 0) return [];
  return (legalRefs ?? []).filter(
    (r) =>
      !!r &&
      !!r.key &&
      want.has(r.key) &&
      (r.url_status || "").trim() === "verified" &&
      !!(r.url || "").trim(),
  );
}

function num(v: number | null | undefined): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  // 백엔드가 이미 반올림해서 준다(round 1~2자리) — 소수점 불필요 0은 제거해 그대로 표시.
  return String(v);
}

// ── 하위 블록 ──

function SlopeBlock({
  slope,
  accuracyCaveat,
}: {
  slope: SlopePreliminary;
  accuracyCaveat?: string | null;
}) {
  const valuePct = num(slope.value_pct);
  const valueDeg = num(slope.value_deg);
  const critDeg = num(slope.criteria_deg);
  const critPct = num(slope.criteria_pct);
  // 근사치 캐비앗: forest_facts.경사도_정확도한계 우선, 없으면 limitations 첫 항목(정직 표기 유지).
  const caveat = accuracyCaveat ?? slope.limitations?.[0] ?? null;
  return (
    <div data-testid="prelim-slope" className="space-y-0.5">
      <p className="flex flex-wrap items-center gap-1.5">
        <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
          경사도(산지전용)
        </span>
        {slope.judgment && <JudgmentBadge judgment={slope.judgment} />}
      </p>
      {(valuePct || valueDeg || critDeg || critPct) && (
        <p data-testid="prelim-slope-values" className="text-[10px] font-bold text-[var(--text-primary)]">
          DEM 측정 {valuePct != null ? `${valuePct}%` : "—"}
          {valueDeg != null ? `(≈${valueDeg}°)` : ""}
          <span className="mx-1 font-medium text-[var(--text-hint)]">vs 기준</span>
          {critDeg != null ? `${critDeg}°` : "—"}
          {critPct != null ? `(${critPct}%)` : ""}
          {slope.source && (
            <span className="ml-1 font-medium text-[var(--text-hint)]">· 출처 {slope.source}</span>
          )}
        </p>
      )}
      {slope.criteria_source && (
        <p className="text-[9px] leading-relaxed text-[var(--text-secondary)]">{slope.criteria_source}</p>
      )}
      {caveat && (
        <p className="text-[9px] leading-relaxed text-[var(--status-warning)]">※ {caveat}</p>
      )}
      {(slope.caveats ?? []).map((c, i) => (
        <p key={i} className="text-[9px] leading-relaxed text-[var(--text-hint)]">
          ※ {c}
        </p>
      ))}
    </div>
  );
}

function StockingBlock({ stocking }: { stocking: StockingPreliminary }) {
  const ratio = num(stocking.입목축적_비율_pct);
  return (
    <div data-testid="prelim-stocking" className="space-y-0.5">
      <p className="flex flex-wrap items-center gap-1.5">
        <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
          입목축적(별표4)
        </span>
        {stocking.judgment && <JudgmentBadge judgment={stocking.judgment} />}
      </p>
      <p data-testid="prelim-stocking-values" className="text-[10px] font-bold text-[var(--text-primary)]">
        {ratio != null ? `관할평균 대비 ${ratio}%` : "비율 미산출"}
        {stocking.criteria && (
          <span className="ml-1 font-medium text-[var(--text-hint)]">— 기준: {stocking.criteria}</span>
        )}
      </p>
      {stocking.formula && (
        <p className="text-[9px] leading-relaxed text-[var(--text-secondary)]">{stocking.formula}</p>
      )}
      {(stocking.limitations ?? []).slice(0, 1).map((l, i) => (
        <p key={i} className="text-[9px] leading-relaxed text-[var(--status-warning)]">
          ※ {l}
        </p>
      ))}
    </div>
  );
}

function ChargeBlock({
  charge,
  legalRefs,
}: {
  charge: ChargeNotice;
  legalRefs?: BackendLegalRef[] | null;
}) {
  const refs = chargeRefs(charge.legal_ref_keys, legalRefs);
  const estimate =
    typeof charge.estimate === "number" && Number.isFinite(charge.estimate)
      ? charge.estimate
      : null;
  return (
    <div data-testid="charge-notice" className="space-y-0.5">
      <p className="flex flex-wrap items-center gap-1.5">
        <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-hint)]">
          부담금 고지{charge.charge_name ? ` · ${charge.charge_name}` : ""}
        </span>
      </p>
      {charge.notice && (
        <p className="text-[10px] leading-relaxed font-medium text-[var(--text-secondary)]">{charge.notice}</p>
      )}
      {charge.formula && (
        <p className="text-[9px] leading-relaxed text-[var(--text-primary)] font-semibold">
          산식: {charge.formula}
        </p>
      )}
      {estimate != null && (
        <p className="text-[10px] font-bold text-[var(--text-primary)]">
          추정액 약 {estimate.toLocaleString("ko-KR")}원
        </p>
      )}
      {charge.estimate_note && (
        <p className="text-[9px] leading-relaxed text-[var(--status-warning)]">※ {charge.estimate_note}</p>
      )}
      {refs.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 pt-0.5">
          {refs.map((r, i) => (
            <LegalRefChip
              key={`${r.key || r.law_name || "charge-ref"}-${i}`}
              lawName={r.law_name || ""}
              article={r.article}
              title={r.title}
              url={r.url}
            />
          ))}
        </p>
      )}
    </div>
  );
}

// ── 본체 ──

export function SpecialParcelLegalPrelim({
  factors,
  className = "",
}: {
  /** special_parcel.factors[] 원본(객체형 원소만 소비 — 문자열 원소는 무시). */
  factors?: Array<SpecialParcelFactorLike | string> | null;
  className?: string;
}) {
  const objs = (factors ?? []).filter(
    (f): f is SpecialParcelFactorLike => !!f && typeof f !== "string",
  );
  const withPrelim = objs.filter((f) => !!f.preliminary_assessment);
  const withCharge = objs.filter((f) => !!f.charge_notice);
  if (withPrelim.length === 0 && withCharge.length === 0) return null; // 데이터 부재 → 미표시(무목업)

  // 부담금 고지만 있는 경우(예비판정 없음) — '공식조사 필요'는 오도(농지 등 공식 산림조사
  // 대상이 아닌 요인 포함)이므로 배지·기본 disclaimer를 부담금 참고용 고지로 대체한다.
  const chargeOnly = withPrelim.length === 0;

  // disclaimer는 백엔드 원문 우선(전 요인 공통이므로 첫 번째만) — 없으면 보수적 기본 문구.
  const disclaimer =
    withPrelim.map((f) => f.preliminary_assessment?.disclaimer).find((d) => !!d) ??
    (chargeOnly
      ? "부담금 안내(참고용) — 추정치는 확정 부과액이 아니며, 감면·연도별 고시 단가 등에 따라 실제 부과액과 다를 수 있습니다."
      : "예비판정(참고용) — 확정 아님. 확정 판정은 공식조사(평균경사도조사서·산림조사서 등) 확보 후에만 가능합니다.");

  return (
    <div
      data-testid="special-parcel-legal-prelim"
      className={`mt-3 rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-3 space-y-2.5 ${className}`}
    >
      <p className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-primary)]">
          법규 예비판정
        </span>
        {/* ★면책 UX — 항상 표시되는 정직 라벨. 예비판정 존재 시 '공식조사 필요',
            부담금 고지만 있으면 '부담금 안내'(공식조사 대상이 아닌 요인 오도 방지) */}
        <span
          data-testid="prelim-honest-badge"
          className="inline-flex items-center rounded-full border border-[color-mix(in_srgb,var(--status-warning)_45%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_14%,transparent)] px-2 py-0.5 text-[9px] font-black text-[var(--status-warning)]"
        >
          {chargeOnly ? "부담금 안내 · 확정 부과액 아님" : "확정 아님 · 공식조사 필요"}
        </span>
      </p>

      {withPrelim.map((f, i) => {
        const pa = f.preliminary_assessment!;
        return (
          <div key={`pa-${f.category || i}`} className="space-y-2">
            {pa.slope && (
              <SlopeBlock slope={pa.slope} accuracyCaveat={f.forest_facts?.경사도_정확도한계} />
            )}
            {!pa.slope && pa.slope_skip_reason && (
              <p className="text-[9px] leading-relaxed text-[var(--text-hint)]">{pa.slope_skip_reason}</p>
            )}
            {pa.stocking && <StockingBlock stocking={pa.stocking} />}
            {!pa.stocking && pa.stocking_skip_reason && (
              <p className="text-[9px] leading-relaxed text-[var(--text-hint)]">{pa.stocking_skip_reason}</p>
            )}
          </div>
        );
      })}

      {withCharge.map((f, i) => (
        <ChargeBlock
          key={`charge-${f.category || i}`}
          charge={f.charge_notice!}
          legalRefs={f.legal_refs}
        />
      ))}

      <p className="border-t border-[var(--line)] pt-1.5 text-[9px] leading-relaxed text-[var(--text-hint)]">
        {disclaimer}
      </p>
    </div>
  );
}
