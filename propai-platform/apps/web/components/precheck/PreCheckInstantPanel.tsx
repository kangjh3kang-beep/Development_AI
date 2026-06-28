"use client";

/**
 * PreCheckInstantPanel — 90초 즉시 진단(개발방식 신호등) 재사용 패널.
 *
 * PreCheckWorkspace의 instant 진단 부분만 떼어낸 재사용 컴포넌트다. 두 가지 모드로 동작한다:
 *
 *  1) 컨트롤드(렌더 전용) 모드 — `data`/`loading`/`error`를 부모가 넘겨주면 그 결과만 렌더한다.
 *     주소 입력바/버튼은 숨긴다(부모가 입력·호출을 소유). PreCheckWorkspace가 이 모드로 쓴다
 *     (기존 거동 100% 보존 — 추출은 순수 리팩토링).
 *
 *  2) 스탠드얼론 모드 — `data` 미전달 시 패널이 자체 주소입력 + "90초 진단" 버튼을 갖고
 *     POST /precheck/instant 를 직접 호출해 신호등을 그 자리에서 보여준다. 중앙분석센터(SiteCanvas)
 *     부지 미확정 진입에서 라우트 이동 없이 빠른진단을 흡수하는 용도.
 *
 * ★읽기전용 원칙: 이 패널 자체는 SSOT(store)에 절대 쓰지 않는다(진단은 정보제공일 뿐).
 *   실제 부지 확정(SSOT 커밋)은 `onStartAnalysis` 콜백을 받은 부모가 1회만 수행한다
 *   (임의 주소가 매 입력마다 store를 오염시키지 않게 — consume-once).
 *
 * 무목업: POST /precheck/instant 실엔드포인트만 사용. 실패 시 정직하게 에러를 표시한다.
 * 신호등은 의미색 토큰(emerald/amber/rose = status-success/warning/error)을 재사용한다.
 */

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { NumberInput } from "@/components/common/NumberInput";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import type {
  InstantPreCheckRequest,
  InstantPreCheckResponse,
  PreCheckFeasibilityBand,
  PreCheckMethod,
  PreCheckScenario,
  PreCheckSignal,
} from "./types";

/* ── 신호등 의미색(토큰 일관 팔레트) ── */
const SIGNAL_STYLE: Record<
  PreCheckSignal,
  { ring: string; chip: string; dot: string; label: string }
> = {
  pass: {
    ring: "border-[var(--status-success)]/40 bg-[var(--status-success)]/[0.06]",
    chip: "border-[var(--status-success)]/40 bg-[var(--status-success)]/15 text-[var(--status-success)]",
    dot: "bg-[var(--status-success)]",
    label: "가능",
  },
  warn: {
    ring: "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/[0.06]",
    chip: "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 text-[var(--status-warning)]",
    dot: "bg-[var(--status-warning)]",
    label: "심의/조건부",
  },
  fail: {
    ring: "border-[var(--status-error)]/40 bg-[var(--status-error)]/[0.06]",
    chip: "border-[var(--status-error)]/40 bg-[var(--status-error)]/15 text-[var(--status-error)]",
    dot: "bg-[var(--status-error)]",
    label: "불가",
  },
};

interface PreCheckInstantPanelProps {
  /** 스탠드얼론 모드 초기 주소(부지 미확정 진입에서 미리 채움). */
  initialAddress?: string;
  /**
   * 결과가 있을 때 노출되는 "이 부지로 분석 시작" CTA 콜백.
   * ★커밋은 부모가 1회만(SSOT 오염 방지) — 이 패널은 콜백 호출만 한다.
   * 미전달 시 CTA는 렌더하지 않는다(읽기 전용 진단으로만 사용).
   */
  onStartAnalysis?: (data: InstantPreCheckResponse) => void;
  /** 컴팩트(여백 축소) — 좁은 진입 영역(중앙분석센터 부지선택)용. */
  compact?: boolean;
  /**
   * CTA 문구 변형:
   *  - "analysis"(기본): "이 부지로 심층 분석을 시작할까요?" — 중앙분석센터 인라인 흡수용.
   *  - "project": "이 부지로 프로젝트를 시작할까요?" — PreCheckWorkspace 핸드오프(기존 거동 보존).
   */
  ctaVariant?: "analysis" | "project";
  /**
   * 컨트롤드(렌더 전용) 모드 — 부모가 진단 결과/로딩/에러를 직접 넘긴다.
   * 셋 중 하나라도 의미값이 있으면(또는 controlled=true) 자체 입력바를 숨기고 부모 데이터만 렌더한다.
   * PreCheckWorkspace가 기존 거동 보존을 위해 이 모드로 사용한다.
   */
  data?: InstantPreCheckResponse | null;
  loading?: boolean;
  error?: string;
  /** 명시적 컨트롤드 플래그(data가 아직 null인 로딩/에러 단계 구분용). */
  controlled?: boolean;
}

export function PreCheckInstantPanel({
  initialAddress,
  onStartAnalysis,
  compact = false,
  data: controlledData,
  loading: controlledLoading,
  error: controlledError,
  controlled = false,
  ctaVariant = "analysis",
}: PreCheckInstantPanelProps) {
  const isControlled =
    controlled ||
    controlledData != null ||
    controlledLoading != null ||
    controlledError != null;

  // 스탠드얼론 모드 자체 상태(컨트롤드면 미사용).
  const [address, setAddress] = useState(initialAddress ?? "");
  const [areaSqm, setAreaSqm] = useState<number | null>(null);
  const [localData, setLocalData] = useState<InstantPreCheckResponse | null>(null);
  const [localLoading, setLocalLoading] = useState(false);
  const [localError, setLocalError] = useState("");

  const data = isControlled ? (controlledData ?? null) : localData;
  const loading = isControlled ? !!controlledLoading : localLoading;
  const error = isControlled ? (controlledError ?? "") : localError;

  const canRun = address.trim().length > 0 && !localLoading;

  function readError(e: unknown, fallback: string): string {
    if (e instanceof ApiClientError) {
      const p = e.payload as { message?: string; detail?: string } | null;
      return p?.message || p?.detail || `${fallback} (${e.status})`;
    }
    return fallback;
  }

  // 스탠드얼론 모드: POST /precheck/instant 직접 호출(실엔드포인트만 · 가짜신호 0).
  async function runInstant() {
    if (!address.trim()) return;
    setLocalLoading(true);
    setLocalError("");
    setLocalData(null);
    const body: InstantPreCheckRequest = {
      address: address.trim(),
      area_sqm: areaSqm,
      use_llm: false,
    };
    try {
      const res = await apiClient.post<InstantPreCheckResponse>("/precheck/instant", {
        body: body as unknown as Record<string, unknown>,
        useMock: false,
        timeoutMs: 90_000,
      });
      setLocalData(res);
    } catch (e) {
      setLocalError(readError(e, "즉시 진단을 불러오지 못했습니다."));
    } finally {
      setLocalLoading(false);
    }
  }

  return (
    <div className="grid gap-4 min-w-0">
      {/* 스탠드얼론 입력바 — 컨트롤드 모드에선 부모가 입력을 소유하므로 숨긴다. */}
      {!isControlled && (
        <div className="grid gap-2 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          <div className={`grid gap-2 sm:grid-cols-[1fr_150px_auto]`}>
            <div className="grid gap-1">
              <label htmlFor="precheck-inline-address" className="text-[11px] font-semibold text-[var(--text-tertiary)]">
                주소 <span className="text-[var(--status-error)]">*</span>
              </label>
              <input
                id="precheck-inline-address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canRun) void runInstant();
                }}
                placeholder="예) 서울특별시 강남구 테헤란로 152"
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
            </div>
            <div className="grid gap-1">
              <label htmlFor="precheck-inline-area" className="text-[11px] font-semibold text-[var(--text-tertiary)]">
                대지면적(㎡, 선택)
              </label>
              <NumberInput
                id="precheck-inline-area"
                value={areaSqm}
                onChange={(v) => setAreaSqm(v)}
                allowDecimal
                placeholder="미입력 시 자동"
                className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
            </div>
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => void runInstant()}
                disabled={!canRun}
                className="h-[42px] whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
              >
                {localLoading ? "진단 중…" : "90초 진단"}
              </button>
            </div>
          </div>
          <p className="text-[11px] text-[var(--text-hint)]">
            주소만 입력하면 용도지역을 판독해 개발방식별 인허가 신호등을 즉시 진단합니다(라우트 이동 없음).
          </p>
        </div>
      )}

      {/* 진단 결과 렌더(컨트롤드/스탠드얼론 공통). */}
      <InstantResult
        loading={loading}
        error={error}
        data={data}
        compact={compact}
        onStartAnalysis={onStartAnalysis}
        ctaVariant={ctaVariant}
      />
    </div>
  );
}

/* ════════════════════ 즉시 진단 결과 렌더 ════════════════════ */

function InstantResult({
  loading,
  error,
  data,
  compact,
  onStartAnalysis,
  ctaVariant,
}: {
  loading: boolean;
  error: string;
  data: InstantPreCheckResponse | null;
  compact: boolean;
  onStartAnalysis?: (data: InstantPreCheckResponse) => void;
  ctaVariant: "analysis" | "project";
}) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-hint)]">
        용도지역 판독 + 개발방식 인허가 룰체크 중…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-[var(--status-error)]/40 bg-[var(--status-error)]/[0.06] p-5 text-sm text-[var(--status-error)]">
        {error}
      </div>
    );
  }
  if (!data) return null;

  // 빈/오류 경로: 용도지역 미확인
  if (!data.ok) {
    return (
      <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/[0.06] p-5 text-sm text-[var(--status-warning)]">
        {data.message || "용도지역을 확인하지 못했습니다. 주소(지번)를 다시 확인해 주세요."}
      </div>
    );
  }

  const { summary, legal_limits, methods } = data;

  return (
    <div className="grid gap-5">
      {/* 요약 바 */}
      <section className="grid gap-4 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 sm:grid-cols-[auto_1fr]">
        <div className="grid grid-cols-3 gap-3">
          <SummaryStat label="가능" value={summary.pass} tone="emerald" />
          <SummaryStat label="심의" value={summary.warn} tone="amber" />
          <SummaryStat label="불가" value={summary.fail} tone="rose" />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[var(--line)] pt-3 text-[13px] sm:border-l sm:border-t-0 sm:pl-5 sm:pt-0">
          <Meta label="용도지역" value={data.zone_type || "-"} />
          {data.area_sqm != null && (
            <Meta label="대지면적" value={`${Math.round(data.area_sqm).toLocaleString()}㎡`} />
          )}
          <Meta label="추천 개발방식" value={bestName(methods, summary.best)} accent />
          <Meta label="소요" value={`${data.elapsed_ms.toLocaleString()}ms`} />
        </div>
      </section>

      {/* ★"이 부지로 ..." CTA — onStartAnalysis가 있을 때만(부모가 SSOT 커밋/핸드오프를 1회 수행).
          ctaVariant로 문구만 분기한다: project=프로젝트 생성 핸드오프(PreCheckWorkspace 기존 거동 보존),
          analysis=중앙분석센터 인라인 흡수(심층 분석으로 이어짐). */}
      {onStartAnalysis && (
        <section className="flex flex-col gap-3 rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-bold text-[var(--text-primary)]">
              {ctaVariant === "project"
                ? "이 부지로 프로젝트를 시작할까요?"
                : "이 부지로 심층 분석을 시작할까요?"}
            </p>
            <p className="mt-0.5 text-[12px] text-[var(--text-secondary)]">
              진단한 주소{data.zone_type ? ` · ${data.zone_type}` : ""}
              {summary.best ? ` · 추천 ${bestName(methods, summary.best)}` : ""}을(를) 그대로 가져가
              {ctaVariant === "project" ? " 프로젝트 생성으로 이어집니다." : " 중앙분석센터의 통합 분석으로 이어집니다."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onStartAnalysis(data)}
            className="h-[42px] shrink-0 whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-opacity hover:opacity-90"
          >
            {ctaVariant === "project" ? "이 부지로 프로젝트 시작 →" : "이 부지로 분석 시작 →"}
          </button>
        </section>
      )}

      {/* 법정 한도 */}
      <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
          법정 한도 · {legal_limits.source || "출처 미상"}
        </p>
        <div className="flex flex-wrap gap-2">
          <LimitChip label="건폐율" value={legal_limits.bcr_pct} suffix="%" />
          <LimitChip label="용적률" value={legal_limits.far_pct} suffix="%" />
          <LimitChip label="높이" value={legal_limits.height_m} suffix="m" />
        </div>
        {/* 법령 원문링크 — 백엔드 레지스트리(law.go.kr 검증 딥링크) 출력만 렌더 */}
        {Array.isArray(data.legal_refs) && data.legal_refs.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--line)] pt-3">
            <span className="mr-1 self-center text-[11px] font-semibold text-[var(--text-tertiary)]">법적 근거</span>
            {data.legal_refs.map((ref) => (
              <LegalRefChip
                key={ref.key}
                lawName={ref.law_name}
                article={ref.article}
                title={ref.title}
                url={ref.url}
              />
            ))}
          </div>
        )}
      </section>

      {/* 최저/기본/최대 사업성 밴드 — 컴팩트 모드(좁은 진입)에선 생략(요약만 노출). */}
      {!compact && data.feasibility_band && <FeasibilityBandSection band={data.feasibility_band} />}

      {/* 산출 근거 트레이스 */}
      {!compact && Array.isArray(data.evidence) && data.evidence.length > 0 && (
        <EvidencePanel
          title="산출 근거"
          defaultOpen={false}
          items={data.evidence.map((ev): EvidenceItem => {
            const ref = ev.legal_ref_key
              ? data.legal_refs?.find((r) => r.key === ev.legal_ref_key)
              : undefined;
            return {
              label: ev.label,
              value: ev.value ?? "-",
              basis: ev.basis,
              legalRef: ref
                ? { lawName: ref.law_name, article: ref.article, title: ref.title, url: ref.url }
                : null,
            };
          })}
        />
      )}

      {/* 데이터 품질·검증 표기 */}
      {data.data_quality && (
        <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
              데이터 품질 · 검증
            </p>
            {data.data_quality.confidence_level && (
              <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold ${
                data.data_quality.confidence_level === "high"
                  ? "border-[var(--status-success)]/40 bg-[var(--status-success)]/15 text-[var(--status-success)]"
                  : data.data_quality.confidence_level === "low"
                    ? "border-[var(--status-error)]/40 bg-[var(--status-error)]/15 text-[var(--status-error)]"
                    : "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 text-[var(--status-warning)]"
              }`}>
                신뢰도 {data.data_quality.confidence_level === "high" ? "높음" : data.data_quality.confidence_level === "low" ? "낮음" : "보통"}
              </span>
            )}
            {data.data_quality.quantitative_reliable === false && (
              <span className="rounded-full border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 px-2 py-0.5 text-[11px] font-bold text-[var(--status-warning)]">
                필지 미확정 — 정량 수치 참고용
              </span>
            )}
          </div>
          {Array.isArray(data.data_quality.warnings) && data.data_quality.warnings.length > 0 && (
            <ul className="grid gap-1 text-[12px] text-[var(--text-secondary)]">
              {data.data_quality.warnings.map((w, i) => (
                <li key={i} className="flex items-center gap-1.5">
                  <AlertTriangle className="size-3.5 shrink-0 text-[var(--status-warning)]" aria-hidden />
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* LLM 요약 */}
      {summary.llm_note && (
        <div className="rounded-2xl border border-[var(--accent-strong)]/25 bg-[var(--accent-soft)] p-4 text-[13px] text-[var(--text-primary)]">
          <span className="mr-2 font-bold text-[var(--accent-strong)]">AI 요약</span>
          {summary.llm_note}
        </div>
      )}

      {/* 신호등 그리드 */}
      <section>
        <p className="mb-3 text-[11px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
          개발방식 인허가 신호등 ({methods.length})
        </p>
        {methods.length === 0 ? (
          <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm text-[var(--text-hint)]">
            해당 용도지역의 후보 개발방식이 없습니다.
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {methods.map((m) => (
              <MethodCard key={m.code} method={m} isBest={m.code === summary.best} />
            ))}
          </div>
        )}
      </section>

      {!!data.sources?.length && (
        <p className="text-[11px] text-[var(--text-hint)]">출처: {data.sources.join(" · ")}</p>
      )}
    </div>
  );
}

/* ── 최저/기본/최대 사업성 밴드 — 검증된 수지엔진 3점 산출 렌더 ── */

const SCENARIO_META: { key: "min" | "base" | "max"; label: string; tone: string }[] = [
  { key: "min", label: "최저(보수)", tone: "border-[var(--status-error)]/30" },
  { key: "base", label: "기본", tone: "border-[var(--accent-strong)]/40" },
  { key: "max", label: "최대(낙관)", tone: "border-[var(--status-success)]/30" },
];

function fmtEok(won?: number | null): string {
  if (won == null) return "-";
  const eok = won / 100_000_000;
  return `${eok >= 0 ? "" : "-"}${Math.abs(eok) >= 100 ? Math.round(Math.abs(eok)).toLocaleString() : Math.abs(eok).toFixed(1)}억`;
}

function describeAssumptions(a?: Record<string, number | string>): string {
  if (!a) return "";
  const parts: string[] = [];
  if (typeof a.sale_price_delta_pct === "number" && a.sale_price_delta_pct !== 0) {
    parts.push(`분양가 ${a.sale_price_delta_pct > 0 ? "+" : ""}${a.sale_price_delta_pct}%`);
  }
  if (typeof a.construction_cost_delta_pct === "number" && a.construction_cost_delta_pct !== 0) {
    parts.push(`공사비 ${a.construction_cost_delta_pct > 0 ? "+" : ""}${a.construction_cost_delta_pct}%`);
  }
  if (typeof a.sale_ratio === "number") parts.push(`분양률 ${(a.sale_ratio * 100).toFixed(0)}%`);
  return parts.join(" · ");
}

function ScenarioCard({ label, tone, s }: { label: string; tone: string; s?: PreCheckScenario }) {
  if (!s) return null;
  return (
    <div className={`grid gap-1 rounded-xl border ${tone} bg-[var(--surface-strong)] p-3`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold text-[var(--text-tertiary)]">{label}</span>
        {s.grade && (
          <span className="rounded-full border border-[var(--line)] px-1.5 py-0.5 text-[11px] font-bold text-[var(--text-primary)]">
            {s.grade}등급
          </span>
        )}
      </div>
      <p className="text-base font-bold text-[var(--text-primary)]">{fmtEok(s.npv_won)}</p>
      <p className="text-[12px] text-[var(--text-secondary)]">
        이익률 {s.profit_rate_pct != null ? `${s.profit_rate_pct.toFixed(1)}%` : "-"}
        {s.roi_pct != null ? ` · ROI ${s.roi_pct.toFixed(1)}%` : ""}
      </p>
      {describeAssumptions(s.assumptions) && (
        <p className="text-[11px] text-[var(--text-hint)]" title="시나리오 가정">
          {describeAssumptions(s.assumptions)}
        </p>
      )}
    </div>
  );
}

function FeasibilityBandSection({ band }: { band: PreCheckFeasibilityBand }) {
  const { scenarios } = band;
  if (!scenarios?.base && !scenarios?.min && !scenarios?.max) return null;
  return (
    <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
          사업성 밴드 (최저·기본·최대)
        </p>
        <span className="rounded-full border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
          {band.method_name}
        </span>
        <span className="text-[11px] text-[var(--text-hint)]">검증된 수지엔진 3점 산출 · 약식</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {SCENARIO_META.map(({ key, label, tone }) => (
          <ScenarioCard key={key} label={label} tone={tone} s={scenarios[key]} />
        ))}
      </div>
      {band.note && <p className="mt-2 text-[11px] text-[var(--text-hint)]">{band.note}</p>}
    </section>
  );
}

function bestName(methods: PreCheckMethod[], best: string | null): string {
  if (!best) return "-";
  const m = methods.find((x) => x.code === best);
  return m ? `${m.name} (${m.code})` : best;
}

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "emerald" | "amber" | "rose";
}) {
  const color =
    tone === "emerald" ? "text-[var(--status-success)]" : tone === "amber" ? "text-[var(--status-warning)]" : "text-[var(--status-error)]";
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-center">
      <AnimatedCounter value={value} className={`cc-num block text-2xl font-extrabold ${color}`} />
      <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">{label}</span>
    </div>
  );
}

function Meta({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">{label}</span>
      <span className={`font-bold ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>
        {value}
      </span>
    </span>
  );
}

function LimitChip({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | null;
  suffix: string;
}) {
  return (
    <span className="inline-flex items-baseline gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-1.5">
      <span className="text-[11px] font-semibold text-[var(--text-tertiary)]">{label}</span>
      <span className="cc-num text-sm font-bold text-[var(--text-primary)]">
        {value != null ? `${value.toLocaleString()}${suffix}` : "—"}
      </span>
    </span>
  );
}

function MethodCard({ method, isBest }: { method: PreCheckMethod; isBest: boolean }) {
  const s = SIGNAL_STYLE[method.signal];
  return (
    <div className={`relative rounded-2xl border p-4 ${s.ring}`}>
      {isBest && (
        <span className="absolute right-3 top-3 rounded-md border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">
          추천
        </span>
      )}
      <div className="mb-2 flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${s.dot}`} aria-hidden="true" />
        <span className="text-[11px] font-bold text-[var(--text-tertiary)]">{method.code}</span>
        <span className="text-sm font-bold text-[var(--text-primary)]">{method.name}</span>
      </div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${s.chip}`}>{s.label}</span>
        <span className="rounded-md border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          복잡도 {method.complexity}/5 · {method.complexity_label}
        </span>
      </div>
      {method.reason && (
        <p className="mb-2.5 text-[12px] leading-relaxed text-[var(--text-secondary)]">{method.reason}</p>
      )}
      {method.checks?.length > 0 && (
        <ul className="grid gap-1">
          {(method.checks ?? []).map((c, i) => {
            const cs = SIGNAL_STYLE[c.status];
            return (
              <li key={`${c.rule}-${i}`} className="flex items-start gap-2 text-[12px]">
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${cs.dot}`} aria-hidden="true" />
                <span className="font-semibold text-[var(--text-secondary)]">{c.rule}</span>
                <span className="text-[var(--text-hint)]">{c.detail}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default PreCheckInstantPanel;
