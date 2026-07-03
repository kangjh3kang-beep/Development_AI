"use client";

/**
 * AuditReportView — 설계심사(DA-7) 결과 보고서 뷰.
 *
 *  S0 종합판정 히어로(적합=success / 조건부=warning / 부적합=error 의미색)
 *  S1~S7 섹션 아코디언:
 *   - findings 표(판정·현재/한도·법령근거 LegalRefChip·개선안)
 *   - 사례비교(분위 밴드·중앙값 격차 pp) — DesignReviewService.compare_with_nearby_cases 출력 형태
 *   - 인센티브 카드(경로·근거법령·'예상치' 마커)
 *   - 사각지대('AI 추정' 라벨 + confidence + '전문가 확인 필요' 구분)
 *   - EvidencePanel(공용) 재사용 — 산출 근거 트레이스
 *  PDF 다운로드: GET /design-audit/{id}/pdf (blob) — id 없으면 버튼 미표시(정직).
 *
 * 정직성 원칙:
 *  - 법령 URL은 백엔드 legal_reference_registry 출력만 렌더(LegalRefChip이 스킴 방어).
 *  - 섹션/판정/통계 결손은 "없음/판정 불가"로 그대로 표기 — 가짜값 생성 금지.
 */

import { useState } from "react";
import { apiV1BaseUrl } from "@/lib/api-client";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";

/* ── 보고서 타입(방어적 — 백엔드 결손 필드 graceful 수용) ── */

export interface AuditLegalRef {
  key?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  /** law.go.kr 한글주소 — legal_reference_registry 출력만 들어온다(여기서 조립 금지). */
  url?: string | null;
}

export interface AuditFinding {
  item?: string | null;
  label?: string | null;
  status?: string | null; // pass|warn|fail|적합|조건부|부적합 등
  severity?: string | null;
  current?: string | number | null;
  limit?: string | number | null;
  unit?: string | null;
  recommendation?: string | null;
  correction?: string | null;
  legal_ref?: AuditLegalRef | null;
  legal_ref_key?: string | null;
}

export interface AuditCasePosition {
  value?: number | null;
  p25?: number | null;
  p50?: number | null;
  p75?: number | null;
  band?: string | null;
}

export interface AuditCaseComparison {
  available?: boolean;
  sample_count?: number | null;
  far_position?: AuditCasePosition | null;
  bcr_position?: AuditCasePosition | null;
  vs_median_far_pp?: number | null;
  vs_median_bcr_pp?: number | null;
  note?: string | null;
}

export interface AuditIncentive {
  name?: string | null;
  path?: string | null;
  description?: string | null;
  bonus?: string | null;
  bonus_far_pp?: number | null;
  /** true면 '예상치' 마커 — 실제 적용은 심의·허가권자 판단에 따름. */
  estimated?: boolean | null;
  legal_ref?: AuditLegalRef | null;
  legal_ref_key?: string | null;
}

export interface AuditBlindSpot {
  topic?: string | null;
  note?: string | null;
  /** 0~1 또는 0~100 — 표기 시 정규화. 없으면 수치 미표기(가짜값 금지). */
  confidence?: number | null;
  needs_expert?: boolean | null;
}

export interface AuditEvidence {
  label?: string | null;
  value?: string | number | null;
  basis?: string | null;
  legal_ref?: AuditLegalRef | null;
  legal_ref_key?: string | null;
}

export interface AuditSection {
  id?: string | null; // "S1"~"S7"
  title?: string | null;
  status?: string | null;
  summary?: string | null;
  findings?: AuditFinding[] | null;
  case_comparison?: AuditCaseComparison | null;
  incentives?: AuditIncentive[] | null;
  blind_spots?: AuditBlindSpot[] | null;
  evidence?: AuditEvidence[] | null;
  legal_refs?: AuditLegalRef[] | null;
}

export interface DesignAuditReport {
  id?: string | null;
  audit_id?: string | null;
  verdict?: string | null; // 적합|조건부|부적합|compliant|conditional|non_compliant 등
  verdict_label?: string | null;
  summary?: string | null;
  sections?: AuditSection[] | null;
  legal_refs?: AuditLegalRef[] | null;
  generated_at?: string | null;
  message?: string | null;
}

/* ── 판정 의미색 매핑(디자인 토큰) ── */

type VerdictTone = "pass" | "conditional" | "fail" | "unknown";

const VERDICT_META: Record<
  VerdictTone,
  { label: string; hero: string; chip: string }
> = {
  pass: {
    label: "적합",
    hero: "border-[var(--status-success)]/40 bg-[var(--status-success)]/[0.08]",
    chip: "border-[var(--status-success)]/40 bg-[var(--status-success)]/15 text-[var(--status-success)]",
  },
  conditional: {
    label: "조건부 적합",
    hero: "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/[0.08]",
    chip: "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 text-[var(--status-warning)]",
  },
  fail: {
    label: "부적합",
    hero: "border-[var(--status-error)]/40 bg-[var(--status-error)]/[0.08]",
    chip: "border-[var(--status-error)]/40 bg-[var(--status-error)]/15 text-[var(--status-error)]",
  },
  unknown: {
    label: "판정 불가",
    hero: "border-[var(--line-strong)] bg-[var(--surface-soft)]",
    chip: "border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
  },
};

function verdictTone(v?: string | null): VerdictTone {
  const s = (v ?? "").trim().toLowerCase();
  if (!s) return "unknown";
  if (["적합", "compliant", "pass", "ok", "통과"].includes(s)) return "pass";
  if (
    ["조건부", "조건부 적합", "조건부적합", "conditional", "warn", "주의", "correction_required"].includes(s)
  )
    return "conditional";
  if (["부적합", "non_compliant", "noncompliant", "fail", "불가", "critical"].includes(s))
    return "fail";
  return "unknown";
}

/** finding.status → 칩 스타일/라벨 — 미지의 값은 원문 그대로(정직). */
function findingChip(status?: string | null): { label: string; cls: string } {
  const tone = verdictTone(status);
  if (tone === "unknown") {
    return {
      label: status?.trim() || "—",
      cls: VERDICT_META.unknown.chip,
    };
  }
  // findings 표는 간결 라벨(적합/조건부/부적합)을 쓴다.
  const label = tone === "pass" ? "적합" : tone === "conditional" ? "조건부" : "부적합";
  return { label, cls: VERDICT_META[tone].chip };
}

/* ── 값/근거 헬퍼 ── */

function fmtVal(v?: string | number | null, unit?: string | null): string {
  if (v == null || v === "") return "—";
  const body = typeof v === "number" ? v.toLocaleString() : String(v);
  return unit?.trim() ? `${body}${unit.trim()}` : body;
}

/** 직접 legal_ref 우선, 없으면 legal_ref_key를 섹션/보고서 레지스트리 풀에서 해석. */
function resolveLegalRef(
  direct: AuditLegalRef | null | undefined,
  refKey: string | null | undefined,
  pools: Array<AuditLegalRef[] | null | undefined>,
): AuditLegalRef | null {
  if (direct?.law_name?.trim()) return direct;
  if (refKey) {
    for (const pool of pools) {
      const hit = pool?.find((r) => r?.key === refKey && r?.law_name?.trim());
      if (hit) return hit;
    }
  }
  return null;
}

function legalRefChip(ref: AuditLegalRef | null, key: string | number) {
  if (!ref?.law_name?.trim()) return null;
  return (
    <LegalRefChip
      key={key}
      lawName={ref.law_name}
      article={ref.article}
      title={ref.title}
      url={ref.url}
    />
  );
}

/* ── 사례비교 밴드 라벨(DesignReviewService._position_band 값) ── */

const BAND_LABEL: Record<string, string> = {
  below_p25: "하위 25% 미만(보수적)",
  p25_p50: "p25~중앙값 구간",
  p50_p75: "중앙값~p75 구간",
  above_p75: "상위 25% 초과(공격적)",
  insufficient_sample: "표본 부족 — 통계 비표기",
};

function CasePositionBlock({
  title,
  pos,
  vsMedianPp,
}: {
  title: string;
  pos?: AuditCasePosition | null;
  vsMedianPp?: number | null;
}) {
  if (!pos) return null;
  const band = pos.band ? BAND_LABEL[pos.band] ?? pos.band : null;
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-bold text-[var(--text-secondary)]">{title}</p>
        {band && (
          <span className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-strong)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">
            {band}
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12px]">
        <span className="font-black text-[var(--text-primary)]">
          설계값 {pos.value != null ? `${pos.value.toLocaleString()}%` : "—"}
        </span>
        <span className="text-[var(--text-tertiary)]">
          p25 {pos.p25 != null ? `${pos.p25}%` : "—"} · 중앙값{" "}
          {pos.p50 != null ? `${pos.p50}%` : "—"} · p75 {pos.p75 != null ? `${pos.p75}%` : "—"}
        </span>
        {vsMedianPp != null && (
          <span
            className={`font-bold ${
              vsMedianPp > 0 ? "text-[var(--status-warning)]" : "text-[var(--status-success)]"
            }`}
          >
            중앙값 대비 {vsMedianPp > 0 ? "+" : ""}
            {vsMedianPp}pp
          </span>
        )}
      </div>
    </div>
  );
}

/* ── PDF 다운로드(blob) — ReportPdfDownload 패턴 준용 ── */

function AuditPdfDownload({ auditId }: { auditId: string }) {
  // 통합 보고서 생성엔진: PDF/PPT/Word 중 선택 다운로드(같은 데이터·같은 디자인).
  const [busy, setBusy] = useState<"pdf" | "pptx" | "docx" | null>(null);
  const [error, setError] = useState("");

  async function download(format: "pdf" | "pptx" | "docx") {
    setBusy(format);
    setError("");
    try {
      const token =
        typeof window !== "undefined"
          ? window.localStorage.getItem("propai_access_token") ?? ""
          : "";
      const res = await fetch(
        `${apiV1BaseUrl()}/design-audit/${encodeURIComponent(auditId)}/pdf?format=${format}`,
        {
          method: "GET",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        },
      );
      if (!res.ok) {
        throw new Error(`보고서 생성에 실패했습니다 (HTTP ${res.status}).`);
      }
      const contentType = res.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        // 파일 대신 JSON이 오면 오류 메시지로 정직 표기(빈 파일 다운로드 방지).
        const payload = (await res.json()) as { detail?: string; message?: string };
        throw new Error(payload?.detail || payload?.message || "보고서가 아직 준비되지 않았습니다.");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `design-audit-${auditId}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "보고서 다운로드에 실패했습니다.");
    } finally {
      setBusy(null);
    }
  }

  const FORMATS = [
    { key: "pdf", label: "PDF" },
    { key: "pptx", label: "PPT" },
    { key: "docx", label: "Word" },
  ] as const;

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5">
        {FORMATS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => void download(f.key)}
            disabled={busy !== null}
            className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy === f.key ? "준비 중…" : `${f.label} ↓`}
          </button>
        ))}
      </div>
      {error && <span className="text-[11px] font-semibold text-[var(--status-error)]">{error}</span>}
    </div>
  );
}

/* ── 섹션 본문 블록 ── */

function FindingsTable({
  findings,
  pools,
}: {
  findings: AuditFinding[];
  pools: Array<AuditLegalRef[] | null | undefined>;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-left text-[12px]">
        <thead>
          <tr className="border-b border-[var(--line)] text-[11px] uppercase tracking-wider text-[var(--text-tertiary)]">
            <th className="py-2 pr-3 font-bold">검사 항목</th>
            <th className="py-2 pr-3 font-bold">판정</th>
            <th className="py-2 pr-3 font-bold">현재</th>
            <th className="py-2 pr-3 font-bold">한도</th>
            <th className="py-2 pr-3 font-bold">법적 근거</th>
            <th className="py-2 font-bold">개선안</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f, i) => {
            const chip = findingChip(f.status);
            const ref = resolveLegalRef(f.legal_ref, f.legal_ref_key, pools);
            const recommendation = f.recommendation ?? f.correction;
            return (
              <tr key={i} className="border-b border-[var(--line)] last:border-b-0 align-top">
                <td className="py-2 pr-3 font-semibold text-[var(--text-primary)]">
                  {f.item || f.label || "—"}
                </td>
                <td className="py-2 pr-3">
                  <span className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-bold ${chip.cls}`}>
                    {chip.label}
                  </span>
                </td>
                <td className="cc-num py-2 pr-3 font-bold text-[var(--text-primary)]">
                  {fmtVal(f.current, f.unit)}
                </td>
                <td className="cc-num py-2 pr-3 text-[var(--text-secondary)]">
                  {fmtVal(f.limit, f.unit)}
                </td>
                <td className="py-2 pr-3">{legalRefChip(ref, `ref-${i}`) ?? <span className="text-[var(--text-hint)]">—</span>}</td>
                <td className="py-2 text-[var(--text-secondary)]">
                  {recommendation?.trim() || "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CaseComparisonBlock({ comparison }: { comparison: AuditCaseComparison }) {
  if (comparison.available === false) {
    return (
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 text-[12px] text-[var(--text-hint)]">
        {comparison.note?.trim() || "인근 인허가 사례 없음 — 비교 생략"}
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
        <span className="font-bold text-[var(--text-secondary)]">인근 인허가 사례 비교</span>
        {comparison.sample_count != null && <span>표본 {comparison.sample_count}건</span>}
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        <CasePositionBlock
          title="용적률(FAR) 위치"
          pos={comparison.far_position}
          vsMedianPp={comparison.vs_median_far_pp}
        />
        <CasePositionBlock
          title="건폐율(BCR) 위치"
          pos={comparison.bcr_position}
          vsMedianPp={comparison.vs_median_bcr_pp}
        />
      </div>
      {comparison.note?.trim() && (
        <p className="text-[11px] text-[var(--text-hint)]">{comparison.note.trim()}</p>
      )}
    </div>
  );
}

function IncentiveCards({
  incentives,
  pools,
}: {
  incentives: AuditIncentive[];
  pools: Array<AuditLegalRef[] | null | undefined>;
}) {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      {incentives.map((inc, i) => {
        const ref = resolveLegalRef(inc.legal_ref, inc.legal_ref_key, pools);
        const bonus =
          inc.bonus?.trim() ||
          (inc.bonus_far_pp != null
            ? `용적률 +${inc.bonus_far_pp.toLocaleString()}%p`
            : null);
        return (
          <div
            key={i}
            className="rounded-xl border border-[var(--accent-strong)]/25 bg-[var(--accent-soft)] p-3"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <p className="text-[12px] font-bold text-[var(--text-primary)]">
                {inc.name || inc.path || "인센티브 경로"}
              </p>
              {inc.estimated && (
                <span
                  title="예상치 — 실제 적용은 심의·허가권자 판단에 따라 달라질 수 있습니다."
                  className="inline-flex cursor-help items-center rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--status-warning)]"
                >
                  예상치
                </span>
              )}
            </div>
            {inc.path && inc.name && (
              <p className="mt-0.5 text-[11px] text-[var(--text-tertiary)]">{inc.path}</p>
            )}
            {bonus && (
              <p className="cc-num mt-1 text-sm font-black text-[var(--accent-strong)]">{bonus}</p>
            )}
            {inc.description?.trim() && (
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                {inc.description.trim()}
              </p>
            )}
            {ref && <div className="mt-2">{legalRefChip(ref, `inc-${i}`)}</div>}
          </div>
        );
      })}
    </div>
  );
}

function BlindSpotList({ spots }: { spots: AuditBlindSpot[] }) {
  return (
    <div className="grid gap-2">
      {spots.map((b, i) => {
        // confidence 0~1/0~100 표기 변형 정규화 — 수치 없으면 미표기(가짜값 금지).
        const raw = b.confidence;
        const pct =
          raw != null && Number.isFinite(raw)
            ? Math.round(raw <= 1 ? raw * 100 : raw)
            : null;
        return (
          <div
            key={i}
            className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                title="규칙·데이터로 단정하지 못해 AI가 추정한 항목입니다."
                className="inline-flex cursor-help items-center rounded-full border border-[var(--status-info)]/40 bg-[var(--status-info)]/10 px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--status-info)]"
              >
                AI 추정
              </span>
              {pct != null && (
                <span className="text-[10px] font-bold text-[var(--text-tertiary)]">
                  확신도 {pct}%
                </span>
              )}
              {b.needs_expert && (
                <span className="inline-flex items-center rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--status-warning)]">
                  전문가 확인 필요
                </span>
              )}
              <p className="text-[12px] font-bold text-[var(--text-primary)]">{b.topic || "—"}</p>
            </div>
            {b.note?.trim() && (
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                {b.note.trim()}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── 메인 뷰 ── */

export function AuditReportView({
  report,
  onReset,
}: {
  report: DesignAuditReport;
  /** "다시 심사" — 부모가 보고서를 닫고 스테퍼로 복귀. */
  onReset?: () => void;
}) {
  const sections = Array.isArray(report.sections) ? report.sections : [];
  // 첫 섹션 기본 펼침 — 나머지는 아코디언 토글.
  const [openSet, setOpenSet] = useState<Set<number>>(() => new Set(sections.length ? [0] : []));
  const toggle = (i: number) =>
    setOpenSet((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  const tone = verdictTone(report.verdict);
  const meta = VERDICT_META[tone];
  const verdictLabel =
    tone === "unknown" && (report.verdict_label?.trim() || report.verdict?.trim())
      ? (report.verdict_label?.trim() || report.verdict?.trim())!
      : meta.label;
  const auditId = report.id ?? report.audit_id ?? null;

  return (
    <div className="grid gap-4">
      {/* S0 종합판정 히어로 */}
      <section className={`rounded-2xl border p-5 ${meta.hero}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
              S0 · 종합판정
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-3 py-1 text-sm font-black ${meta.chip}`}>
                {verdictLabel}
              </span>
              {report.generated_at && (
                <span className="text-[11px] text-[var(--text-hint)]">
                  생성 {report.generated_at}
                </span>
              )}
            </div>
            {report.summary?.trim() && (
              <p className="mt-2 max-w-3xl text-[13px] leading-relaxed text-[var(--text-primary)]">
                {report.summary.trim()}
              </p>
            )}
            {!report.summary?.trim() && tone === "unknown" && (
              <p className="mt-2 text-[12px] text-[var(--text-hint)]">
                서버가 종합판정을 반환하지 않았습니다 — 아래 섹션별 결과를 확인하세요.
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            {auditId ? (
              <AuditPdfDownload auditId={auditId} />
            ) : (
              <span className="text-[11px] text-[var(--text-hint)]">
                보고서 ID 없음 — PDF 다운로드 미제공
              </span>
            )}
            {onReset && (
              <button
                type="button"
                onClick={onReset}
                className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"
              >
                ← 입력 수정·다시 심사
              </button>
            )}
          </div>
        </div>
        {/* 보고서 전역 법령 근거(레지스트리 검증 딥링크만) */}
        {Array.isArray(report.legal_refs) && report.legal_refs.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--line)] pt-3">
            <span className="mr-1 self-center text-[11px] font-semibold text-[var(--text-tertiary)]">
              법적 근거
            </span>
            {report.legal_refs.map((ref, i) => legalRefChip(ref, i))}
          </div>
        )}
      </section>

      {/* S1~S7 섹션 아코디언 */}
      {sections.length === 0 ? (
        <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/[0.06] p-5 text-sm text-[var(--status-warning)]">
          {report.message?.trim() || "심사 섹션 결과가 비어 있습니다 — 입력(부지·개요)을 보강해 다시 실행해 주세요."}
        </div>
      ) : (
        sections.map((sec, i) => {
          const open = openSet.has(i);
          const secChip = sec.status ? findingChip(sec.status) : null;
          const pools = [sec.legal_refs, report.legal_refs];
          const findings = Array.isArray(sec.findings) ? sec.findings : [];
          const incentives = Array.isArray(sec.incentives) ? sec.incentives : [];
          const blindSpots = Array.isArray(sec.blind_spots) ? sec.blind_spots : [];
          const evidence = Array.isArray(sec.evidence) ? sec.evidence : [];
          const hasBody =
            !!sec.summary?.trim() ||
            findings.length > 0 ||
            !!sec.case_comparison ||
            incentives.length > 0 ||
            blindSpots.length > 0 ||
            evidence.length > 0;
          return (
            <section
              key={i}
              className="rounded-2xl border border-[var(--line)] bg-[var(--surface-secondary)] shadow-[var(--shadow-sm)]"
            >
              <button
                type="button"
                onClick={() => toggle(i)}
                aria-expanded={open}
                className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left"
              >
                <span className="flex min-w-0 items-center gap-2">
                  {sec.id && (
                    <span className="shrink-0 rounded-md border border-[var(--line-strong)] bg-[var(--surface-strong)] px-1.5 py-0.5 text-[10px] font-black text-[var(--text-tertiary)]">
                      {sec.id}
                    </span>
                  )}
                  <span className="truncate text-sm font-bold text-[var(--text-primary)]">
                    {sec.title || `섹션 ${i + 1}`}
                  </span>
                  {secChip && (
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-bold ${secChip.cls}`}>
                      {secChip.label}
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-[11px] font-semibold text-[var(--accent-strong)]">
                  {open ? "접기" : "펼치기"}
                </span>
              </button>

              {open && (
                <div className="grid gap-3 border-t border-[var(--line)] px-5 py-4">
                  {!hasBody && (
                    <p className="text-[12px] text-[var(--text-hint)]">
                      이 섹션에는 표시할 결과가 없습니다.
                    </p>
                  )}
                  {sec.summary?.trim() && (
                    <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
                      {sec.summary.trim()}
                    </p>
                  )}
                  {findings.length > 0 && <FindingsTable findings={findings} pools={pools} />}
                  {sec.case_comparison && <CaseComparisonBlock comparison={sec.case_comparison} />}
                  {incentives.length > 0 && (
                    <IncentiveCards incentives={incentives} pools={pools} />
                  )}
                  {blindSpots.length > 0 && <BlindSpotList spots={blindSpots} />}
                  {evidence.length > 0 && (
                    <EvidencePanel
                      title="산출 근거"
                      defaultOpen={false}
                      items={evidence.map((ev): EvidenceItem => {
                        const ref = resolveLegalRef(ev.legal_ref, ev.legal_ref_key, pools);
                        return {
                          label: ev.label ?? "",
                          value: ev.value ?? "—",
                          basis: ev.basis,
                          legalRef: ref?.law_name
                            ? {
                                lawName: ref.law_name,
                                article: ref.article,
                                title: ref.title,
                                url: ref.url,
                              }
                            : null,
                        };
                      })}
                    />
                  )}
                </div>
              )}
            </section>
          );
        })
      )}

      <p className="text-[11px] text-[var(--text-hint)]">
        ※ 본 심사는 AI 사전검토 참고자료이며 법적 효력이 없습니다. 인허가 판단은 허가권자(지자체)·건축사
        등 전문가 확인이 필요합니다.
      </p>
    </div>
  );
}
