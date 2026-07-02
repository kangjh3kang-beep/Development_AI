"use client";

/**
 * 다필지 필지×판정 매트릭스 + 실사용가능용지 3계층 + 검증·시니어·혼재(§84)·제외 시나리오 — S6(additive).
 *
 * 백엔드 계약(MULTI_PARCEL_ATTRIBUTES_PLAN_2026-07-03 S3~S5 — D 웨이브(special_parcel 합류) 병렬
 * 진행 중이라 응답 내 위치가 유동적일 수 있어, resolver 가 다위치(top-level·multi_parcel_report·
 * aggregate 중첩)를 호환 수집한다. 형상은 W1 커밋된 순수모듈 산출 기준:
 *   usable_area        = compute_usable_area (apps/api app/services/zoning/usable_area.py)
 *   area_verification  = verify_parcel_areas (app/services/land_intelligence/parcel_verification.py)
 *   senior_review[]    = RuleEvaluation.to_dict (senior_agents/evaluators/land_assembly.py)
 *   zone_straddle_ruling = S3-A 국계법 §84 걸침 판정 {applied_rule, threshold_sqm?, honest_note}
 *   exclusion_scenario = simulate_exclusion {lost_area_sqm, excluded_parcels, after{…}, note}
 *
 * ★무날조 원칙: 모든 필드 optional — 데이터 부재 시 해당 섹션 '완전 미표시'(추정 렌더 금지),
 *   수치 미확보는 '미상'으로 정직 표기(0·가짜값 금지). 조건부·잠정 산출에는 '확정 아님' 라벨 동반.
 *   §84 조문 라벨은 zone_straddle_ruling 데이터가 실재할 때만 노출(정적 단정 금지).
 */

import { AlertTriangle, CheckCircle2, Grid3X3, Ruler, Scale, Scissors, ShieldCheck, SlidersHorizontal } from "lucide-react";

// ── 계약 타입(전 필드 optional — D 병렬 진행 중 호환 가드) ──────────────────────

type Rec = Record<string, unknown>;

export type UsableAreaLike = {
  gross_sqm?: number | null;
  usable_confirmed_sqm?: number | null;
  usable_conditional_sqm?: number | null;
  excluded_sqm?: number | null;
  share?: { confirmed_pct?: number | null; conditional_pct?: number | null; excluded_pct?: number | null } | null;
  excluded_parcels?: { pnu?: string | null; land_category?: string | null; area_sqm?: number | null; reasons?: { code?: string; detail?: string }[] }[] | null;
  area_unknown_parcels?: unknown[] | null;
  honest_notes?: string[] | null;
  warnings?: string[] | null;
} & Rec;

export type AreaVerificationLike = {
  all_consistent?: boolean | null;
  discrepancy_count?: number | null;
  insufficient_count?: number | null;
  per_parcel?: ({ pnu?: string | null; status?: string | null; recommendation?: string | null } & Rec)[] | null;
} & Rec;

export type SeniorRuleLike = {
  rule_id?: string | null; label?: string | null;
  value?: number | null; unit?: string | null;
  verdict?: string | null; threshold?: string | null;
  basis?: string | null; detail?: string | null;
} & Rec;

export type ZoneStraddleRulingLike = {
  applied_rule?: string | null;
  threshold_sqm?: number | null;
  honest_note?: string | null;
} & Rec;

export type ExclusionScenarioLike = {
  applied_exclude_pnus?: string[] | null;
  excluded_parcels?: ({ pnu?: string | null; land_category?: string | null; area_sqm?: number | null } & Rec)[] | null;
  lost_area_sqm?: number | null;
  after?: ({ gross_sqm?: number | null; usable_confirmed_sqm?: number | null; usable_conditional_sqm?: number | null; excluded_sqm?: number | null } & Rec) | null;
  note?: string | null;
} & Rec;

export type MatrixParcelLike = {
  pnu?: string | null; address?: string | null;
  area_sqm?: number | null; zone_type?: string | null; land_category?: string | null;
  developability?: string | null;
  special_parcel?: { developability?: string | null; label?: string | null } | null;
} & Rec;

export type MultiParcelReportLike = {
  usable_area?: UsableAreaLike | null;
  area_verification?: AreaVerificationLike | null;
  senior_review?: SeniorRuleLike[] | null;
  zone_straddle_ruling?: ZoneStraddleRulingLike | null;
  exclusion_scenario?: ExclusionScenarioLike | null;
  matrix?: MatrixParcelLike[] | null;
} & Rec;

// ── resolver: 응답 다위치 호환 수집(top-level 우선 → multi_parcel_report → aggregate 중첩) ──

const REPORT_KEYS = [
  "usable_area", "area_verification", "senior_review", "zone_straddle_ruling", "exclusion_scenario", "matrix",
] as const;

const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);

/** 응답(통합분석·배치)에서 다필지 보고 계약 필드를 호환 수집. 아무것도 없으면 null(추정 생성 금지). */
export function resolveMultiParcelReport(resp: unknown): MultiParcelReportLike | null {
  if (!isRec(resp)) return null;
  const nested = [
    resp,
    isRec(resp.multi_parcel_report) ? resp.multi_parcel_report : null,
    isRec(resp.aggregate) && isRec((resp.aggregate as Rec).multi_parcel_report)
      ? ((resp.aggregate as Rec).multi_parcel_report as Rec) : null,
  ].filter((x): x is Rec => x != null);

  const out: MultiParcelReportLike = {};
  for (const key of REPORT_KEYS) {
    for (const src of nested) {
      const v = src[key];
      if (v != null && out[key] == null) out[key] = v as never;
    }
  }
  return hasMultiParcelAttributeData(out) ? out : null;
}

/** 표시할 계약 데이터가 1개 이상 실재하는가(빈 배열·빈 객체는 부재로 간주). */
export function hasMultiParcelAttributeData(report: unknown): boolean {
  if (!isRec(report)) return false;
  return REPORT_KEYS.some((k) => {
    const v = report[k];
    if (v == null) return false;
    if (Array.isArray(v)) return v.length > 0;
    if (isRec(v)) return Object.keys(v).length > 0;
    return false;
  });
}

// ── 표시 헬퍼(무날조: null → 미표시/'미상', 숫자 포맷은 실값에만) ──────────────

const fmt = (v: number | null | undefined): string | null =>
  v == null || !Number.isFinite(v) ? null : Math.round(v).toLocaleString("ko-KR");

const sqm = (v: number | null | undefined): string => {
  const f = fmt(v);
  return f == null ? "미상" : `${f}㎡`;
};

type Tone = "ok" | "warn" | "bad" | "muted";
const toneCls: Record<Tone, string> = {
  ok: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  bad: "border-rose-500/30 bg-rose-500/10 text-rose-400",
  muted: "border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
};

// 게이트 전 어휘(special_parcel.py _RANK SSOT와 동일 문자열) → 한국어 배지.
function gateBadge(dev?: string | null): { text: string; tone: Tone } {
  switch ((dev || "").trim().toUpperCase()) {
    case "POSSIBLE": return { text: "가능", tone: "ok" };
    case "CAUTION": return { text: "주의(사전확인)", tone: "warn" };
    case "CONDITIONAL": return { text: "조건부(확정 아님)", tone: "warn" };
    case "PRECONDITION": return { text: "조건부·선행절차(확정 아님)", tone: "warn" };
    case "NEEDS_OFFICIAL_SURVEY": return { text: "공식조사 필요(확정 아님)", tone: "warn" };
    case "BLOCKED": return { text: "차단", tone: "bad" };
    case "": return { text: "가능", tone: "ok" }; // special=None=일상 필지(기존 계약)
    default: return { text: dev as string, tone: "muted" }; // 미지 어휘 — 원문 정직 표기
  }
}

// 시니어 verdict → 한국어 배지(PASS/WARN/BLOCK — RuleEvaluation SSOT).
function verdictBadge(v?: string | null): { text: string; tone: Tone } {
  switch ((v || "").trim().toUpperCase()) {
    case "PASS": return { text: "통과", tone: "ok" };
    case "WARN": return { text: "경고", tone: "warn" };
    case "BLOCK": return { text: "차단", tone: "bad" };
    default: return { text: v || "미상", tone: "muted" };
  }
}

function SectionTitle({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <p className="mb-2 inline-flex items-center gap-1.5 text-[11px] font-black uppercase tracking-wide text-[var(--text-secondary)]">
      {icon} {children}
    </p>
  );
}

// ── 본체 ────────────────────────────────────────────────────────────────────

export function MultiParcelAttributeMatrix({
  report,
  perParcel,
  className = "",
}: {
  report: MultiParcelReportLike;
  /** 매트릭스 행 폴백 — /zoning/integrated-analysis per_parcel(report.matrix 부재 시 사용). */
  perParcel?: MatrixParcelLike[] | null;
  className?: string;
}) {
  const usable = isRec(report.usable_area) ? (report.usable_area as UsableAreaLike) : null;
  const verif = isRec(report.area_verification) ? (report.area_verification as AreaVerificationLike) : null;
  const senior = Array.isArray(report.senior_review) ? (report.senior_review as SeniorRuleLike[]) : [];
  const straddle = isRec(report.zone_straddle_ruling) ? (report.zone_straddle_ruling as ZoneStraddleRulingLike) : null;
  const exclusion = isRec(report.exclusion_scenario) ? (report.exclusion_scenario as ExclusionScenarioLike) : null;

  // 매트릭스 행: report.matrix(D 계약) 우선 → perParcel 폴백. 없으면 미표시.
  const matrixRows: MatrixParcelLike[] =
    (Array.isArray(report.matrix) && report.matrix.length > 0 ? (report.matrix as MatrixParcelLike[]) : null)
    ?? (Array.isArray(perParcel) && perParcel.length > 0 ? perParcel : []);

  // usable 게이지: gross 실재(양수)일 때만(수치 추정 금지).
  const gross = typeof usable?.gross_sqm === "number" && Number.isFinite(usable.gross_sqm) && usable.gross_sqm > 0
    ? usable.gross_sqm : null;
  const showUsable = usable != null && gross != null;

  const showVerif = verif != null && (
    verif.all_consistent != null || verif.discrepancy_count != null || (verif.per_parcel?.length ?? 0) > 0
  );
  const showSenior = senior.length > 0;
  const showStraddle = straddle != null && (straddle.applied_rule != null || straddle.honest_note != null);
  const showExclusion = exclusion != null && (
    exclusion.lost_area_sqm != null || (exclusion.excluded_parcels?.length ?? 0) > 0 || exclusion.after != null
  );
  const showMatrix = matrixRows.length > 0;

  if (!showMatrix && !showUsable && !showVerif && !showSenior && !showStraddle && !showExclusion) {
    return null; // 데이터 전무 — 완전 미표시(추정 렌더 금지)
  }

  const pctW = (v: number | null | undefined): string =>
    gross != null && v != null && Number.isFinite(v) ? `${Math.max(0, Math.min(100, (v / gross) * 100))}%` : "0%";

  const discrepancy = verif?.discrepancy_count ?? 0;
  const insufficient = verif?.insufficient_count ?? 0;
  const consistentAll = verif?.all_consistent === true;
  const discrepantParcels = (verif?.per_parcel ?? []).filter((p) => p?.status === "discrepancy");

  return (
    <div className={`flex flex-col gap-3 ${className}`} data-testid="mpx-root">
      {/* 1) 필지×판정 매트릭스 — 게이트 배지·면적·지목 */}
      {showMatrix && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3" data-testid="mpx-matrix">
          <SectionTitle icon={<Grid3X3 className="size-3.5" aria-hidden />}>필지×판정 매트릭스 ({matrixRows.length})</SectionTitle>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] border-collapse text-[11px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-[var(--text-hint)]">
                  <th className="px-2 py-1 font-bold">필지</th>
                  <th className="px-2 py-1 font-bold">면적</th>
                  <th className="px-2 py-1 font-bold">지목</th>
                  <th className="px-2 py-1 font-bold">용도지역</th>
                  <th className="px-2 py-1 font-bold">게이트 판정</th>
                </tr>
              </thead>
              <tbody>
                {matrixRows.map((p, i) => {
                  const dev = p.developability ?? p.special_parcel?.developability ?? null;
                  // 조회 실패 필지는 기본값 '가능'으로 과대표시하지 않는다(정직 — 판정 불가 표기).
                  const failed = typeof p.status === "string" && p.status !== "ok" && dev == null;
                  const g = failed ? { text: "판정 불가(조회 실패)", tone: "muted" as Tone } : gateBadge(dev);
                  return (
                    <tr key={(p.pnu || p.address || "") + i} className="border-t border-[var(--line)]">
                      <td className="max-w-[180px] truncate px-2 py-1.5 font-bold text-[var(--text-primary)]" title={p.address || p.pnu || undefined}>
                        {p.address || p.pnu || `필지 ${i + 1}`}
                      </td>
                      <td className="px-2 py-1.5 text-[var(--text-secondary)]" data-testid={`mpx-area-${i}`}>{sqm(p.area_sqm)}</td>
                      <td className="px-2 py-1.5 text-[var(--text-secondary)]">{p.land_category || "미상"}</td>
                      <td className="max-w-[140px] truncate px-2 py-1.5 text-[var(--text-secondary)]" title={p.zone_type || undefined}>{p.zone_type || "미상"}</td>
                      <td className="px-2 py-1.5">
                        <span className={`inline-block rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${toneCls[g.tone]}`} data-testid={`mpx-gate-${i}`}>
                          {g.text}{p.special_parcel?.label ? ` · ${p.special_parcel.label}` : ""}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 2) 실사용가능용지 3계층 게이지 — 확정+조건부+제외 = 총면적(면적 보존) */}
      {showUsable && usable && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3" data-testid="mpx-usable">
          <SectionTitle icon={<Ruler className="size-3.5" aria-hidden />}>실사용가능용지 3계층</SectionTitle>
          <p className="text-[11px] text-[var(--text-secondary)]">
            총면적 <b className="text-[var(--text-primary)]">{sqm(gross)}</b> 기준(확정+조건부+제외 = 총면적)
          </p>
          <div className="mt-2 flex h-3 w-full overflow-hidden rounded-full bg-[var(--surface-strong)]" aria-hidden>
            <div style={{ width: pctW(usable.usable_confirmed_sqm) }} className="bg-emerald-500" />
            <div style={{ width: pctW(usable.usable_conditional_sqm) }} className="bg-amber-500" />
            <div style={{ width: pctW(usable.excluded_sqm) }} className="bg-rose-500" />
          </div>
          <ul className="mt-2 space-y-1 text-[11px]">
            <li className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]"><span className="size-2 rounded-full bg-emerald-500" aria-hidden /> 확정 사용가능</span>
              <b className="text-[var(--text-primary)]">{sqm(usable.usable_confirmed_sqm)}{usable.share?.confirmed_pct != null ? ` · ${usable.share.confirmed_pct}%` : ""}</b>
            </li>
            <li className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]"><span className="size-2 rounded-full bg-amber-500" aria-hidden /> 조건부(확정 아님 — 선행절차 전제)</span>
              <b className="text-[var(--text-primary)]">{sqm(usable.usable_conditional_sqm)}{usable.share?.conditional_pct != null ? ` · ${usable.share.conditional_pct}%` : ""}</b>
            </li>
            <li className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]"><span className="size-2 rounded-full bg-rose-500" aria-hidden /> 제외(차단·건축불가 지목)</span>
              <b className="text-[var(--text-primary)]">{sqm(usable.excluded_sqm)}{usable.share?.excluded_pct != null ? ` · ${usable.share.excluded_pct}%` : ""}</b>
            </li>
          </ul>
          {(usable.excluded_parcels?.length ?? 0) > 0 && (
            <div className="mt-2 rounded-lg border border-rose-500/20 bg-rose-500/5 p-2">
              <p className="text-[10px] font-bold text-rose-400">제외 필지 사유 명세</p>
              <ul className="mt-1 space-y-0.5 text-[10px] leading-relaxed text-[var(--text-secondary)]">
                {usable.excluded_parcels!.map((ep, i) => (
                  <li key={(ep.pnu || "") + i}>
                    · {ep.pnu || `필지`}{ep.land_category ? `(${ep.land_category})` : ""} {ep.area_sqm != null ? sqm(ep.area_sqm) : ""}
                    {(ep.reasons ?? []).map((r, j) => <span key={j}> — {r.detail || r.code}</span>)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(usable.area_unknown_parcels?.length ?? 0) > 0 && (
            <p className="mt-2 inline-flex items-start gap-1 text-[10px] text-amber-500">
              <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
              면적 미확보 {usable.area_unknown_parcels!.length}필지 — 합산 제외(0 가정 안 함), 공부 면적 확보 후 재정산 필요.
            </p>
          )}
          {(usable.honest_notes?.length ?? 0) > 0 && (
            <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[10px] leading-relaxed text-[var(--text-hint)]">
              {usable.honest_notes!.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </section>
      )}

      {/* 3) 면적 3원 검증 상태 — 미수렴은 측량 권고(자동 보정 금지) */}
      {showVerif && verif && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3" data-testid="mpx-verification">
          <SectionTitle icon={<ShieldCheck className="size-3.5" aria-hidden />}>면적 교차검증(공부·좌표·입력)</SectionTitle>
          <div className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 text-[11px] ${consistentAll ? toneCls.ok : (discrepancy > 0 ? toneCls.warn : toneCls.muted)}`}>
            {consistentAll ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" aria-hidden /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
            <span>
              {consistentAll
                ? <b>전 필지 면적 신호 정합 — 공부 면적 기준 사용 가능</b>
                : discrepancy > 0
                  ? <b>미수렴 {discrepancy}필지 — 지적측량(경계·면적 확정측량) 확인 권고</b>
                  : <b>검증 신호 부족{insufficient > 0 ? ` ${insufficient}필지` : ""} — 정합 여부 미확정</b>}
            </span>
          </div>
          {discrepantParcels.length > 0 && (
            <ul className="mt-2 space-y-1 text-[10px] leading-relaxed text-[var(--text-secondary)]">
              {discrepantParcels.map((p, i) => (
                <li key={(p.pnu || "") + i}>· {p.pnu || `필지`} — {p.recommendation || "괴리 검출(권고 미상)"}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* 4) 시니어 종합 리뷰 카드 — RuleEvaluation(verdict 색·근거·산식) */}
      {showSenior && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3" data-testid="mpx-senior">
          <SectionTitle icon={<SlidersHorizontal className="size-3.5" aria-hidden />}>시니어 종합 리뷰</SectionTitle>
          <ul className="space-y-1.5">
            {senior.map((r, i) => {
              const vb = verdictBadge(r.verdict);
              return (
                <li key={(r.rule_id || "") + i} className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-bold text-[var(--text-primary)]">{r.label || r.rule_id || "평가"}</span>
                    <span className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${toneCls[vb.tone]}`}
                      data-testid={`mpx-senior-verdict-${r.rule_id ?? i}`}>
                      {vb.text}
                    </span>
                  </div>
                  {r.detail && <p className="mt-1 text-[10px] leading-relaxed text-[var(--text-secondary)]">{r.detail}</p>}
                  {r.basis && <p className="mt-0.5 text-[10px] text-[var(--text-hint)]">근거: {r.basis}{r.threshold ? ` · 기준: ${r.threshold}` : ""}</p>}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* 5) 용도지역 걸침(혼재) 판정 — 국계법 §84(데이터 실재 시에만 라벨 노출) */}
      {showStraddle && straddle && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3" data-testid="mpx-straddle">
          <SectionTitle icon={<Scale className="size-3.5" aria-hidden />}>용도지역 걸침(혼재) 판정 — 국토계획법 제84조</SectionTitle>
          {straddle.applied_rule && (
            <p className="text-[11px] text-[var(--text-primary)]">
              적용 규칙: <b>{straddle.applied_rule}</b>
              {straddle.threshold_sqm != null ? <span className="text-[var(--text-hint)]"> (기준 {fmt(straddle.threshold_sqm)}㎡)</span> : null}
            </p>
          )}
          {straddle.honest_note && (
            <p className="mt-1 inline-flex items-start gap-1 text-[10px] leading-relaxed text-amber-500">
              <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden /> {straddle.honest_note}
            </p>
          )}
        </section>
      )}

      {/* 6) 제외 시나리오(what-if) — 차단 필지 제외 후 재정산 */}
      {showExclusion && exclusion && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3" data-testid="mpx-exclusion">
          <SectionTitle icon={<Scissors className="size-3.5" aria-hidden />}>제외 시나리오(what-if — 확정 아님)</SectionTitle>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2">
              <p className="text-[10px] font-bold uppercase text-[var(--text-hint)]">제외 필지·상실 면적</p>
              <p className="mt-0.5 font-black text-[var(--text-primary)]">
                {exclusion.excluded_parcels?.length ?? exclusion.applied_exclude_pnus?.length ?? 0}필지 · {sqm(exclusion.lost_area_sqm)}
              </p>
            </div>
            {exclusion.after && (
              <div className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-2">
                <p className="text-[10px] font-bold uppercase text-[var(--text-hint)]">제외 후 총면적</p>
                <p className="mt-0.5 font-black text-[var(--text-primary)]">{sqm(exclusion.after.gross_sqm)}</p>
                {exclusion.after.usable_confirmed_sqm != null && (
                  <p className="text-[10px] text-[var(--text-secondary)]">확정 사용가능 {sqm(exclusion.after.usable_confirmed_sqm)}</p>
                )}
              </div>
            )}
          </div>
          {(exclusion.excluded_parcels?.length ?? 0) > 0 && (
            <ul className="mt-2 space-y-0.5 text-[10px] text-[var(--text-secondary)]">
              {exclusion.excluded_parcels!.map((ep, i) => (
                <li key={(ep.pnu || "") + i}>· {ep.pnu || "필지"}{ep.land_category ? `(${ep.land_category})` : ""} — {sqm(ep.area_sqm)}</li>
              ))}
            </ul>
          )}
          {exclusion.note && <p className="mt-2 text-[10px] text-[var(--text-hint)]">{exclusion.note}</p>}
        </section>
      )}
    </div>
  );
}
