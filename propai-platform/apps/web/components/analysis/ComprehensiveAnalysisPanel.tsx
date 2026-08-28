"use client";

import { IntegrityWarnings } from "@/components/ui/IntegrityWarnings";
import { useState, useCallback, useEffect, useMemo, Fragment, type ReactNode } from "react";
import { BarChart3, Construction, ExternalLink, Home, Map, MapPin, Tag, TrendingUp, Wallet, type LucideIcon } from "lucide-react";
import dynamic from "next/dynamic";
const SatongMapShellDynamic = dynamic(
  () => import("@/components/precheck/SatongMapShell").then((m) => m.SatongMapShell),
  { ssr: false },
);
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { UpzoningFarRangeNotice, UpzoningFarRangeValue } from "@/components/common/UpzoningFarRange";
import { SiteInfraPoiCard } from "@/components/site/SiteInfraPoiCard";
import { SeniorVerdictCard, type SeniorConsultation } from "@/components/analysis/SeniorVerdictCard";
import { BuildableOptionsCard } from "@/components/analysis/BuildableOptionsCard";
import { AllowedBuildingsCard } from "@/components/analysis/AllowedBuildingsCard";
import { DecisionSpecialistCard } from "@/components/projects/DecisionSpecialistCard";
import type { DecisionSpecialist } from "@/components/projects/decision-brief-types";
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { adaptEvidence } from "@/lib/evidence/adaptEvidence";
import { AnalysisHistoryCard } from "@/components/common/AnalysisHistoryCard";
import { optionsSummary } from "@/lib/use-analysis-history";
import { parcelDataToRows, type ParcelRow } from "@/lib/parcel-rows";
import { parcelDisplayAddress } from "@/lib/pnu";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { riskLevelStyle } from "@/lib/risk-level-style";
import { apiClient } from "@/lib/api-client";
import {
  formatArea, formatPercent, formatPercentDelta, formatUpzoningFarRange,
  type UpzoningFarRange,
} from "@/lib/formatters"; // 면적·비율 표기 SSOT(UX A2) — 로컬 중복 formatArea 대체
import { fieldMeta, formatFieldValue, formatDelta } from "@/lib/analysis-field-labels"; // 필드 라벨·단위 SSOT(원시 키 노출 근절)
import { fetchInterpretation } from "@/lib/interpretation-job"; // 해석 제출·폴링 공용(형제 소비처와 공유)
import {
  PERSONAS, sectionOrderFor, isExpandedFor, personaByKey,
  type PersonaKey, type AnalysisSectionId,
} from "@/lib/analysis-persona"; // 관점별 강조 순서·요약문 SSOT(W5)
import { analysisTargetKey } from "@/lib/analysis-target"; // 분석 대상 판정 키(프로젝트+주소 복합)
import { useAnalysisTargetGuard } from "@/hooks/useAnalysisTargetGuard"; // 대상 전환 시 옛 결과 무효화 SSOT
import { readFieldAudit, findingsForSection } from "@/lib/field-audit"; // 자가검증 표면화 SSOT(W3)
import { FieldAuditNotice } from "@/components/analysis/FieldAuditNotice";
import { CredibilitySummaryCard } from "@/components/analysis/CredibilitySummaryCard";
import { SpecialParcelActions } from "@/components/analysis/SpecialParcelActions";
import { developabilityLabel } from "@/lib/zoning-ssot"; // 개발가능성 코드 → 사용자 라벨(공용 SSOT)

/* ── Helpers ── */

function formatWon(value: number): string {
  if (!value || value <= 0) return "-";
  if (value >= 1e8) return `${(value / 1e8).toFixed(1)}억원`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(0)}만원`;
  return `${value.toLocaleString("ko-KR")}원`;
}

function formatManWon(value: number): string {
  if (!value || value <= 0) return "-";
  return `${value.toLocaleString("ko-KR")}만원`;
}

/* ── Sub-components ── */

function SectionCard({ title, icon: Icon, children, defaultOpen = false }: {
  title: string; icon: LucideIcon; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left hover:bg-[var(--surface-soft)] transition-colors"
      >
        <Icon className="size-5 text-[var(--text-secondary)]" aria-hidden />
        <span className="flex-1 text-sm font-bold text-[var(--text-primary)]">{title}</span>
        <span className="text-[var(--text-hint)] text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="px-5 pb-5 space-y-3">{children}</div>}
    </div>
  );
}

function MarketAiBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="text-xs font-black text-[var(--status-success)] mb-1">{label}</p>
      <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
        {text}
      </p>
    </div>
  );
}

function AiInterpretation({ text }: { text: string }) {
  return (
    <div className="mt-3 rounded-lg bg-blue-500/5 border border-blue-500/20 p-4">
      <div className="flex items-start gap-2">
        <span className="text-blue-400 text-sm shrink-0">AI</span>
        <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
          {text}
        </p>
      </div>
    </div>
  );
}

function AnnotationLine({ text }: { text: string }) {
  const tagMatch = text.match(/^\[(.+?)\]\s*(.*)/);
  if (!tagMatch) return <p className="text-[10px] text-[var(--text-secondary)]">{text}</p>;

  const [, tag, content] = tagMatch;
  const colors: Record<string, string> = {
    "법정 상한": "bg-blue-500/20 text-blue-400",
    "조례 제한": "bg-[var(--status-warning)]/20 text-[var(--status-warning)]",
    "조례 동일": "bg-gray-500/20 text-gray-400",
    "실효 용적률": "bg-[var(--status-success)]/20 text-[var(--status-success)]",
    "실효 건폐율": "bg-[var(--status-success)]/20 text-[var(--status-success)]",
    "적용 결과": "bg-[var(--accent-strong)]/20 text-[var(--accent-strong)]",
    "기부체납 여력": "bg-purple-500/20 text-purple-400",
  };
  const color = colors[tag] || "bg-gray-500/20 text-gray-400";

  return (
    <div className="flex items-start gap-2 text-[10px]">
      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-bold ${color}`}>{tag}</span>
      <span className="text-[var(--text-secondary)] leading-relaxed">{content}</span>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
      <p className="text-[10px] text-[var(--text-hint)] mb-0.5">{label}</p>
      <p className="text-sm font-bold text-[var(--text-primary)]">{String(value)}</p>
    </div>
  );
}

// 개발계획 종합 리스크 등급 → 배지 색은 **lib/risk-level-style** 로 옮겼다.
//   ★1,500줄 클라이언트 패널 안에 두면 순수 함수 테스트가 next/dynamic·지도 셸까지
//     통째로 임포트해, 계약과 무관한 이유로 락이 죽는다(적대 리뷰 지적 · 2026-08-27).
//   표 키의 SSOT 는 백엔드 SEVERITY_ORDER 이고 파생형 락이 강제한다.

// ★SEVERITY_CARD_STYLE(심각도→카드색) 제거(2026-08-01): 값 변화의 상대폭으로 경고색을 칠하면
//   입력 변경(필지 재선택)까지 빨간 HIGH가 되는 라이브 오표기가 재발한다. 카드색은 이제
//   change_cause 기준으로만 정해진다(ChangeCauseCard 참조).

function PermitBadge({ complexity }: { complexity: number }) {
  const colors = ["", "bg-[var(--status-success)]/20 text-[var(--status-success)]", "bg-blue-500/20 text-blue-400", "bg-[var(--status-warning)]/20 text-[var(--status-warning)]", "bg-orange-500/20 text-orange-400", "bg-[var(--status-error)]/20 text-[var(--status-error)]"];
  const labels = ["", "매우 쉬움", "쉬움", "보통", "어려움", "매우 어려움"];
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${colors[complexity] || colors[3]}`}>
      {labels[complexity] || "보통"}
    </span>
  );
}

/**
 * ChangeCauseCard — "이전 분석과 무엇이·왜 달라졌는지"를 사용자 언어로 렌더.
 *
 * ## 왜 이렇게 바뀌었나 (2026-08-01)
 *
 * 종전 "이전 분석과 모순 감지"는 값 차이를 전부 **모순**이라 부르고 상대변화율로 심각도를
 * 칠했다. 그런데 프로덕션 실제 4건은 하나도 모순이 아니었다 — 셋은 사용자가 필지를 3개→2개로
 * 다시 고른 것(입력 변경), 하나는 학교 중복집계 버그 수정. 전부 빨간 HIGH로 떠서 *지금 숫자가
 * 의심스럽다*는 정반대 인상을 줬다.
 *
 * 그래서 표시의 기준을 심각도가 아니라 **원인**(backend change_cause)으로 바꾼다:
 *   INPUT_CHANGED   → 중립색. 비교 대상이 아님을 설명(경고 아님)
 *   VERSION_CHANGED → 중립색. 최신이 더 정확하다고 안내
 *   UNEXPLAINED     → ★유일하게 경고색. 사용자가 실제로 확인해야 하는 경우
 *   NONE            → 카드 대신 한 줄 배지
 *
 * ★불변식: max_severity로 카드색을 정하지 않는다. 그렇게 하면 입력 변경까지 빨간 경고가 되는
 *   종전 결함이 그대로 재발한다(백엔드 contradiction.py 주석과 쌍).
 */
export function ChangeCauseCard({ contradictions }: { contradictions?: AnalysisResult }) {
  const [showOther, setShowOther] = useState(false);
  if (!contradictions) return null;

  const cause = (contradictions.change_cause ?? null) as AnalysisResult | null;
  const groups: AnalysisResult[] = Array.isArray(contradictions.groups) ? contradictions.groups : [];
  const raw: AnalysisResult[] = Array.isArray(contradictions.contradictions) ? contradictions.contradictions : [];

  // ★하위호환: 구버전 백엔드(change_cause 없음)는 원인을 알 수 없다. 원인을 지어내지 않고
  //   "확인 필요"로만 표기한다(없는 확신 금지 — 백엔드 UNEXPLAINED와 동일 정직 규칙).
  const causeCode = (cause?.cause as string) ?? (groups.length || raw.length ? "UNEXPLAINED" : "NONE");
  if (causeCode === "NONE") {
    if (groups.length === 0 && raw.length === 0) {
      return (
        <p className="text-[11px] text-[var(--text-hint)]">
          ✓ 이전 분석과 동일합니다 (같은 조건 · 주요 수치 일치)
        </p>
      );
    }
  }

  const needsReview = causeCode === "UNEXPLAINED";
  const cardStyle = needsReview
    ? "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10"
    : "border-[var(--line-strong)] bg-[var(--surface-strong)]";

  const headline = (cause?.headline as string) || "이전 분석과 달라진 항목이 있습니다";
  const reason = (cause?.reason as string) || "이전 분석의 조건 정보가 없어 원인을 확인할 수 없습니다.";
  const trustHint = (cause?.trust_hint as string) || "";

  // 표시 행 — 그룹 우선(패턴 단위 압축본), 없으면 원시 목록.
  const items = groups.length > 0 ? groups : raw;
  const known = items.filter((it) => fieldMeta(String(it.key_pattern ?? it.key ?? "")) !== null);
  const unknown = items.filter((it) => fieldMeta(String(it.key_pattern ?? it.key ?? "")) === null);

  return (
    <div className={`rounded-2xl border p-4 ${cardStyle}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-bold text-[var(--text-primary)]">
          {needsReview ? "⚠ " : ""}{headline}
        </span>
        <span className="rounded-full bg-black/10 px-2 py-0.5 text-[10px] font-bold text-[var(--text-primary)]">
          {needsReview ? "확인 필요" : causeCode === "VERSION_CHANGED" ? "최신이 정확" : "비교 불가"}
        </span>
      </div>

      <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">{reason}</p>

      {known.length > 0 && (
        <div className="mt-2.5 rounded-xl border border-[var(--line-strong)] bg-[var(--surface)]/60 p-2.5">
          <p className="mb-1.5 text-[10px] font-semibold text-[var(--text-hint)]">무엇이 달라졌나</p>
          <ul className="space-y-1">
            {known.map((it, i) => {
              const key = String(it.key_pattern ?? it.key ?? "");
              const meta = fieldMeta(key);
              const delta = formatDelta(it.prev, it.now, meta);
              return (
                <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-[11px]">
                  <span className="min-w-[7rem] text-[var(--text-hint)]">{meta?.label}</span>
                  <span className="text-[var(--text-secondary)]">{formatFieldValue(it.prev, meta)}</span>
                  <span className="text-[var(--text-hint)]">→</span>
                  <span className="font-semibold text-[var(--text-primary)]">{formatFieldValue(it.now, meta)}</span>
                  {delta ? <span className="text-[10px] text-[var(--text-hint)]">({delta})</span> : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ★등재되지 않은 키는 이름을 지어내지 않는다 — 접어서 원본 그대로 보여준다(숨김도 날조도 아님). */}
      {unknown.length > 0 && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setShowOther((v) => !v)}
            className="text-[10px] font-semibold text-[var(--accent-strong)]"
          >
            {showOther ? "기타 변경 항목 접기 ▲" : `기타 변경 항목 ${unknown.length}건 보기 ▼`}
          </button>
          {showOther && (
            <ul className="mt-1 space-y-0.5 pl-3">
              {unknown.map((it, i) => (
                <li key={i} className="text-[10px] text-[var(--text-hint)]">
                  · {String(it.key_pattern ?? it.key ?? "")}: {String(it.prev)} → {String(it.now)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {trustHint ? (
        <p className="mt-2.5 rounded-lg bg-black/5 px-2.5 py-2 text-[11px] leading-relaxed text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">어느 쪽을 믿어야 하나요? </span>
          {trustHint}
        </p>
      ) : null}
    </div>
  );
}

/** 용적률 시나리오 표(1-B 최적화 시뮬레이션) — 전체 표 원형(요약 축약 시에도 재사용). */
function ScenarioTable({ scenarios, recommended }: { scenarios: AnalysisResult[]; recommended?: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-[var(--line)] text-[var(--text-hint)]">
            <th className="py-2 px-2 text-left">시나리오</th>
            <th className="py-2 px-1 text-right">달성 용적률</th>
            <th className="py-2 px-1 text-right">인센티브</th>
            <th className="py-2 px-1 text-right">기부체납</th>
            <th className="py-2 px-1 text-right">연면적 증가</th>
            <th className="py-2 px-1 text-center">상한</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((sc, i) => (
            <tr key={i} className={`border-b border-[var(--line)]/50 ${sc.scenario_name === recommended ? "bg-[var(--accent-strong)]/5" : ""}`}>
              <td className="py-2 px-2 font-bold text-[var(--text-primary)]">
                {sc.scenario_name === recommended && <span className="text-[var(--accent-strong)] mr-1">★</span>}
                {sc.scenario_name}
              </td>
              {/* ★비율 3칸은 포매터 경유(#530 계약) — 종전에는 원시 보간이라 값이 없으면
                  "%"·"+%" 라는 깨진 표기가 나왔고, 기부체납은 0%와 미확보가 똑같이 "-"였다. */}
              <td className="py-2 px-1 text-right font-bold text-[var(--accent-strong)]">{formatPercent(sc.achieved_far)}</td>
              <td className="py-2 px-1 text-right text-[var(--text-secondary)]">{formatPercentDelta(sc.total_incentive)}</td>
              <td className="py-2 px-1 text-right text-[var(--text-secondary)]">{formatPercent(sc.donation_pct)}</td>
              <td className="py-2 px-1 text-right text-[var(--text-secondary)]">{sc.gfa_increase_sqm > 0 ? `+${sc.gfa_increase_sqm}m²` : "-"}</td>
              <td className="py-2 px-1 text-center">{sc.is_capped ? <span className="text-[var(--status-warning)] text-[10px] font-bold">상한</span> : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * FarOptimizationPanel — "1-B. 용적률 최적화 시뮬레이션" 섹션.
 *
 * 전 시나리오의 achieved_far가 상한(cap_far)과 동일하면(인센티브를 더 써도 무의미) 표 대신
 * 요약 1행 + '자세히' 접기로 원 표를 강등한다. structural_cap_pct(구조상한 — 층수 제한이
 * 지배하는 경우)가 있으면 그 사실도 함께 부기해 "인센티브를 더 계산해봐야 소용없는 이유"를 밝힌다.
 */
function FarOptimizationPanel({ farOpt, structuralCapPct }: { farOpt?: AnalysisResult; structuralCapPct?: number | null }) {
  const [showDetail, setShowDetail] = useState(false);
  if (!farOpt?.scenarios) return null;
  const scenarios: AnalysisResult[] = farOpt.scenarios;
  const capFar = farOpt.cap_far;
  // achieved_far(1자리)·cap_far(2자리 가능) 반올림 자릿수가 달라 엄격 등가 대신 0.5%p
  // 허용오차로 "상한 도달"을 판정한다(소수 상한에서 요약 강등 누락 방지 — 안전 방향 유지).
  const allCapped =
    scenarios.length > 0 &&
    Number.isFinite(capFar) &&
    scenarios.every(
      (sc) => Number.isFinite(sc.achieved_far) && Math.abs((sc.achieved_far as number) - (capFar as number)) < 0.5,
    );

  return (
    <SectionCard title="1-B. 용적률 최적화 시뮬레이션" icon={TrendingUp} defaultOpen>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <Field label="현재 기본 용적률" value={formatPercent(farOpt.base_far)} />
        <Field label="최대 달성 가능" value={formatPercent(farOpt.max_achievable_far)} />
        {/* 통합모드의 상한은 §84 면적가중 통합값(단일필지 시행령 정값과 의미가 달라 라벨 분리) */}
        <Field label={farOpt.integrated ? "통합 상한 (면적가중)" : "법정 상한"} value={formatPercent(capFar)} />
      </div>
      {farOpt.recommended_scenario && (
        <div className="rounded-lg bg-[var(--accent-strong)]/10 border border-[var(--accent-strong)]/30 p-3 mb-3">
          <p className="text-[10px] font-bold text-[var(--accent-strong)]">추천: {farOpt.recommended_scenario}</p>
          <p className="text-[10px] text-[var(--text-secondary)]">{farOpt.recommended_reason}</p>
        </div>
      )}
      {allCapped ? (
        <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
          <p className="text-xs font-bold text-[var(--text-primary)]">
            {/* ★같은 카드 위쪽 Field가 formatPercent(capFar)를 쓰는데 이 문장만 원시 보간이라
                "152.8%" 옆에 "152.83333333333334%"가 같이 떴다(실측). 비교 짝을 맞춘다. */}
            모든 시나리오가 상한 {formatPercent(capFar)}에서 cap — 인센티브 추가 완화 불가
          </p>
          {structuralCapPct != null && (
            <p className="mt-1 text-[11px] text-[var(--status-warning)]">
              층수 제한이 지배 — 구조상한 {formatPercent(structuralCapPct)} 기준으론 인센티브 무의미
            </p>
          )}
          <button
            type="button"
            onClick={() => setShowDetail((v) => !v)}
            className="mt-2 text-[11px] font-semibold text-[var(--accent-strong)]"
          >
            {showDetail ? "표 접기 ▲" : "자세히(원 표) ▼"}
          </button>
          {showDetail && (
            <div className="mt-2">
              <ScenarioTable scenarios={scenarios} recommended={farOpt.recommended_scenario} />
            </div>
          )}
        </div>
      ) : (
        <ScenarioTable scenarios={scenarios} recommended={farOpt.recommended_scenario} />
      )}
    </SectionCard>
  );
}

/* ── Types ── */

interface ModelInfo {
  id: string;
  name: string;
  tier: "standard" | "premium" | "economy";
}

interface ProviderInfo {
  provider: string;
  name: string;
  models: ModelInfo[];
  default_model: string;
}

/* ── Main Component ── */

type AnalysisResult = Record<string, any>;

// ★F3(QA REQUEST CHANGES) supply_areas 항목 타입 — additive(blocked_reason?/note? 신설).
//   백엔드가 개발불가 게이트(GB·비연접 등)로 공급규모 산정을 억제할 때 dev_type/지표 필드는
//   전부 비우고(undefined) blocked_reason(또는 note)만 채워 반환한다("판정불가" 스텁 — P0-2/F1).
//   나머지 필드는 AnalysisResult(Record<string, any>) 계약을 그대로 잇는다(느슨한 기존 패턴 유지).
type SupplyAreaItem = AnalysisResult & {
  dev_type?: string | null;
  total_gfa_pyeong?: number | null;
  blocked_reason?: string | null;
  note?: string | null;
};

export function ComprehensiveAnalysisPanel() {
  const siteAnalysis = useProjectContextStore((state) => state.siteAnalysis);
  // ★분석 대상 판정은 주소만으로는 부족하다 — 프로젝트까지 함께 본다(analysisTargetKey).
  //   주소가 없는 프로젝트(다필지)로 바꿔도 대상이 바뀐 것을 알아채야 하기 때문.
  const projectId = useProjectContextStore((state) => state.projectId);
  const [address, setAddress] = useState("");
  // 다필지: 검색·엑셀로 등록된 전 필지 주소(2필지↑ 시 통합 개발방식 분석 노출)
  const [parcels, setParcels] = useState<string[]>([]);
  // ★다필지 통합분석용 필지 상세(면적·용도지역·실효한도) — 백엔드 통합집계 전송 페이로드.
  const [parcelRows, setParcelRows] = useState<ParcelRow[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  // ★2단계(AI 해석) 진행 상태 — loading과 분리한다. 1단계 결과는 이미 화면에 있으므로
  //   전체 로딩으로 덮으면 사용자가 받은 분석이 사라진 것처럼 보인다(점진 렌더의 요점).
  const [interpreting, setInterpreting] = useState(false);
  // ★W2-d 파이프라인 토큰 — 종합분석 시작 시 1 올려 POI·개발방식 시뮬을 함께 태운다.
  //   사용자 지적: "종합 분석 시작을 누르면 입지 인프라·최적 개발방식도 같이 분석되어야 한다."
  const [pipelineRunToken, setPipelineRunToken] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("anthropic");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [selectionNotice, setSelectionNotice] = useState("");
  // 히스토리 카드 재조회 신호 — handleAnalyze 완료 시 증가시켜 AnalysisHistoryCard가 새 항목을 반영한다.
  const [historyRefreshTick, setHistoryRefreshTick] = useState(0);
  // ★관점(페르소나) — 기본은 중립(null)이다. 아무도 고르지 않으면 종전과 정확히 같은 순서로
  //   보인다. 관점 기능이 켜졌다는 이유만으로 화면이 멋대로 바뀌면 안 된다.
  const [persona, setPersona] = useState<PersonaKey | null>(null);
  const sectionOrder = useMemo(() => sectionOrderFor(persona), [persona]);
  const personaSpec = personaByKey(persona);
  // 관점이 지정한 펼침 상태가 있으면 그것을, 없으면(중립) 종전 기본값을 그대로 쓴다.
  const openFor = useCallback(
    (id: AnalysisSectionId, fallback: boolean) => isExpandedFor(persona, id) ?? fallback,
    [persona],
  );

  useEffect(() => {
    apiClient.get<{ providers: ProviderInfo[] }>("/analysis/llm-providers")
      .then(data => {
        setProviders(data.providers ?? []);
        if ((data.providers?.length ?? 0) > 0) {
          setSelectedProvider(data.providers[0].provider);
          setSelectedModel(data.providers[0].default_model);
        }
      })
      .catch(() => {}); // 실패 시 기본값 유지
  }, []);

  // ★대상(프로젝트+주소)이 바뀌면 화면의 옛 결과를 비운다 — 종전에는 주소 문자열만 비교해서
  //   ①주소 없는 프로젝트로 전환 ②siteAnalysis가 통째로 비는 전환에서 옛 분석이 그대로 남았다
  //   (머리글=새 프로젝트 / 본문=옛 주소인 모순 표시). 판정은 useAnalysisTargetGuard 한 곳으로.
  const targetKey = analysisTargetKey(projectId, siteAnalysis?.address ?? "");
  const { begin: beginAnalysisRun, isCurrent: isCurrentTarget } = useAnalysisTargetGuard(
    targetKey,
    useCallback(() => {
      setResult(null);
      setError(null);
    }, []),
    // ★실제 결과 상태를 함께 넘긴다 — 가드가 begin() 호출로만 추적하면 실행 경로가 아닌
    //   방법으로 결과가 붙었을 때 조용히 죽는다(대상을 바꿔도 안 지워진다).
    result != null,
  );

  useEffect(() => {
    if (!siteAnalysis) {
      setAddress("");
      setParcels([]);
      setParcelRows([]);
      return;
    }
    const mainAddr = siteAnalysis.address ?? "";
    setAddress(mainAddr);

    const parcelList = siteAnalysis.parcels ?? [];
    if (parcelList.length > 0) {
      // ★★2026-08-28 봉합 — 종전엔 `p.address` 를 **그대로** 썼다. 스토어 필지 주소는 지번이
      //   없는 경우가 있어(예: "경기도 오산시 내삼미동") **77필지가 모두 같은 문자열**이 되고,
      //   백엔드 `scenario_simulator._merge` 가 주소로 중복제거하며 **1필지로 붕괴**했다.
      //   그 결과 86,755㎡ 부지가 **44㎡**(약 13평)로 시뮬레이션돼 「도시개발사업 1만㎡ 미달」 등
      //   **개발방식 19건이 거짓 '불가'** 로 막혔다(라이브 재현: parcel_count=1 · total_area=44.0).
      //
      //   ★처방이 이미 저장소에 있었다 — `lib/parcel-rows.ts` 가 `parcelDisplayAddress` 로
      //     **PNU 에서 지번을 파생**해 같은 동의 필지를 구분한다. 그 파일 주석이 이 결함을 그대로
      //     적어 뒀다: *"여기서 지번이 빠지면 백엔드가 같은 동의 필지를 구분하지 못한다."*
      //     형제 3화면(파이프라인·시장·규제)은 그 헬퍼를 쓰는데 **이 패널만 손수 복제**했다
      //     (이 파일은 같은 모듈에서 **타입만** 임포트하고 빌더는 베껴 썼다).
      //
      //   ★두 값은 의미가 다르므로 갈라서 만든다(한 헬퍼로 뭉치면 표시가 회귀한다):
      //     · `parcels`    = 사용자가 **고른** 것 → 표시·렌더 게이트. 면적 유무로 거르지 않는다.
      //     · `parcelRows` = 우리가 **보낼 수 있는** 것 → 면적>0(`parcelDataToRows` 의미론).
      setParcels(
        parcelList
          .map((p) => parcelDisplayAddress(p.address, p.pnu ?? null))
          .filter(Boolean),
      );
      setParcelRows(parcelDataToRows(parcelList));
    } else if (mainAddr) {
      setParcels([mainAddr]);
      setParcelRows([
        {
          address: mainAddr,
          // ★P1(감사): raw landAreaSqm 직독 금지 — 다필지 통합면적 우선 공용헬퍼로
          //   (단일 PNU 재조회가 대표면적으로 덮어써도 통합면적이 이긴다: 면적 SSOT 패리티).
          area_sqm: effectiveLandAreaSqm(siteAnalysis) ?? null,
          zone_type: siteAnalysis.zoneCode ?? null,
          farPct: null,
          bcrPct: null,
          farLegalPct: null,
          bcrLegalPct: null,
        }
      ]);
    }
    // ★deps에서 result를 뺐다 — 이 이펙트는 더 이상 result를 지우지 않는다(무효화는 가드가 담당).
    //   result를 deps에 둔 채 안에서 setResult를 부르면 자기 자신을 다시 깨우는 구조가 된다.
  }, [siteAnalysis]);

  /**
   * 종합분석 실행 — ★2단계 점진 렌더(W2-c).
   *
   * 왜 나눴나: 종합분석은 오리진 실측 190초인데 Cloudflare 엣지가 ~125초에서 끊는다.
   * 한 번에 다 받으려 하면 **분석 전체가 524로 사라진다**(실측 7회 중 6회 실패).
   *   1단계 `/analysis/comprehensive` (include_interpretation:false) — 결정론 분석만. 즉시 렌더.
   *   2단계 `/analysis/interpretation` — 1단계 결과를 넘겨 AI 해석만 생성 후 **병합**.
   *
   * ★2단계가 실패해도 1단계 결과를 잃지 않는다. 해석 필드만 'unavailable'로 정직 표기된다
   * (종전에는 하나의 타임아웃이 분석 전체를 날렸다).
   */
  const handleAnalyze = useCallback(async () => {
    if (!address.trim()) { setError("주소를 입력해주세요."); return; }
    setLoading(true); setError(null); setResult(null); setInterpreting(false);
    // ★이 분석이 '어느 대상의 것인지' 착수 시점에 못 박는다. 종합분석은 오래 걸려서, 기다리는
    //   사이 사용자가 프로젝트를 바꾸면 뒤늦게 도착한 옛 대상의 응답이 새 화면에 붙을 수 있다.
    const runKey = beginAnalysisRun();
    // ★착수 시점에 올린다 — POI·시뮬은 종합분석 결과가 아니라 주소만 필요하므로 병렬 실행이
    //   맞다(1단계 완료를 기다리면 사용자가 그만큼 더 오래 빈 카드를 본다).
    setPipelineRunToken((t) => t + 1);
    let core: AnalysisResult | null = null;
    try {
      core = await apiClient.post<AnalysisResult>("/analysis/comprehensive", {
        body: {
          address,
          llm_provider: selectedProvider || undefined,
          llm_model: selectedModel || undefined,
          // ★다필지(2필지↑)면 통합집계용 필지목록 전송 → 종합분석이 '통합면적' 기준 산출(543㎡ 단일 버그 제거).
          //   단일/미등록은 미전송(백엔드 단일경로 = N=1 항등). 면적 보유 필지만.
          ...(parcelRows.length > 1 ? { parcels: parcelRows } : {}),
          include_interpretation: false, // 1단계: 해석 제외로 엣지 컷오프 회피
        },
        useMock: false,
      });
      // 대상이 바뀌었으면 이 응답은 남의 것이다 — 화면에 붙이지 않고 버린다(무음 오염 차단).
      if (!isCurrentTarget(runKey)) { setLoading(false); return; }
      setResult(core);
      setHistoryRefreshTick((t) => t + 1);
    } catch (e) {
      // 원시 개발자 문자열(Error:…·[object Object]) 노출 금지 — 통상어 안내(정직 표기).
      setError(e instanceof Error ? e.message : "종합분석 중 오류가 발생했습니다. 입력을 확인하고 다시 시도해 주세요.");
      setLoading(false);
      return;
    }
    setLoading(false);

    // ── 2단계: AI 해석 생성 후 병합(실패해도 1단계 결과 보존) ──
    // ★실측(2026-08-01 프로덕션): 해석 2종만으로 125초를 넘어 CF 524가 재현됐다(2/2). 동기
    //   응답으로는 해석을 전달할 방법이 없어 **제출·폴링 잡**으로 받는다.
    // ★두 응답 형태를 모두 수용한다 — 백엔드가 job_id를 주면 폴링, 결과를 바로 주면 그대로
    //   병합. 백엔드/프론트 배포 순서가 어긋나도 깨지지 않는다(구버전 백엔드=동기 응답).
    setInterpreting(true);
    try {
      // ★제출·폴링은 lib/interpretation-job.ts로 공용화했다 — 같은 API를 쓰는 프로젝트 AI
      //   인사이트 카드가 이 처리를 놓쳐 라이브에서 100% 실패하고 있었다(형제 소비처 미전파).
      const parts = await fetchInterpretation(core, {
        llmProvider: selectedProvider,
        llmModel: selectedModel,
      });
      // 해석은 1단계보다 더 오래 걸린다 — 그 사이 대상이 바뀌었으면 병합하지 않는다.
      if (!isCurrentTarget(runKey)) { setInterpreting(false); return; }
      setResult((prev) => (prev ? { ...prev, ...parts } : prev));
    } catch (e) {
      // ★해석 실패를 '분석 실패'로 승격하지 않는다 — setError를 쓰지 않고 해당 필드만 정직 표기.
      const reason = e instanceof Error ? e.message : "알 수 없는 오류";
      setResult((prev) => (prev ? {
        ...prev,
        ai_interpretation: null,
        ai_interpretation_status: { status: "unavailable", reason },
        market_interpretation: null,
        market_interpretation_status: { status: "unavailable", reason },
      } : prev));
    } finally {
      setInterpreting(false);
    }
  }, [address, selectedProvider, selectedModel, parcelRows, beginAnalysisRun, isCurrentTarget]);

  // 히스토리 변동감지 시그니처 파트 — 백엔드 계약과 동일 순서: [address, pnu||"", parcelCount, useLlm, options요약].
  //   parcelCount는 handleAnalyze가 실제 전송하는 parcelRows(2필지↑일 때만 전송)와 동일 출처.
  //   ★idx3(useLlm) 취약점(P3, R1 REVISE 검토됨): 백엔드는 build_signature_parts에
  //   use_llm=bool(llm_provider)(comprehensive_analysis_service.py)를 넘겨 저장하는데, 이 프론트는
  //   selectedProvider 상태값을 안 읽고 "true" 상수로 고정한다. selectedProvider 기본값이
  //   "anthropic"(항상 truthy)이라 실사용 경로에서 백엔드 bool(llm_provider)도 거의 항상 True로
  //   일치해 현재 무해하다(로직 변경 불요 — 사용자가 provider를 명시적으로 비우는 드문 경로만
  //   불일치, idx3 자체가 비교 대상이라 그 경우도 오탐 배너 최악의 경우일 뿐 데이터 손상은 없다).
  const historySignatureParts = useMemo(
    () => [result?.address ?? address, result?.pnu ?? "", String(parcelRows.length || 1), "true", optionsSummary(undefined)],
    [result?.address, result?.pnu, address, parcelRows.length],
  );

  const ef = result?.effective_far || {};
  const supplyAreas: SupplyAreaItem[] = result?.supply_areas || [];
  const landPrices = result?.land_prices || {};
  const transactions = result?.transaction_prices || {};
  const salePrices: AnalysisResult[] = result?.sale_prices || [];
  const location = result?.location || {};
  const devPlans = result?.development_plans || {};

  // ★자가검증(W3) — 1단계 분석 응답에 이미 실려 오므로 추가 호출이 없다.
  //   result 전체를 의존성으로 둔다(리졸버가 여러 하위 키를 함께 읽으므로 부분 의존은 stale).
  const auditView = useMemo(() => readFieldAudit(result), [result]);

  return (
    <div className="space-y-4">
      {/* 사통팔땅 전역 싱글 통합지도 워크스페이스 (대시보드와 100% 동일한 필지 입력 + 멀티지도 엔진).
          ★UX 트랙 B4: 착지 페이지라 기본 접힘(defaultCollapsed) — 요약 1줄+"지도 열기" 토글.
          ★UX 트랙 B2: 내부 ContextHeader 활성화(showContextHeader) — 프로젝트·주소·PNU·
          용도지역·대지면적 집계를 여기 한 곳으로 흡수. */}
      <SatongMapShellDynamic locale="ko" defaultCollapsed showContextHeader />
      {/* Header */}
      <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--surface-strong)] p-6">
        <h2 className="text-xl font-black text-[var(--text-primary)] mb-1">종합 부지분석 보고서</h2>
        <p className="text-xs text-[var(--text-secondary)] mb-4">주소를 입력하면 7개 카테고리 자동 분석 보고서를 생성합니다</p>
        {selectionNotice && (
          <p className="mb-3 rounded-xl border border-lime-400/40 bg-lime-400/10 px-3 py-2 text-xs font-bold text-lime-700">
            {selectionNotice}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)]/50 p-4">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">분석 대상 정보</span>
            <h3 className="text-sm font-black text-[var(--text-primary)] mt-0.5">
              {address ? (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="size-4 text-[var(--accent-strong)]" />
                  {address}
                  {parcels.length > 1 ? (
                    <span className="text-xs font-bold text-[var(--accent-strong)]">(외 {parcels.length - 1}필지 선택됨)</span>
                  ) : null}
                </span>
              ) : (
                <span className="text-[var(--text-hint)]">상단 통합 지도를 클릭하거나 검색하여 필지를 선택해 주세요.</span>
              )}
            </h3>
          </div>
          <div className="flex items-center gap-3">
            {/* ★UX 트랙 B R2(리뷰어 MEDIUM): 대지면적·용도 수치는 제거됐다 — 위 셸 내부
                sticky ContextHeader(showContextHeader)가 같은 effectiveLandAreaSqm SSOT를
                이미 상시 표시 중이라, 여기서 또 보이면 "어느 게 정본?" 혼란만 남긴다.
                "분석 대상 정보" 카드는 주소 + 분석 CTA만 남긴다(중복 수치만 제거, 카피는 보존). */}
            <button
              onClick={handleAnalyze}
              disabled={loading || !address.trim()}
              className="shrink-0 rounded-xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-all hover:brightness-110 disabled:opacity-50"
            >
              {loading ? "분석 중..." : "종합 분석 시작"}
            </button>
          </div>
        </div>
        {providers.length > 0 ? (
          <div className="flex gap-3 items-center mt-3">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[var(--text-hint)]">AI 모델</span>
              <select
                value={selectedProvider}
                onChange={(e) => {
                  setSelectedProvider(e.target.value);
                  const p = providers.find(pr => pr.provider === e.target.value);
                  if (p) setSelectedModel(p.default_model);
                }}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs text-[var(--text-primary)]"
              >
                {providers.map(p => (
                  <option key={p.provider} value={p.provider}>{p.name}</option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[var(--text-hint)]">모델</span>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-xs text-[var(--text-primary)]"
              >
                {providers.find(p => p.provider === selectedProvider)?.models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} {m.tier === "premium" ? "★" : m.tier === "economy" ? "⚡" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-[var(--text-hint)] mt-2">AI 해석: API 키 미설정 (규칙 기반 분석만 제공)</p>
        )}
      </div>

      {/* 입지 인프라(POI) 분석 — 주소 선택 시. 분석결과 있으면 context로 통합 입지점수 산출.
          ★W2-d: 종합분석 시작 시 autoRunToken이 올라 자동 조회된다(버튼 별도 클릭 불요). */}
      {address.trim() && (
        <SiteInfraPoiCard
          address={address}
          context={result ? (result as unknown as Record<string, unknown>) : undefined}
          autoRunToken={pipelineRunToken}
        />
      )}

      {/* 다필지(2필지↑) 통합 개발방식 분석 — 검색·엑셀로 등록 시 자동 노출.
          ★W2-d: 종합분석과 함께 자동 실행(파이프라인 편입). */}
      {/* ★parcelRows 를 함께 넘긴다 — 이 패널은 이미 면적을 갖고 있는데(위 /analysis/comprehensive
          전송용) 시나리오 카드에는 주소만 줘서, 백엔드가 면적을 재파생하다 미해석 필지를
          0㎡로 떨어뜨렸다(2026-08-19 실측). 같은 값을 두 소비처가 나눠 쓴다. */}
      {parcels.length > 1 && (
        <DevelopmentScenarioCard
          address={address}
          parcels={parcels}
          parcelRows={parcelRows}
          autoRunToken={pipelineRunToken}
        />
      )}

      {error && (
        <div className="rounded-xl bg-[var(--status-error)]/10 border border-[var(--status-error)]/30 p-4 text-sm text-[var(--status-error)]">{error}</div>
      )}

      {loading && (
        <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-8 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-3 border-[var(--accent-strong)] border-t-transparent mb-3" />
          {/* ★UX 트랙 C5(무날조 원칙): "약 5~10초"는 실측 근거가 없는 거짓 문구였다 — 이 요청은
              apiClient 기본 타임아웃(120초, lib/api-client.ts DEFAULT_TIMEOUT_MS)을 그대로 쓰므로
              실제로 최대 2분까지 걸릴 수 있다. 별도 timeoutMs override가 없어 그 상한을 그대로 반영. */}
          <p className="text-sm text-[var(--text-secondary)]">7개 카테고리 분석 중... (최대 2분 소요될 수 있습니다)</p>
          <div className="mt-3 flex items-center justify-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
            <p className="text-[11px] text-blue-400">AI 해석 생성 중...</p>
          </div>
        </div>
      )}

      {result && (
        <div className="space-y-3">
          {/* ★이전 분석 대비 변경 — 값 차이(detect_contradictions)를 **원인**(change_cause)으로
              분류해 렌더. 입력이 달라진 것/분석 방식이 개선된 것은 경고가 아니며, 입력·기준이
              같은데 값이 다른 경우(UNEXPLAINED)만 경고색으로 확인을 요청한다(ChangeCauseCard). */}
          <ChangeCauseCard contradictions={result.contradictions} />

          {/* 기본 정보 요약 */}
          <div className="rounded-2xl border border-[var(--accent-strong)]/20 bg-[var(--surface-strong)] p-5">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <Field label="주소" value={result.address || ""} />
              <Field label="PNU" value={result.pnu || "-"} />
              <Field label="용도지역" value={result.zone_type || "-"} />
              <Field label="대지면적" value={formatArea(result.land_area_sqm)} />
            </div>
          </div>

          {/* ★정합성 안내 배너 — 비연접 파편 필지(다필지 통합 불가) 경고 + 백엔드 warnings[](이미
              라이브였으나 미렌더였던 핸드오프 손실 해소). §2 "판정불가" 스텁과 동일 논조로
              페이지 전체 정직 표기 일관성을 맞춘다(가짜 통합수치를 그대로 믿지 않도록 상단에 배치). */}
          {(result.integrated_zoning?.adjacency_contiguous === false ||
            (Array.isArray(result.warnings) && result.warnings.length > 0)) && (
            <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-4 space-y-2">
              {result.integrated_zoning?.adjacency_contiguous === false && (
                <p className="text-xs font-bold leading-relaxed text-[var(--status-warning)]">
                  비연접 파편 필지
                  {typeof result.integrated_zoning?.cluster_count === "number"
                    ? ` ${result.integrated_zoning.cluster_count}개 클러스터`
                    : ""}
                  {" "}— 단일 대지 통합개발 불가. 아래 통합 수치는 참고용이며 클러스터별 분석이 필요합니다.
                </p>
              )}
              {Array.isArray(result.warnings) && result.warnings.length > 0 && (
                <ul className="space-y-1">
                  {(result.warnings as string[]).map((w, i) => (
                    <li key={i} className="text-[11px] text-[var(--text-secondary)]">· {w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* ★법정초과 가드(integrity_warnings) — 위 `warnings` 배너와 **다른 배열**이다.
              백엔드가 실효 건폐·용적·층수의 법정초과를 검출해 실어 보내는데 렌더가 없었다
              (2026-08-24 실측: 프론트 소비처 0). 값은 그대로 두고 사실만 알린다(무날조). */}
          <IntegrityWarnings items={result.integrity_warnings as never} className="mt-3" />

          {/* 시니어 전문가 자문 verdict(심의·도시계획·법무) — 백엔드 senior_consultation 소비 */}
          <SeniorVerdictCard
            consultation={(result as { senior_consultation?: SeniorConsultation }).senior_consultation}
            title="시니어 종합 자문(심의·도시계획·법무)"
          />

          {/* ★SpecialistAgent 결정론 교차검증(전수감사 #2) — 백엔드 result.specialists 소비.
              zoning 허용용도·far 실효검증·심의/설계(엔진 가용 시)를 동기 수집해 화면 반영.
              그간 .delay fire-and-forget로 결과 미반영이던 갭 해소. specialists 비면 미렌더(graceful). */}
          <DecisionSpecialistCard
            specialists={(result as { specialists?: DecisionSpecialist[] }).specialists}
          />

          {/* ★특이부지 게이트(학교·GB·맹지·농지 등) — 백엔드 special_parcel/developability 소비.
              표시 누락 시 '최대 연면적 가능' 오해 위험이므로 경고를 명시 렌더(orphan handoff 해소). */}
          {result.special_parcel?.is_special && (
            <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold text-[var(--status-warning)]">특이부지 제약 감지</span>
                {/* ★원시 코드(NEEDS_OFFICIAL_SURVEY 등)를 그대로 뿌리지 않는다 — 공용 라벨 SSOT를
                    경유한다. 이 맵은 이미 있었는데 이 경로만 안 타서 개발자용 코드가 화면에
                    노출되고 있었다(다른 화면들은 이미 라벨을 쓴다). 미등재 코드는 이름을
                    지어내지 않고 원문 + '설명 준비 중'으로 정직 표기한다. */}
                {(() => {
                  const dev = developabilityLabel(result.developability);
                  if (!dev.text) return null;
                  return (
                    <span
                      className="rounded-full border border-[var(--status-warning)]/40 px-2 py-0.5 text-[10px] font-semibold text-[var(--status-warning)]"
                      title={String(result.developability ?? "")}
                    >
                      {dev.text}
                      {!dev.known && " (설명 준비 중)"}
                    </span>
                  );
                })()}
              </div>
              {(result.special_parcel.honest_disclosure || result.special_parcel.development_caveat) && (
                <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-secondary)]">
                  {result.special_parcel.honest_disclosure || result.special_parcel.development_caveat}
                </p>
              )}
              {/* ★백엔드가 이미 주던 해결 절차·선행 요건·대안을 표면화(소비처 0건이던 고아 핸드오프).
                  문장은 전부 응답 필드에서 오며 프론트가 지어내지 않는다. */}
              <SpecialParcelActions factors={result.special_parcel.factors} />
            </div>
          )}

          {/* 경사도 미획득 등 개발행위 판단 근거 갭 — 특이부지 카드 옆에 붙인다.
              ★특이부지 카드와 독립 렌더: is_special이 아니어도 지적은 나올 수 있다. */}
          <FieldAuditNotice notes={findingsForSection(auditView, "special-parcel").notes} />

          {/* ★현행 허용건축물(별표2~20) — 백엔드 allowed_buildings 소비(orphan handoff 해소).
              스토리: "지금 지을 수 있는 것"을 먼저 보여준 다음, 그 아래 랭킹으로 사업성을 비교한다. */}
          <AllowedBuildingsCard data={result.allowed_buildings} floorCap={ef.floor_cap} />

          {/* ★건축가능항목 랭킹(Stage 1) — 백엔드 buildable_options 소비(orphan handoff 해소) */}
          <BuildableOptionsCard data={result.buildable_options} />
          {/* ★ai_interpretation.buildable_options_interpretation — 12해석키 중 미소비였던 마지막 1건(핸드오프 손실 해소) */}
          {result.ai_interpretation?.buildable_options_interpretation && (
            <AiInterpretation text={result.ai_interpretation.buildable_options_interpretation} />
          )}

          {/* ★종상향/종변경 잠재(예상치 — 현행과 분리) — 백엔드 upzoning 소비 */}
          {Array.isArray(result.upzoning_scenarios) && result.upzoning_scenarios.length > 0 && (
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold text-[var(--text-primary)]">종상향 잠재 시나리오</span>
                <span className="text-[10px] text-[var(--text-secondary)]">★예상치 — 현행 실효 용적률과 분리</span>
                {/* ★범위가 붕괴하면(min===max) 범위인 척하지 않는다.
                    실측: 자연녹지 서울은 세 경로가 모두 같은 목표(제1종일반주거)를 가리켜
                    `예상 상한 150.0~150.0%`가 찍혔다 — 개발사는 이것을 "그 위는 안 된다"로
                    읽지만, 실제 의미는 "우리가 한 경로만 봤다"이다. 판정과 고지 문구는
                    백엔드 계약(is_collapsed·honest_disclosure)에서 오고, 표기는
                    formatUpzoningFarRange 한 곳에서 결정한다(형제 화면과 같은 문구). */}
                {result.potential_far_range ? (
                  <>
                    <span className="text-xs font-semibold text-[var(--accent-strong)]">
                      {formatUpzoningFarRange(result.potential_far_range as UpzoningFarRange).collapsed
                        ? "예상"
                        : "예상 상한"}{" "}
                      <UpzoningFarRangeValue range={result.potential_far_range as UpzoningFarRange} />
                    </span>
                    <UpzoningFarRangeNotice
                      range={result.potential_far_range as UpzoningFarRange}
                      className="w-full text-[11px] leading-relaxed text-[var(--text-secondary)]"
                    />
                  </>
                ) : null}
              </div>
              <ul className="mt-2 space-y-1">
                {result.upzoning_scenarios.slice(0, 4).map((s: Record<string, any>, i: number) => (
                  <li key={i} className="text-[11px] text-[var(--text-secondary)]">
                    · {s.path} → {s.target_zone}
                    {s.expected_far_pct_high != null ? ` (예상 ${formatPercent(s.expected_far_pct_high)})` : ""}
                    {s.feasibility ? ` · 가능성 ${s.feasibility}` : ""}
                    {/* ★#700 의 upside 축을 이 화면에도 올린다 — 공용 UpzoningScenarioList 를
                        쓰는 화면(부지분석·설계감사)에만 있고 여기엔 없어서, "어떤 경로도 상한을
                        못 넘는다"는 오독이 이 패널에만 남아 있었다. 조건은 그 공용 컴포넌트와
                        **같은 조건**을 쓴다(숫자와 용도지역은 한 쌍 — 라벨 없이 숫자만 올리면 위법값). */}
                    {s.upside_far_pct_high != null && s.upside_far_zone
                      && s.upside_far_pct_high > (s.expected_far_pct_high ?? 0)
                      ? ` · 최대 ${s.upside_far_zone} 상향 시 ${formatPercent(s.upside_far_pct_high)}`
                      : ""}
                    {/* ★신규(additive) blocked_reasons — 비연접 등으로 구역 성립이 불확실한 사유(정직 표기). */}
                    {Array.isArray(s.blocked_reasons) && s.blocked_reasons.length > 0
                      ? ` · ${(s.blocked_reasons as string[]).join(" · ")}`
                      : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ★산출 근거·법령링크(EvidencePanel) — 백엔드 evidence/legal_refs 소비.
              '용적률 200% 왜 나왔나'의 법령 원문까지 표면화(근거 기본제공·할루시네이션 가드 전역원칙). */}
          <EvidencePanel
            items={adaptEvidence(result.evidence, result.legal_refs)}
            title="산출 근거·법령"
            defaultOpen={false}
          />

          {/* ★자가검증 요약(W3) — 근거 계열이 모인 자리에 붙인다. 개별 지적은 각 섹션 안에
              함께 표시되고, 여기서는 '어디까지 점검됐나'와 섹션에 못 붙은 지적을 맡는다. */}
          <CredibilitySummaryCard view={auditView} parcelCount={parcelRows.length} />

          {/* 출처·신선도 지적은 근거 섹션 소관 */}
          <FieldAuditNotice notes={findingsForSection(auditView, "evidence").notes} />

          {/* ★AI 해석 상태 고지(W2-c) — 결정론 분석은 이미 위에 다 있고 해석만 뒤따라온다.
              생성 중/실패를 명시하지 않으면 사용자는 "AI 분석이 원래 없는 화면"으로 오해한다.
              3상태(deferred=생성 중 / unavailable=실패 / ok=정상)를 구분해 표기한다. */}
          {!result.ai_interpretation?.overall_summary && (
            interpreting || result.ai_interpretation_status?.status === "deferred" ? (
              <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-4">
                <p className="text-xs font-semibold text-[var(--accent-strong)]">
                  AI 종합 해석을 생성하고 있습니다…
                </p>
                <p className="mt-1 text-[11px] text-[var(--text-hint)]">
                  위 분석 결과는 이미 완료되었습니다. 해석은 잠시 후 이 자리에 추가됩니다.
                </p>
              </div>
            ) : result.ai_interpretation_status?.status === "unavailable" ? (
              <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10 p-4">
                <p className="text-xs font-semibold text-[var(--text-primary)]">
                  AI 종합 해석을 생성하지 못했습니다
                </p>
                <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                  위 분석 결과는 정상적으로 산출되었습니다. 해석만 생성에 실패했으며, 다시
                  분석하면 재시도됩니다.
                  {result.ai_interpretation_status?.reason ? (
                    <span className="block mt-1 text-[10px] text-[var(--text-hint)]">
                      사유: {String(result.ai_interpretation_status.reason)}
                    </span>
                  ) : null}
                </p>
              </div>
            ) : null
          )}

          {/* AI 종합 요약 */}
          {result.ai_interpretation?.overall_summary && (
            <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-gradient-to-r from-[var(--accent-strong)]/5 to-transparent p-6">
              <h3 className="text-sm font-bold text-[var(--accent-strong)] mb-2">AI 종합 분석</h3>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
                {result.ai_interpretation.overall_summary}
              </p>
              {result.ai_interpretation.risk_factors && (
                <div className="mt-3 flex gap-4">
                  <div className="flex-1 rounded-lg bg-[var(--status-error)]/5 border border-[var(--status-error)]/20 p-3">
                    <p className="text-[10px] font-bold text-[var(--status-error)] mb-1">리스크 요인</p>
                    <p className="text-[10px] text-[var(--text-secondary)] whitespace-pre-line">{result.ai_interpretation.risk_factors}</p>
                  </div>
                  <div className="flex-1 rounded-lg bg-[var(--status-success)]/5 border border-[var(--status-success)]/20 p-3">
                    <p className="text-[10px] font-bold text-[var(--status-success)] mb-1">기회 요인</p>
                    <p className="text-[10px] text-[var(--text-secondary)] whitespace-pre-line">{result.ai_interpretation.opportunity_factors}</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* AI 시장분석 종합 해석 (market_interpretation) — market_interpretation이 빈 객체({})로만
              와도 헤더 셸이 남지 않도록 실제 내용(6개 하위텍스트 중 1개 이상) 보유 여부로 게이트한다.
              내용이 없고 market_interpretation_status.reason이 있으면 정직 미생성 사유 한 줄만 표기(무목업). */}
          {(() => {
            const mi = result.market_interpretation as AnalysisResult | undefined;
            const miFields = mi
              ? [mi.market_overview, mi.price_trend_analysis, mi.comparable_analysis, mi.investment_insight, mi.risk_factors, mi.timing_recommendation]
              : [];
            const hasMarketInterp = miFields.some((v) => typeof v === "string" && v.trim().length > 0);
            if (hasMarketInterp && mi) {
              return (
                <div className="rounded-2xl border border-[var(--status-success)]/25 bg-[var(--status-success)]/5 p-6">
                  <h3 className="mb-3 inline-flex items-center gap-1.5 text-sm font-bold text-[var(--status-success)]"><BarChart3 className="size-4" aria-hidden /> AI 시장분석</h3>
                  <div className="space-y-3">
                    {mi.market_overview && <MarketAiBlock label="시장 종합 현황" text={mi.market_overview} />}
                    {mi.price_trend_analysis && <MarketAiBlock label="가격 추이·전망" text={mi.price_trend_analysis} />}
                    {mi.comparable_analysis && <MarketAiBlock label="유사물건 비교" text={mi.comparable_analysis} />}
                    {mi.investment_insight && <MarketAiBlock label="투자 시사점" text={mi.investment_insight} />}
                    {mi.risk_factors && <MarketAiBlock label="시장 리스크" text={mi.risk_factors} />}
                    {mi.timing_recommendation && <MarketAiBlock label="매수·개발 타이밍" text={mi.timing_recommendation} />}
                  </div>
                </div>
              );
            }
            if (result.market_interpretation_status?.reason) {
              return (
                <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 text-xs text-[var(--text-hint)]">
                  시장분석 미생성 — 사유: {result.market_interpretation_status.reason}
                </p>
              );
            }
            return null;
          })()}

          {/* ★관점 선택 — 기본은 '전체'(중립)다. 고르면 그 관점이 먼저 봐야 할 순서로 재배치되고
              요약 한 줄이 붙는다. 같은 데이터를 다르게 계산하지 않는다(순서와 요약문만 바뀐다). */}
          <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-bold text-[var(--text-secondary)]">보는 관점</span>
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="보고서를 읽는 관점 선택">
                <button
                  type="button"
                  onClick={() => setPersona(null)}
                  aria-pressed={persona === null}
                  className={`rounded-full px-3 py-1 text-[11px] font-bold transition-colors ${
                    persona === null
                      ? "bg-[var(--accent-strong)] text-white"
                      : "bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:bg-[var(--line)]"
                  }`}
                >
                  전체
                </button>
                {PERSONAS.map((spec) => (
                  <button
                    key={spec.key}
                    type="button"
                    onClick={() => setPersona(spec.key)}
                    aria-pressed={persona === spec.key}
                    className={`rounded-full px-3 py-1 text-[11px] font-bold transition-colors ${
                      persona === spec.key
                        ? "bg-[var(--accent-strong)] text-white"
                        : "bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:bg-[var(--line)]"
                    }`}
                  >
                    {spec.label}
                  </button>
                ))}
              </div>
            </div>
            {personaSpec && (
              <div className="mt-3 space-y-2">
                <p className="text-xs text-[var(--text-primary)]">{personaSpec.summary}</p>
                {/* ★없는 것을 있다고 하지 않는다 — 관점 이름만 붙여놓고 그 관점의 핵심을 안 주면
                    사용자는 없는 것을 있다고 오해한다. 어디로 가야 하는지까지 적는다. */}
                {personaSpec.outOfScope && (
                  <p className="text-[10px] text-[var(--text-hint)]">
                    이 보고서 범위 밖: <span className="font-bold">{personaSpec.outOfScope.what}</span>
                    {" — "}{personaSpec.outOfScope.where}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* ★관점(페르소나)별 스토리라인 — 본문은 한 벌 그대로 두고 **순서만** 바꾼다.
              데이터 재계산 0·새 API 0. 순서 판정은 lib/analysis-persona.ts 한 곳(SSOT).
              ★DOM 순서를 실제로 바꾼다 — CSS order로 시각만 바꾸면 화면 읽기 순서와
              스크린리더 읽기 순서가 어긋난다(의미 있는 순서 위반). */}
          {(() => {
            const sectionNodes: Record<AnalysisSectionId, ReactNode> = {
              "effective-far": (
                <>
            {/* Section 1: 실효용적률 */}
            <SectionCard title="1. 실효용적률 산정" icon={BarChart3} defaultOpen={openFor("effective-far", true)}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <Field label="법정 건폐율 (국토계획법)" value={formatPercent(ef.national_bcr_pct)} />
                <Field label="법정 용적률 (국토계획법)" value={formatPercent(ef.national_far_pct)} />
                <Field label="조례 건폐율 (지자체)" value={formatPercent(ef.ordinance_bcr_pct)} />
                <Field label="조례 용적률 (지자체)" value={formatPercent(ef.ordinance_far_pct)} />
                <Field label="실효 건폐율" value={formatPercent(ef.effective_bcr_pct)} />
                <Field label="실효 용적률" value={formatPercent(ef.effective_far_pct)} />
              </div>
              {ef.source && <p className="text-[10px] text-[var(--text-hint)] mt-1">출처: {ef.source}</p>}
              {/* ★신규(additive) structural_cap_pct — 구조상한(층수 제한 등)이 조례 용적률보다
                  더 타이트하게 걸리는 경우를 명시(예: 4층 이하 제한 부지). 없으면 미표시(무목업). */}
              {ef.structural_cap_pct != null && (
                <div className="mt-3 rounded-lg border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/5 p-3">
                  <p className="text-[11px] font-bold text-[var(--status-warning)]">
                    구조상한 {formatPercent(ef.structural_cap_pct)}{ef.floor_cap != null ? ` · ${ef.floor_cap}층 이하` : ""}
                  </p>
                  {ef.floor_cap_basis && (
                    <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">근거: {ef.floor_cap_basis}</p>
                  )}
                </div>
              )}
              {Array.isArray(ef.annotations) && ef.annotations?.length > 0 && (
                <div className="mt-3 rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3 space-y-1.5">
                  <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">분석 근거</p>
                  {(ef.annotations ?? []).map((note: string, i: number) => (
                    <AnnotationLine key={i} text={note} />
                  ))}
                </div>
              )}
              {/* ★자가검증 지적은 AI 해석 문장보다 **위**에 둔다 — 아래에 두면 사용자가 AI 문장을
                  먼저 읽고, 그 문장이 점검을 통과한 것처럼 오해한다(AI 서술문은 점검 대상이 아니다). */}
              <FieldAuditNotice notes={findingsForSection(auditView, "effective-far").notes} />
              {result.ai_interpretation?.effective_far_interpretation && (
                <AiInterpretation text={result.ai_interpretation.effective_far_interpretation} />
              )}
            </SectionCard>

            {/* Section 1-B: 용적률 최적화 시뮬레이션 — 전 시나리오 cap 동일 시 요약+접기(FarOptimizationPanel) */}
            <FarOptimizationPanel farOpt={ef.far_optimization} structuralCapPct={ef.structural_cap_pct} />
                </>
              ),
              "supply-area": (
                <>
            {/* Section 2: 개발방식별 적정공급면적 */}
            <SectionCard title="2. 개발방식별 적정공급면적 산정" icon={Construction} defaultOpen={openFor("supply-area", true)}>
              {supplyAreas.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[var(--line)] text-[var(--text-hint)]">
                        <th className="py-2 px-2 text-left">개발유형</th>
                        <th className="py-2 px-1 text-right">전용율</th>
                        <th className="py-2 px-1 text-right">공급면적/세대</th>
                        <th className="py-2 px-1 text-right">연면적</th>
                        <th className="py-2 px-1 text-right">세대수</th>
                        <th className="py-2 px-1 text-right">층수</th>
                        <th className="py-2 px-1 text-right">주차</th>
                        <th className="py-2 px-1 text-right">공사비(추정)</th>
                        <th className="py-2 px-1 text-center">인허가</th>
                        <th className="py-2 px-1 text-center">적합성</th>
                      </tr>
                    </thead>
                    <tbody>
                      {supplyAreas.map((sa: SupplyAreaItem, i: number) => {
                        // ★F3(QA REQUEST CHANGES) 개발불가 게이트 정직 표기 — 백엔드가 공급규모를
                        //   산정하지 않은 항목(total_gfa_pyeong 미확보 + blocked_reason/note 보유,
                        //   P0-2/F1의 "판정불가" 스텁)은 undefined평·₩NaN 지표 행 대신 colSpan
                        //   전체 설명 행으로 사유를 표시한다(가짜 지표 은폐 금지).
                        const blockedText = sa.blocked_reason || sa.note;
                        const rowKey = sa.dev_type ?? `blocked-${i}`;
                        if (sa.total_gfa_pyeong == null && blockedText) {
                          return (
                            <tr key={rowKey} className="border-b border-[var(--line)]/50">
                              <td
                                colSpan={10}
                                className="py-3 px-3 text-xs leading-relaxed text-[var(--status-warning)] bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] rounded"
                              >
                                {sa.type_name ? `${sa.type_name} — ` : ""}{blockedText}
                              </td>
                            </tr>
                          );
                        }
                        return (
                        <tr key={rowKey} className={`border-b border-[var(--line)]/50 hover:bg-[var(--surface-soft)] transition-colors ${sa.feasibility_status === "부적합" ? "opacity-50" : ""}`}>
                          <td className="py-2.5 px-2 font-bold text-[var(--text-primary)]">{sa.type_name}</td>
                          <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{formatPercent(sa.exclusive_ratio_pct)}</td>
                          <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.supply_area_per_unit_pyeong}평</td>
                          <td className="py-2.5 px-1 text-right text-[var(--accent-strong)] font-bold">{sa.total_gfa_pyeong}평</td>
                          <td className="py-2.5 px-1 text-right text-[var(--text-primary)] font-bold">{sa.unit_count}</td>
                          <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.floor_count}층</td>
                          <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{sa.parking_count}대</td>
                          <td className="py-2.5 px-1 text-right text-[var(--text-secondary)]">{formatWon(sa.estimated_construction_cost_won)}</td>
                          <td className="py-2.5 px-1 text-center"><PermitBadge complexity={sa.permit_complexity} /></td>
                          <td className="py-2.5 px-1 text-center">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              sa.feasibility_status === "적합" ? "bg-[var(--status-success)]/20 text-[var(--status-success)]" :
                              sa.feasibility_status === "조건부" ? "bg-[var(--status-warning)]/20 text-[var(--status-warning)]" :
                              sa.feasibility_status === "부적합" ? "bg-[var(--status-error)]/20 text-[var(--status-error)]" :
                              "bg-gray-500/20 text-gray-400"
                            }`}>{sa.feasibility_status || "-"}</span>
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {/* 유형별 검증 상세 */}
                  {supplyAreas.filter((sa: AnalysisResult) => sa.conditions_met?.length > 0).length > 0 && (
                    <div className="mt-3 space-y-2">
                      <p className="text-[10px] font-bold text-[var(--text-hint)]">유형별 법적 조건 검증 상세</p>
                      {supplyAreas.map((sa: AnalysisResult) => {
                        const conditions = sa.conditions_met as AnalysisResult[] | undefined;
                        if (!conditions || conditions.length === 0) return null;
                        return (
                          <div key={sa.dev_type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                            <p className="text-[11px] font-bold text-[var(--text-primary)] mb-1">
                              {sa.type_name}
                              <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${
                                sa.feasibility_status === "적합" ? "bg-[var(--status-success)]/20 text-[var(--status-success)]" :
                                sa.feasibility_status === "부적합" ? "bg-[var(--status-error)]/20 text-[var(--status-error)]" :
                                "bg-[var(--status-warning)]/20 text-[var(--status-warning)]"
                              }`}>{sa.feasibility_status}</span>
                            </p>
                            <div className="space-y-0.5">
                              {conditions.map((c: AnalysisResult, i: number) => (
                                <p key={i} className="text-[10px] text-[var(--text-secondary)]">
                                  <span className={`inline-block w-3 h-3 mr-1 rounded-full text-center text-[8px] leading-3 font-bold ${
                                    c.status === "pass" ? "bg-[var(--status-success)]/20 text-[var(--status-success)]" :
                                    c.status === "fail" ? "bg-[var(--status-error)]/20 text-[var(--status-error)]" :
                                    c.status === "unknown" ? "bg-gray-500/20 text-gray-400" :
                                    "bg-[var(--status-warning)]/20 text-[var(--status-warning)]"
                                  }`}>{c.status === "pass" ? "O" : c.status === "fail" ? "X" : "?"}</span>
                                  <span className="font-medium">{c.rule}:</span> {c.detail}
                                </p>
                              ))}
                            </div>
                            {sa.recommendations?.length > 0 && (
                              <div className="mt-1 pt-1 border-t border-[var(--line)]">
                                {(sa.recommendations as string[]).map((r: string, i: number) => (
                                  <p key={i} className="text-[10px] text-[var(--accent-strong)]">→ {r}</p>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-hint)] italic">해당 용도지역에서 허용된 개발유형이 없습니다</p>
              )}
              {result.ai_interpretation?.supply_area_interpretation && (
                <AiInterpretation text={result.ai_interpretation.supply_area_interpretation} />
              )}
            </SectionCard>
                </>
              ),
              "land-price": (
                <>
            {/* Section 3: 토지 주변시세 */}
            <SectionCard title="3. 토지 주변시세" icon={Wallet} defaultOpen={openFor("land-price", false)}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {/* ★공시지가는 **기준연도와 한 쌍**으로 보여준다(2026-08-22).
                    연도가 화면에 없어서 `year=2025` 하드코딩으로 1년 낡은 값이 나가는 동안
                    아무도 눈치채지 못했다(#753). 값만 보이면 낡음이 보이지 않는다.
                    ★연도를 모르는 경로(land_register 폴백)면 **붙이지 않는다** —
                      모르는 연도를 지어내면 "최신"이라는 거짓 신호가 된다. */}
                <Field
                  label={landPrices.official_price_year
                    ? `공시지가 (${landPrices.official_price_year}년 · 원/m²)`
                    : "공시지가 (원/m²)"}
                  value={formatManWon(landPrices.official_price_per_sqm / 10000)}
                />
                <Field label="공시지가 총액" value={formatWon(landPrices.total_official_value_won)} />
                <Field label="추정 시세 (원/m²)" value={formatManWon(landPrices.estimated_market_per_sqm / 10000)} />
                <Field label="추정 시세 총액" value={formatWon(landPrices.total_estimated_value_won)} />
                <Field label="시세 보정계수" value={`×${landPrices.market_multiplier ?? "-"}`} />
              </div>
              <FieldAuditNotice notes={findingsForSection(auditView, "land-price").notes} />
              {result.ai_interpretation?.land_price_interpretation && (
                <AiInterpretation text={result.ai_interpretation.land_price_interpretation} />
              )}
            </SectionCard>
                </>
              ),
              "transactions": (
                <>
            {/* Section 4: 물건별 주변 실거래가 */}
            <SectionCard title="4. 물건별 주변 실거래가" icon={Home} defaultOpen={openFor("transactions", false)}>
              {Object.keys(transactions).length > 0 && !transactions.error ? (
                <div className="space-y-2">
                  {Object.entries(transactions).map(([type, data]) => {
                    const d = data as AnalysisResult;
                    if (!d || !d.count) return null;
                    return (
                      <div key={type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                        <p className="text-xs font-bold text-[var(--text-primary)] mb-1">
                          {type} ({d.count}건)
                          {d.excluded_outliers > 0 && (
                            <span className="ml-1 text-[10px] font-normal text-[var(--text-hint)]">· 이상치 {d.excluded_outliers}건 제외(지분·정정 등)</span>
                          )}
                        </p>
                        <div className="grid grid-cols-3 gap-2 text-[11px]">
                          <div><span className="text-[var(--text-hint)]">평균: </span><span className="font-bold">{formatManWon(d.avg_price_10k)}</span></div>
                          <div><span className="text-[var(--text-hint)]">최고: </span><span className="font-bold">{formatManWon(d.max_price_10k)}</span></div>
                          <div><span className="text-[var(--text-hint)]">최저: </span><span className="font-bold">{formatManWon(d.min_price_10k)}</span></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-hint)] italic">{transactions.error || transactions.message || "실거래 데이터 없음"}</p>
              )}
              {result.ai_interpretation?.transaction_interpretation && (
                <AiInterpretation text={result.ai_interpretation.transaction_interpretation} />
              )}
            </SectionCard>
                </>
              ),
              "sale-price": (
                <>
            {/* Section 5: 물건별 분양가 */}
            <SectionCard title="5. 개발유형별 예상 분양가" icon={Tag} defaultOpen={openFor("sale-price", false)}>
              {salePrices.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {salePrices.map((sp: AnalysisResult) => (
                    <div key={sp.dev_type} className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                      <p className="text-[10px] text-[var(--text-hint)]">{sp.type_name}</p>
                      <p className="text-sm font-bold text-[var(--accent-strong)]">{formatManWon(sp.sale_price_per_pyeong_man)}/평</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[var(--text-hint)] italic">분양가 데이터 없음</p>
              )}
              <FieldAuditNotice notes={findingsForSection(auditView, "sale-price").notes} />
              {result.ai_interpretation?.sale_price_interpretation && (
                <AiInterpretation text={result.ai_interpretation.sale_price_interpretation} />
              )}
            </SectionCard>
                </>
              ),
              "location": (
                <>
            {/* Section 6: 입지분석 */}
            <SectionCard title="6. 입지분석" icon={MapPin} defaultOpen={openFor("location", false)}>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <Field label="입지 점수" value={`${location.location_score ?? "-"}점 (${location.grade ?? "-"})`} />
                {location.transportation?.nearest_subway && (
                  <>
                    <Field label="최근접 지하철" value={location.transportation.nearest_subway.name || "-"} />
                    <Field label="지하철 거리" value={`${location.transportation.nearest_subway.distance_m ?? "-"}m`} />
                  </>
                )}
                <Field label="인근 학교" value={`${location.education?.school_count ?? 0}개교`} />
              </div>
              {/* ★입지 점수 산정 근거(score_breakdown) — 핸드오프 손실 해소(그간 location_score만 표시). */}
              {Array.isArray(location.score_breakdown) && location.score_breakdown.length > 0 && (
                <div className="mt-3 rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3 space-y-1">
                  <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">입지 점수 산정 근거</p>
                  {(location.score_breakdown as string[]).map((s: string, i: number) => (
                    <p key={i} className="text-[10px] text-[var(--text-secondary)]">· {s}</p>
                  ))}
                </div>
              )}
              <FieldAuditNotice notes={findingsForSection(auditView, "location").notes} />
              {result.ai_interpretation?.location_interpretation && (
                <AiInterpretation text={result.ai_interpretation.location_interpretation} />
              )}
            </SectionCard>
                </>
              ),
              "dev-plans": (
                <>
            {/* Section 7: 주변 개발계획 */}
            {(() => {
              // ★신규(additive) land_use_regulations_detail — {name, link|null}. 있으면 이름+링크로
              //   렌더(이름 중복 제거·순서 보존), 없으면 기존 land_use_regulations(문자열 배열)로 폴백.
              const rawDetail: AnalysisResult[] = Array.isArray(devPlans.land_use_regulations_detail)
                ? devPlans.land_use_regulations_detail
                : [];
              const seenNames = new Set<string>();
              const regDetail = rawDetail.filter((r) => {
                const n = (r?.name ?? "").trim();
                if (!n || seenNames.has(n)) return false;
                seenNames.add(n);
                return true;
              });
              const regItems: { name: string; link?: string | null }[] =
                regDetail.length > 0
                  ? regDetail.map((r) => ({ name: r.name, link: r.link ?? null }))
                  : (devPlans.land_use_regulations ?? []).map((name: string) => ({ name, link: null }));
              const specialDistricts: string[] = Array.isArray(devPlans.special_districts)
                ? devPlans.special_districts
                : [];
              const hasAnyRegInfo = regItems.length > 0 || specialDistricts.length > 0;

              return (
                <SectionCard title="7. 주변 개발계획 및 규제" icon={Map} defaultOpen={openFor("dev-plans", false)}>
                  {hasAnyRegInfo ? (
                    <div className="space-y-2">
                      {regItems.length > 0 && (
                        <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <p className="text-[10px] font-bold text-[var(--text-hint)]">토지이용계획 규제</p>
                            {/* ★risk_level(종합 리스크) — 핸드오프 손실 해소(그간 규제명 나열만 표시). */}
                            {devPlans.risk_level && (
                              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-bold ${riskLevelStyle(devPlans.risk_level as string)}`}>
                                종합 리스크 {devPlans.risk_level}
                              </span>
                            )}
                          </div>
                          <div className="space-y-1">
                            {regItems.map((reg, i) => {
                              // ★regulation_notes(이름별 해석 주석) — 매칭되면 회색 보조텍스트로 병기(핸드오프 손실 해소).
                              const note = (devPlans.regulation_notes as AnalysisResult[] | undefined)?.find(
                                (n: AnalysisResult) => n?.name === reg.name,
                              );
                              return (
                                <div key={i} className="flex flex-col gap-0.5">
                                  <div className="flex items-center gap-2 text-[11px]">
                                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--status-warning)] shrink-0" />
                                    <span className="text-[var(--text-primary)]">{reg.name}</span>
                                    {/* 근거 링크 — url 있을 때만(가짜 링크 날조 금지), 새 탭으로 열기. */}
                                    {reg.link ? (
                                      <a
                                        href={reg.link}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        title={`${reg.name} 근거 새 탭에서 열기`}
                                        aria-label={`${reg.name} 근거 새 탭에서 열기`}
                                        className="inline-flex items-center text-[var(--accent-strong)] hover:opacity-80"
                                      >
                                        <ExternalLink className="size-3" aria-hidden />
                                      </a>
                                    ) : null}
                                  </div>
                                  {note?.interpretation && (
                                    <p className="ml-3.5 text-[10px] text-[var(--text-hint)]">{note.interpretation}</p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                          {/* ★risk_factors(리스크 유발 규제 목록) — 핸드오프 손실 해소. */}
                          {Array.isArray(devPlans.risk_factors) && devPlans.risk_factors.length > 0 && (
                            <div className="mt-3 space-y-1 border-t border-[var(--line)] pt-2">
                              <p className="text-[10px] font-bold text-[var(--text-hint)] mb-1">리스크 요인</p>
                              {(devPlans.risk_factors as string[]).map((f: string, i: number) => (
                                <div key={i} className="flex items-center gap-2 text-[11px]">
                                  <span className="h-1.5 w-1.5 rounded-full bg-[var(--status-warning)] shrink-0" />
                                  <span className="text-[var(--text-secondary)]">{f}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                      {/* 특별·지구 지정 — devPlans.special_districts(그간 게이트 조건에만 쓰이고 미렌더였던 항목). */}
                      {specialDistricts.length > 0 && (
                        <div className="rounded-lg bg-[var(--surface-soft)] border border-[var(--line)] p-3">
                          <p className="mb-1 text-[10px] font-bold text-[var(--text-hint)]">특별·지구 지정</p>
                          <div className="space-y-1">
                            {specialDistricts.map((d, i) => (
                              <div key={i} className="flex items-center gap-2 text-[11px]">
                                <span className="h-1.5 w-1.5 rounded-full bg-purple-400 shrink-0" />
                                <span className="text-[var(--text-secondary)]">{d}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-[var(--text-hint)] italic">개발계획/규제 정보 없음</p>
                  )}
                  <FieldAuditNotice notes={findingsForSection(auditView, "dev-plans").notes} />
                  {result.ai_interpretation?.development_plan_interpretation && (
                    <AiInterpretation text={result.ai_interpretation.development_plan_interpretation} />
                  )}
                </SectionCard>
              );
            })()}
                </>
              ),
            };
            return sectionOrder.map((id) => (
              <Fragment key={`${persona ?? "neutral"}:${id}`}>{sectionNodes[id]}</Fragment>
            ));
          })()}

          {/* 분석 시간 */}
          <p className="text-[10px] text-[var(--text-hint)] text-right">분석 시간: {result.analyzed_at}</p>

          {/* 분석 히스토리 — 원장 조회(옵셔널 소비). 입력변동 감지 시 재분석 제안(자동실행 없음).
              배치=result 블록 최하단(evidence/ai_interpretation 등 전 섹션 뒤). */}
          <AnalysisHistoryCard
            analysisType="site_analysis"
            address={result.address ?? address}
            pnu={result.pnu ?? null}
            currentSignatureParts={historySignatureParts}
            onReanalyze={handleAnalyze}
            reanalyzing={loading}
            refreshSignal={historyRefreshTick}
          />
        </div>
      )}
    </div>
  );
}
