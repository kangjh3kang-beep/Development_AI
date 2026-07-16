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
  // ★실 U5 오케스트레이터 정본 키(과거 프론트가 item/label·legal_ref·recommendation만 읽어
  //   3열 전부 "—"였다) — check_id·engine·legal_refs[]·improvement·note를 함께 수용.
  check_id?: string | null;
  engine?: string | null;
  status?: string | null; // pass|warning|fail|skipped|info|적합|조건부|부적합 등
  severity?: string | null;
  current?: string | number | null;
  limit?: string | number | null;
  unit?: string | null;
  recommendation?: string | null;
  correction?: string | null;
  improvement?: string | null;
  note?: string | null;
  legal_ref?: AuditLegalRef | null;
  legal_ref_key?: string | null;
  legal_refs?: AuditLegalRef[] | null;
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
  // ★blindspot 정본 항목(generate_blindspot.items)은 {claim, basis, confidence, citation_gate}.
  //   과거 프론트는 topic/note만 읽어 항목이 "—"로 비었다 — claim/basis도 수용.
  claim?: string | null;
  basis?: string | null;
  /** 0~1·0~100 수치 또는 high|medium|low 문자열 — 표기 시 정규화. 없으면 미표기(가짜값 금지). */
  confidence?: number | string | null;
  needs_expert?: boolean | null;
  /** 결정론 인용검문 결과 — gated=true면 미근거 인용 치환됨(전문가 확인 필요 신호). */
  citation_gate?: { gated?: boolean | null; reasons?: string[] | null } | null;
}

export interface AuditEvidence {
  label?: string | null;
  value?: string | number | null;
  basis?: string | null;
  legal_ref?: AuditLegalRef | null;
  legal_ref_key?: string | null;
}

/** 로드맵③ — 중심엔진 shadow 판정(설정 게이트가 켜졌을 때만 백엔드가 동봉·기본 미존재).
 * shadow_integration.shadow_compare 반환 계약과 1:1(engine_verdict: compliant|needs_review|
 * non_compliant|null — 3값). matched=false면 플랫폼 자체 판정과 엔진 판정이 갈렸다는 뜻(참고 신호). */
export interface AuditDeliberationResult {
  engine_verdict?: string | null;
  platform_verdict?: string | null;
  matched?: boolean | null;
  divergence_score?: number | null;
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
  // ★pass_rate 정직화(design_review_service) — 이 파라미터 검토가 실제 검사하지 않은
  //   항목(일조·주차·피난 등)의 한글 라벨 목록. 있을 때만 "미검사 N항목"으로 표시(정직).
  not_checked_items?: string[] | null;
  // 로드맵③ additive — 게이트 off·구서버는 항상 undefined(기존 렌더 그대로).
  deliberation_result?: AuditDeliberationResult | null;
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
    // ★실 U5 status 어휘 "warning" 포함(과거 "warn"만 있어 실엔진 warning이 unknown으로 샜다).
    ["조건부", "조건부 적합", "조건부적합", "conditional", "warn", "warning", "주의", "correction_required"].includes(s)
  )
    return "conditional";
  if (["부적합", "non_compliant", "noncompliant", "fail", "불가", "critical"].includes(s))
    return "fail";
  return "unknown";
}

/** finding.status → 칩 스타일/라벨 — 미지의 값은 원문 그대로(정직). */
function findingChip(status?: string | null): { label: string; cls: string } {
  const s = (status ?? "").trim().toLowerCase();
  // 실 U5 비판정 status — 검사 못 함/정보성은 판정 색이 아닌 중립 표기(정직).
  if (s === "skipped") return { label: "생략", cls: VERDICT_META.unknown.chip };
  if (s === "not_checked") return { label: "미검사", cls: VERDICT_META.unknown.chip };
  if (s === "info")
    return {
      label: "정보",
      cls: "border-[var(--status-info)]/40 bg-[var(--status-info)]/10 text-[var(--status-info)]",
    };
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

/** 엔진 코드 → 사람이 읽는 검사 항목 라벨(실 U5 finding.engine 기준 — 비전문가 대행 표기). */
const ENGINE_LABEL: Record<string, string> = {
  rules8: "법규 8룰(건폐·용적·높이·이격)",
  design_review: "설계 파라미터 법규검토",
  solar_envelope: "정북일조 인벨로프",
  parking: "법정 주차",
  permit: "인허가 가능성",
  change_risk: "설계변경 리스크",
  incentives: "인센티브·종상향",
  case_compare: "인근 인허가 사례",
  grammar: "평면 문법(LDK·연결성·채광)",
  bl_rules: "피난·방화(건축법 §34/§46/§35)",
};

/** finding의 '검사 항목' 라벨 — item/label 우선, 없으면 engine 라벨, 최후 check_id(정직). */
function findingItemLabel(f: AuditFinding): string {
  if (f.item?.trim()) return f.item.trim();
  if (f.label?.trim()) return f.label.trim();
  const eng = (f.engine ?? "").toString();
  if (ENGINE_LABEL[eng]) return ENGINE_LABEL[eng];
  return (f.check_id ?? "—").toString();
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

/** 로드맵⑤ — 제출번들(zip) 다운로드용 실 기하값. 미보유 항목은 백엔드 SubmissionBundleRequest
 * 기본값(대지폭·깊이 등)에 위임한다(프론트가 값을 지어내지 않음 — 무날조). */
export interface AuditBundleContext {
  buildingWidthM?: number | null;
  buildingDepthM?: number | null;
  floorCount?: number | null;
  buildingUse?: string | null;
  zoneCode?: string | null;
  projectName?: string | null;
  unitTypes?: string[] | null;
  households?: number | null;
}

/** 제출번들(zip) 다운로드 — design_v61.py POST /{project_id}/submission-bundle 소비.
 *
 * CadBimIntegrationPanel.exportSubmissionBundle(직전 캠페인 구현) 패턴을 미러: 인증 Bearer
 * 토큰 동봉 raw fetch(blob) + 422(필수시트 미충족) 등 실패 사유를 그대로 노출(무음 실패 금지).
 * bundleContext가 없으면(설계 스튜디오 매스 미보유 — 도면세트 없음) 버튼을 비활성화한다.
 */
function AuditSubmissionBundleDownload({
  projectId,
  bundleContext,
}: {
  projectId: string;
  bundleContext: AuditBundleContext;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function download() {
    setBusy(true);
    setError("");
    try {
      const token =
        typeof window !== "undefined"
          ? window.localStorage.getItem("propai_access_token") ?? ""
          : "";
      const res = await fetch(
        `${apiV1BaseUrl()}/design/${encodeURIComponent(projectId)}/submission-bundle`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            // 실보유 기하값만 전송 — 미보유(대지폭·깊이 등)는 생략해 백엔드 선언 기본값에 위임.
            building_width_m: bundleContext.buildingWidthM ?? undefined,
            building_depth_m: bundleContext.buildingDepthM ?? undefined,
            floor_count: bundleContext.floorCount ?? undefined,
            building_use: bundleContext.buildingUse ?? undefined,
            zone_code: bundleContext.zoneCode ?? undefined,
            project_name: bundleContext.projectName ?? undefined,
            unit_types:
              bundleContext.unitTypes && bundleContext.unitTypes.length > 0
                ? bundleContext.unitTypes
                : undefined,
            households: bundleContext.households ?? undefined,
            // 제출번들 전용(SubmissionBundleRequest) — 발행일은 클라이언트 명시 인자(서버 now() 금지 계약).
            issue_date: new Date().toISOString().slice(0, 10),
            include_dxf: true,
            include_report: true,
            include_boq: true,
          }),
          signal: AbortSignal.timeout(120000),
        },
      );
      if (!res.ok) {
        // 백엔드 거부(4xx)는 사유를 그대로 노출(무날조). 필수시트 미충족(422)은 detail.missing[] 동봉.
        let msg = `제출번들 생성 실패 (HTTP ${res.status})`;
        try {
          const j = await res.json();
          const detail = (j as { detail?: unknown })?.detail;
          if (typeof detail === "string" && detail.trim()) {
            msg = detail.trim();
          } else if (detail && typeof detail === "object") {
            const d = detail as { message?: unknown; missing?: unknown };
            const head =
              typeof d.message === "string" && d.message.trim() ? d.message.trim() : msg;
            const missing = Array.isArray(d.missing)
              ? d.missing.filter((x): x is string => typeof x === "string")
              : [];
            msg = missing.length > 0 ? `${head} — 누락 시트: ${missing.join(", ")}` : head;
          }
        } catch {
          /* JSON 아님 — 기본 메시지 유지 */
        }
        if (res.status === 401) msg = `로그인이 필요합니다 — ${msg}`;
        throw new Error(msg);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${bundleContext.projectName || "PropAI"}_제출번들.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "제출번들 생성에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => void download()}
        disabled={busy}
        className="rounded-xl border border-[var(--accent-strong)]/50 bg-transparent px-4 py-2 text-xs font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] disabled:opacity-50"
      >
        {busy ? "준비 중…" : "제출번들(zip) ↓"}
      </button>
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
            // 법령 근거: 실 U5는 legal_refs[](레지스트리 레코드 배열) — 있으면 다중 칩, 없으면
            // 단일 legal_ref/legal_ref_key 폴백(과거 계약 하위호환). 백엔드 legal_refs 증발 봉합.
            const directRefs = Array.isArray(f.legal_refs)
              ? f.legal_refs.filter((r) => r?.law_name?.trim())
              : [];
            const ref = resolveLegalRef(f.legal_ref, f.legal_ref_key, pools);
            // 개선안: recommendation/correction(구계약) → improvement(실 U5) 순.
            const recommendation = f.recommendation ?? f.correction ?? f.improvement;
            return (
              <tr key={i} className="border-b border-[var(--line)] last:border-b-0 align-top">
                <td className="py-2 pr-3 font-semibold text-[var(--text-primary)]">
                  {findingItemLabel(f)}
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
                <td className="py-2 pr-3">
                  {directRefs.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {directRefs.map((r, j) => legalRefChip(r, `ref-${i}-${j}`))}
                    </div>
                  ) : (
                    legalRefChip(ref, `ref-${i}`) ?? <span className="text-[var(--text-hint)]">—</span>
                  )}
                </td>
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

/** confidence: high|medium|low 문자열 라벨(실 U5 blindspot 항목). */
const CONF_LABEL: Record<string, string> = { high: "높음", medium: "보통", low: "낮음" };

function BlindSpotList({ spots }: { spots: AuditBlindSpot[] }) {
  return (
    <div className="grid gap-2">
      {spots.map((b, i) => {
        // confidence 정규화 — high|medium|low 문자열 또는 0~1/0~100 수치. 없으면 미표기(가짜값 금지).
        const raw = b.confidence;
        let confDisplay: string | null = null;
        if (typeof raw === "string" && CONF_LABEL[raw.trim().toLowerCase()]) {
          confDisplay = `확신도 ${CONF_LABEL[raw.trim().toLowerCase()]}`;
        } else if (typeof raw === "number" && Number.isFinite(raw)) {
          confDisplay = `확신도 ${Math.round(raw <= 1 ? raw * 100 : raw)}%`;
        }
        // 실 U5 항목은 claim/basis — topic/note(구계약) 우선, 없으면 claim/basis로 폴백.
        const mainText = b.topic?.trim() || b.claim?.trim() || "—";
        const detail =
          b.note?.trim() || (b.basis?.trim() ? `근거: ${b.basis.trim()}` : null);
        // 인용검문 치환(citation_gate.gated) 또는 명시적 needs_expert면 '전문가 확인 필요'.
        const needsExpert = b.needs_expert ?? b.citation_gate?.gated ?? false;
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
              {confDisplay != null && (
                <span className="text-[10px] font-bold text-[var(--text-tertiary)]">
                  {confDisplay}
                </span>
              )}
              {needsExpert && (
                <span className="inline-flex items-center rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--status-warning)]">
                  전문가 확인 필요
                </span>
              )}
              <p className="text-[12px] font-bold text-[var(--text-primary)]">{mainText}</p>
            </div>
            {detail && (
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                {detail}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── 로드맵③ — 심의엔진(shadow) 판정 블록 ──
 * SeniorVerdictCard(components/analysis)는 senior_consultation 계약(evaluations[]·citations[]
 * 다중 도메인 자문)전용이라 이 shadow 비교 결과(엔진 3값 verdict + divergence, 세부 근거·인용
 * 없음)와 데이터 모양이 다르다 — 억지로 끼워 맞추면 evaluations/citations를 날조해야 해서
 * 재사용하지 않고, 이 파일에 이미 있는 판정 배지 언어(VERDICT_META)를 그대로 재사용한다(보고서
 * 전체와 시각적으로 일관). */

const DELIB_VERDICT_LABEL: Record<string, string> = {
  compliant: "통과", needs_review: "조건부", non_compliant: "보류",
};

function deliberationTone(v?: string | null): VerdictTone {
  const s = (v ?? "").trim().toLowerCase();
  if (s === "compliant") return "pass";
  if (s === "needs_review") return "conditional";
  if (s === "non_compliant") return "fail";
  return "unknown";
}

function DeliberationVerdictBlock({ result }: { result: AuditDeliberationResult }) {
  const ev = (result.engine_verdict ?? "").trim().toLowerCase();
  const tone = deliberationTone(ev);
  const meta = VERDICT_META[tone];
  const label = DELIB_VERDICT_LABEL[ev] ?? (result.engine_verdict?.trim() || "판정 불가");
  return (
    <div className={`rounded-xl border p-3 ${meta.hero}`}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[11px] font-bold text-[var(--text-secondary)]">
          심의엔진 판정(중심엔진 shadow 관측)
        </p>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${meta.chip}`}>
          {label}
        </span>
        {result.matched === false && (
          <span className="rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 px-1.5 py-0.5 text-[9px] font-bold text-[var(--status-warning)]">
            플랫폼 판정과 상이
          </span>
        )}
      </div>
      <p className="mt-1 text-[11px] text-[var(--text-hint)]">
        참고용 관측치입니다 — 운영이 표면화 설정을 켰을 때만 표시되며, 플랫폼 자체 판정을
        대체하지 않습니다.
      </p>
    </div>
  );
}

/* ── 메인 뷰 ── */

export function AuditReportView({
  report,
  onReset,
  projectId,
  bundleContext,
}: {
  report: DesignAuditReport;
  /** "다시 심사" — 부모가 보고서를 닫고 스테퍼로 복귀. */
  onReset?: () => void;
  /** 로드맵⑤ — 제출번들(zip) 대상 프로젝트 ID. 실 프로젝트(수동주소 심사가 아님)일 때만 전달. */
  projectId?: string | null;
  /** 실 도면세트(설계 스튜디오 매스) 보유 시에만 전달 — 없으면 버튼 자체를 표시하지 않는다(정직). */
  bundleContext?: AuditBundleContext | null;
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
            {/* 로드맵⑤ — 제출번들(zip). 실 프로젝트+실 도면세트(설계 스튜디오 매스) 보유 시에만
                버튼 자체를 노출한다(비활성 버튼 대신 정직 생략 — PDF 다운로드 관행과 동일). */}
            {projectId && bundleContext && (
              <AuditSubmissionBundleDownload projectId={projectId} bundleContext={bundleContext} />
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
            evidence.length > 0 ||
            !!sec.deliberation_result; // 로드맵③ — 게이트 off·구서버는 항상 falsy(회귀 없음)
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
                  {Array.isArray(sec.not_checked_items) && sec.not_checked_items.length > 0 && (
                    <p
                      className="text-[11px] text-[var(--text-hint)]"
                      title={sec.not_checked_items.join(", ")}
                    >
                      ※ 미검사 {sec.not_checked_items.length}항목(파라미터 검토 범위 밖 — 별도
                      확인 필요): {sec.not_checked_items.join(", ")}
                    </p>
                  )}
                  {sec.case_comparison && <CaseComparisonBlock comparison={sec.case_comparison} />}
                  {incentives.length > 0 && (
                    <IncentiveCards incentives={incentives} pools={pools} />
                  )}
                  {blindSpots.length > 0 && <BlindSpotList spots={blindSpots} />}
                  {sec.deliberation_result && (
                    <DeliberationVerdictBlock result={sec.deliberation_result} />
                  )}
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
