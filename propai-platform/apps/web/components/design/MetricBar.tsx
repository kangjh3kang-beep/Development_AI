"use client";

/**
 * 설계 스튜디오 하단 "설계 산출 KPI 바" — 설계 생성 결과 수치를 상시 확인하는 띠.
 *
 * 역할 분리(사용자 지적 '부지 지표 중복' 해소):
 *   · 상단 ContextHeader = "대상 식별"(프로젝트·주소·PNU·용도지역·대지면적) — 무엇을 대상으로 하는가.
 *   · 하단 이 바 = "설계 산출 KPI"(건폐율·용적률·연면적·층수·세대수) — 생성한 설계의 결과가 무엇인가.
 *   대지면적·용도지역 같은 식별 지표는 상단에서만 표기해 화면 내 중복을 제거한다(정보 손실 0 —
 *   같은 페이지 상단 ContextHeader가 정본으로 항상 노출). 건폐율/용적률은 설계 산출이므로 여기 남기되,
 *   설계 전(미생성)에는 부지 실효 한도로 폴백해 "설계가 준수해야 할 기준선"을 정직히 보여준다.
 *
 * 단일 진실원천(SSOT): 모든 값은 useProjectContextStore의 designData·siteAnalysis에서만 읽고,
 *   건폐율/용적률은 공용 리졸버(lib/zoning-ssot)로 "설계값 우선 → 부지 실효" 순위를 한 곳에서 따른다.
 *
 * 무날조 원칙: 어떤 칩이든 값이 없으면(null/undefined) "—"로만 표기한다(가짜 0/임의값 금지).
 *   designData·siteAnalysis가 둘 다 없으면 띠 자체를 그리지 않는다(빈 "—" 노출 방지).
 */

import { useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  resolveBcrWithBasis,
  resolveFarWithBasis,
  limitBasisLabel,
  type LimitBasis,
} from "@/lib/zoning-ssot";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import {
  summarizeCompliance,
  ruleTraceToEvidence,
  contractCanonicalFloors,
  type GeoStatus,
} from "@/lib/design-contract";

// 정수 ㎡ 표기(천단위 콤마). 미확보(null)면 "—". (가짜 0 금지 — 호출부에서 null 그대로 전달)
function fmtSqm(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${Math.round(v).toLocaleString()}㎡`;
}

// 퍼센트 표기(소수 그대로). 미확보면 "—".
function fmtPct(v: number | null | undefined): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${v}%`;
}

// 정수 + 단위 표기(층/세대 등). 미확보면 "—".
function fmtCount(v: number | null | undefined, suffix: string): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return `${v}${suffix}`;
}

/* ── C2R 계약(geometry_invariants) 등급 배지 — PASS/WARN/FAIL을 색으로 한눈에 ── */
// 백엔드 GeoStatus(PASS/PASS_WITH_WARNINGS/FAIL) → 한글 라벨 + 색. 미상(null)은 회색 "미산출".
const GEO_STATUS_LABEL: Record<GeoStatus, string> = {
  PASS: "정상(PASS)",
  PASS_WITH_WARNINGS: "경고(WARN)",
  FAIL: "오류(FAIL)",
};
const GEO_STATUS_CLASS: Record<GeoStatus, string> = {
  PASS: "border-emerald-500/40 bg-emerald-500/10 text-emerald-400",
  PASS_WITH_WARNINGS: "border-amber-500/40 bg-amber-500/10 text-amber-400",
  FAIL: "border-red-500/40 bg-red-500/10 text-red-400",
};

function GeoStatusBadge({ status }: { status: GeoStatus | null }) {
  // 미산출(null)이거나, 백엔드가 미래에 표(label/class)에 없는 새 등급 문자열을 보내도
  //   정직 회색 배지로 폴백한다(className에 "undefined"가 새지 않도록 방어 — LOW#1).
  if (!status || !(status in GEO_STATUS_CLASS)) {
    return (
      <span className="inline-flex items-center rounded-full border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">
        기하검증 미산출
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold ${GEO_STATUS_CLASS[status]}`}>
      기하검증 {GEO_STATUS_LABEL[status]}
    </span>
  );
}

/* ── 근거 인스펙터: 백엔드 근거 트레이스를 EvidencePanel/LegalRefChip 입력으로 매핑 ── */

// 백엔드 한도 산출 근거 한 줄(Evidence[]). store엔 unknown[]로 들어오므로 여기서 형태를 좁힌다.
//   claim: 무엇에 대한 근거인지(예: "적용 용적률")
//   value: 결과값(문자/숫자/불리언/null) · basis: 산식·근거 한 줄
//   source/link: 법령명·원문 링크 · confidence: 근거 신뢰등급
type Evidence = {
  claim?: string | null;
  value?: string | number | boolean | null;
  basis?: string | null;
  source?: string | null;
  confidence?: string | null;
  link?: string | null;
};

// 근거 신뢰등급(confidence) → 한글 라벨(DesignGenPanel과 동일 어휘). 미정의 키는 원문 그대로.
const CONF_LABEL: Record<string, string> = {
  ordinance: "실효(조례)",
  statutory: "법정상한",
  rule: "규칙",
  measured: "실측",
  estimated: "추정",
  unknown: "미확인",
};

// 근거 값 표기 — null/불리언을 안전하게(가짜 0 금지). 그 외는 그대로.
function fmtEvidenceValue(v: Evidence["value"]): string | number {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "예" : "아니오";
  return v;
}

// 백엔드 Evidence[](store의 unknown[]) → EvidencePanel EvidenceItem[].
//   DesignGenPanel:toEvidenceItems와 동일 매핑(claim/value/basis+신뢰등급/source|link→법령칩).
//   claim 없는 항목·비객체는 제외(빈 근거 행 방지·무날조).
function toEvidenceItems(ev?: unknown[] | null): EvidenceItem[] {
  if (!Array.isArray(ev)) return [];
  return ev
    .filter((e): e is Evidence => !!e && typeof e === "object")
    .filter((e) => typeof e.claim === "string" && e.claim.trim())
    .map((e) => {
      const conf = e.confidence
        ? CONF_LABEL[String(e.confidence)] ?? String(e.confidence)
        : "";
      const basis = [e.basis?.trim(), conf ? `근거:${conf}` : ""]
        .filter(Boolean)
        .join(" · ");
      return {
        label: String(e.claim).trim(),
        value: fmtEvidenceValue(e.value),
        basis: basis || null,
        legalRef:
          e.source || e.link
            ? { lawName: e.source || "근거", url: e.link ?? null }
            : null,
      };
    });
}

// 법령 원문 링크 한 줄(레지스트리 legalRefs 출력). store엔 unknown[]로 들어온다.
type LegalRefLike = {
  lawName?: string | null;
  law_name?: string | null;
  article?: string | null;
  title?: string | null;
  url?: string | null;
};

// legalRefs(unknown[]) → LegalRefChip 입력. 법령명 없는 항목은 제외(빈 칩 방지·정직성).
//   백엔드 키가 camel(lawName) 또는 snake(law_name) 둘 다 올 수 있어 양쪽 폴백.
function toLegalChips(refs?: unknown[] | null): {
  lawName: string;
  article?: string | null;
  title?: string | null;
  url?: string | null;
}[] {
  if (!Array.isArray(refs)) return [];
  return refs
    .filter((r): r is LegalRefLike => !!r && typeof r === "object")
    .map((r) => ({
      lawName: (r.lawName || r.law_name || "").trim(),
      article: r.article ?? null,
      title: r.title ?? null,
      url: r.url ?? null,
    }))
    .filter((r) => !!r.lawName);
}

// 칩 1개 — 라벨(작은 글씨) + 값(모노 계기 수치). 좁은 화면에선 가로스크롤(shrink-0).
//   note: 값 옆 소형 배지(예: "법정상한"·"실효") — 부지 폴백값의 근거를 정직 표기(무라벨 방지).
function Chip({
  label,
  value,
  note,
  noteTitle,
}: {
  label: string;
  value: string;
  note?: string | null;
  noteTitle?: string;
}) {
  return (
    <div className="flex min-w-[6.5rem] shrink-0 flex-col justify-center gap-0.5 px-3">
      <span className="cc-label text-[10px] text-[var(--text-tertiary)]">{label}</span>
      <span className="flex items-center gap-1">
        <span className="cc-num text-sm text-[var(--text-primary)]">{value}</span>
        {note && (
          <span
            title={noteTitle}
            className="shrink-0 rounded-full border border-[var(--line)] bg-[var(--surface-strong)] px-1 py-0.5 text-[8px] font-bold leading-none text-[var(--text-tertiary)]"
          >
            {note}
          </span>
        )}
      </span>
    </div>
  );
}

// 부지 폴백값 근거 툴팁 — 법정상한/실효를 정직히 구분(설계 산출값이 아니라 부지 기준선임을 명시).
function basisTitle(basis: LimitBasis): string {
  return basis === "national"
    ? "용도지역 법정상한 — 설계 생성 전 부지 기준선(설계 산출값 아님)"
    : "조례·종상향 반영 실효 한도 — 설계 생성 전 부지 기준선(설계 산출값 아님)";
}

export function MetricBar({ className }: { className?: string }) {
  // store 직접 구독(자체 SSOT 읽기) — props로 값을 받지 않아 어느 단계에서든 같은 정본을 본다.
  const designData = useProjectContextStore((s) => s.designData);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  // 근거(evidence/legalRefs)는 분석 경로에 따라 siteAnalysis·complianceData 등 여러 곳에 흩어져 있어
  // (SSOT 파편화), 실제 채워진 곳을 폭넓게 흡수해 '근거 없음' 오표기를 줄인다(무날조 — 없으면 그대로 없음).
  const complianceData = useProjectContextStore((s) => s.complianceData);

  // 근거 인스펙터 펼침 여부 — 기본 접힘(false)이라 종전 메트릭바 모양과 동일(무회귀).
  const [showEvidence, setShowEvidence] = useState(false);

  // 데이터 전무(둘 다 없음)면 띠 자체를 렌더하지 않는다(빈 "—" 7개 노출 방지).
  if (!designData && !siteAnalysis) return null;

  // 건폐율/용적률 — 설계 산출(designData) 우선, 없으면 부지 한도(공용 리졸버·근거 동봉). 미확보 시 null.
  //   대지면적·용도지역(식별 지표)은 상단 ContextHeader가 정본으로 표기하므로 이 바에서는 제외(중복 제거).
  //   ★부지 폴백값은 "법정상한"인지 "실효"인지 근거 배지를 함께 표기한다 — 종전엔 자연녹지 법정상한
  //   100%를 무라벨로 보여 옆 카드(층수클램프 실효 80%)와 모순처럼 읽혔다. 설계 산출값(designData)일
  //   때는 배지 없이 그대로(그게 이 바의 본래 KPI). 무날조: 값 없으면 null → "—".
  const designBcr = designData?.bcr ?? null;
  const designFar = designData?.far ?? null;
  const siteBcr = resolveBcrWithBasis(siteAnalysis);
  const siteFar = resolveFarWithBasis(siteAnalysis);
  const bcr = designBcr ?? siteBcr?.value ?? null;
  const far = designFar ?? siteFar?.value ?? null;
  // 부지 폴백(설계 산출값 아님)일 때만 근거 배지 — 법정상한/실효 정직 구분.
  const bcrNote = designBcr == null && siteBcr ? limitBasisLabel(siteBcr.basis) : null;
  const farNote = designFar == null && siteFar ? limitBasisLabel(siteFar.basis) : null;
  // 연면적·정본 층수·세대수 — 설계 산출(designData)에서만. 미확보 시 null → "—".
  const gfa = designData?.totalGfaSqm ?? null;
  const floors = designData?.floorCount ?? null; // ★INC1이 canonicalFloors로 기록한 정본 층수
  const units = designData?.unitCount ?? null;

  // 근거 데이터 추출(store 실데이터만 — 무날조). 빈 항목·법령명 없는 항목은 헬퍼가 제외.
  //  evidence/legalRefs는 채워진 위치가 경로마다 달라(siteAnalysis 직속·trustMeta·complianceData)
  //  순서대로 폴백해 실제 있는 근거를 표시한다(가짜 생성 아님 — 모두 없으면 '근거 없음').
  const siteTrustMeta = (siteAnalysis as { trustMeta?: { legalRefs?: unknown[] | null } } | null)?.trustMeta;
  const evidenceItems = toEvidenceItems(siteAnalysis?.evidence ?? complianceData?.evidence);
  const legalChips = toLegalChips(siteAnalysis?.legalRefs ?? siteTrustMeta?.legalRefs ?? complianceData?.legalRefs);
  const special = siteAnalysis?.specialParcel ?? null;
  const isSpecial = !!special?.isSpecial;

  // ── C2R 계약 근거(envelope_result·geometry_invariants) — 백엔드 설계엔진이 동봉한 검증·법규추적 ──
  //  store(designData.compliance)에 환류된 실제 계약만 읽는다(무목업·무날조 — 없으면 전부 표시 안 함).
  //  summary=헤드라인(등급·정본층수·run_id·해시), contractEvidence=적용 법규 추적(rule_trace → 근거 행).
  const compliance = designData?.compliance ?? null;
  const contractSummary = summarizeCompliance(compliance);
  const contractEvidence = ruleTraceToEvidence(compliance);
  const contractFloors = contractCanonicalFloors(compliance);

  // 보여줄 근거가 하나라도 있을 때만 '근거 보기' 토글을 노출한다(없으면 종전과 동일).
  const hasEvidence =
    evidenceItems.length > 0 || legalChips.length > 0 || isSpecial || !!contractSummary;

  return (
    <div
      className={[
        // grid 행으로 물리 분리되므로 z-index 비의존. 세로로 [확장 패널][칩 행] 순서로 쌓는다.
        "cc-panel flex min-h-[64px] flex-col px-2 py-2",
        className ?? "",
      ].join(" ")}
      role="group"
      aria-label="설계 산출 KPI"
    >
      {/* 근거 인스펙터(펼침 시에만) — 칩 행 위에 쌓여 "왜 이 값이 나왔나"를 한 창에서 보여준다. */}
      {showEvidence && hasEvidence && (
        <div id="metricbar-evidence" className="mb-2 max-h-[40vh] space-y-2 overflow-y-auto">
          {/* 1) 부지 한도 산출 근거 — Evidence[]를 EvidencePanel로(법령칩 포함). 없으면 생략. */}
          {evidenceItems.length > 0 && (
            <EvidencePanel title="부지 한도 근거" items={evidenceItems} defaultOpen />
          )}

          {/* 2) 특이부지 정직 경고 — 학교용지·맹지 등 정직 고지(앰버 박스). 없으면 생략. */}
          {isSpecial && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-[11px]">
              <p className="font-bold text-amber-400">특이부지 — 정직 고지</p>
              {special?.honest?.trim() && (
                <p className="mt-1 leading-relaxed text-[var(--text-secondary)]">
                  {special.honest.trim()}
                </p>
              )}
              {Array.isArray(special?.factors) && special.factors.length > 0 && (
                <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[var(--text-tertiary)]">
                  {special.factors.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 3) 법령 원문 링크 — evidence와 별개로 온 legalRefs를 칩 행으로. 없으면 생략. */}
          {legalChips.length > 0 && (
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5">
              <p className="mb-1.5 text-[11px] font-bold text-[var(--text-secondary)]">법령 원문</p>
              <div className="flex flex-wrap gap-1.5">
                {legalChips.map((r, i) => (
                  <LegalRefChip
                    key={i}
                    lawName={r.lawName}
                    article={r.article}
                    title={r.title}
                    url={r.url}
                  />
                ))}
              </div>
            </div>
          )}

          {/* 4) C2R 계약/검증 — 설계엔진이 동봉한 기하검증·적용법규·재현정보. 계약 있을 때만 표시. */}
          {contractSummary && (
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <p className="text-[11px] font-bold text-[var(--text-secondary)]">C2R 계약 · 설계 검증</p>
                {/* 기하 불변식 등급 배지(PASS/WARN/FAIL) — 미산출이면 정직 회색 표기. */}
                <GeoStatusBadge status={contractSummary.status} />
              </div>

              {/* 계약 헤드라인(정본층수·적용법규수·경고/오류·해시·run_id) — 모두 store 실값만, 미상은 표기 안 함. */}
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-[var(--text-tertiary)]">
                {/* 계약 정본 층수 — 권위 소스(envelope_result.metrics.canonical_floors). 없으면 "미산출". */}
                <span>
                  정본 층수{" "}
                  <span className="font-bold text-[var(--text-primary)]">
                    {contractFloors != null ? `${contractFloors}층` : "미산출"}
                  </span>
                </span>
                <span>
                  적용 법규{" "}
                  <span className="font-bold text-[var(--text-primary)]">{contractSummary.ruleCount}건</span>
                </span>
                {contractSummary.warningCount > 0 && (
                  <span className="text-amber-400">경고 {contractSummary.warningCount}건</span>
                )}
                {contractSummary.errorCount > 0 && (
                  <span className="text-red-400">오류 {contractSummary.errorCount}건</span>
                )}
                {contractSummary.ruleSetHashShort && (
                  <span title="적용 규칙 묶음 지문(rule_set_hash)">
                    규칙해시 <span className="font-mono text-[var(--text-secondary)]">{contractSummary.ruleSetHashShort}</span>
                  </span>
                )}
                {contractSummary.runId && (
                  <span title="산출 식별자(run_id) — 재현·출처추적">
                    run_id <span className="font-mono text-[var(--text-secondary)]">{contractSummary.runId}</span>
                  </span>
                )}
                {contractSummary.schemaVersion && (
                  <span className="text-[var(--text-hint)]">{contractSummary.schemaVersion}</span>
                )}
              </div>

              {/* 적용 법규 추적(rule_trace) → 근거 행. 있으면 EvidencePanel로, 없으면 정직 안내(무날조). */}
              {contractEvidence.length > 0 ? (
                <div className="mt-2">
                  <EvidencePanel title="적용 법규 추적 (rule_trace)" items={contractEvidence} defaultOpen={false} />
                </div>
              ) : (
                <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">
                  적용 법규 추적(rule_trace) 근거 없음 — 부지정보(용도지역·한도)가 갖춰지면 채워집니다.
                </p>
              )}
            </div>
          )}

          {/* 데이터가 하나도 없을 때 정직 안내(무목업) — 토글 게이트상 보통은 도달 안 함, 방어용. */}
          {evidenceItems.length === 0 && !isSpecial && legalChips.length === 0 && !contractSummary && (
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-[11px] text-[var(--text-tertiary)]">
              표시할 근거가 아직 없습니다 — 부지분석/설계를 실행하면 근거가 채워집니다.
            </div>
          )}
        </div>
      )}

      {/* 칩 행(설계 산출 5종) + 우측 토글. 종전 스타일(가로스크롤·모바일 줄바꿈) 그대로 유지.
          맨 앞 역할 라벨로 "이 띠 = 설계 산출 결과"임을 명시(상단 식별 지표와 역할 구분). */}
      <div className="flex min-h-[48px] items-center gap-1 overflow-x-auto max-md:flex-wrap max-md:overflow-x-visible">
        <span className="flex shrink-0 flex-col justify-center gap-0.5 border-r border-[var(--line)] pl-1 pr-3">
          <span className="cc-label text-[10px] text-[var(--accent-strong)]">설계 산출</span>
          <span className="text-[9px] font-semibold leading-none text-[var(--text-hint)]">생성 결과 KPI</span>
        </span>
        <Chip
          label="건폐율"
          value={fmtPct(bcr)}
          note={bcrNote}
          noteTitle={siteBcr ? basisTitle(siteBcr.basis) : undefined}
        />
        <Chip
          label="용적률"
          value={fmtPct(far)}
          note={farNote}
          noteTitle={siteFar ? basisTitle(siteFar.basis) : undefined}
        />
        <Chip label="연면적" value={fmtSqm(gfa)} />
        <Chip label="층수" value={fmtCount(floors, "층")} />
        <Chip label="세대수" value={fmtCount(units, "세대")} />

        {/* 근거 보기/접기 토글 — 근거 데이터가 있을 때만 노출(없으면 종전 모양 동일). */}
        {hasEvidence && (
          <button
            type="button"
            onClick={() => setShowEvidence((v) => !v)}
            aria-expanded={showEvidence}
            aria-controls="metricbar-evidence"
            className="ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-full border border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 px-3 py-1.5 text-[11px] font-semibold text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-strong)]/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-strong)]/40 max-md:ml-0"
          >
            {/* 근거·법령 링크 아이콘(체인) */}
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="shrink-0"
              aria-hidden="true"
            >
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            <span>{showEvidence ? "근거 접기" : "근거 보기"}</span>
            {/* 펼침 방향 화살표(접힘=위로 펼침, 펼침=아래로 접힘) */}
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`shrink-0 transition-transform ${showEvidence ? "rotate-180" : ""}`}
              aria-hidden="true"
            >
              <path d="m18 15-6-6-6 6" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
