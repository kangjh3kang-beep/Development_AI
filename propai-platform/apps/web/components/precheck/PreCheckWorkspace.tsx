"use client";

/**
 * Flagship A — 90초 AI PreCheck 워크스페이스.
 *
 * 입력(주소+선택 면적) → 두 가지 즉시 진단을 호출/렌더:
 *  A. /precheck/instant     — 개발방식 신호등 그리드 + 법정한도 + 요약
 *  B. /precheck/zoning-signals — 조닝 기회 시그널(지도 + 카드)
 *
 * 디자인 토큰 사용(surface/line/text). 신호등은 의미색(emerald/amber/rose).
 * apiClient v1 POST(lib/api-client.ts) 패턴, Leaflet은 dynamic ssr:false.
 */

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { AlertTriangle } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { PRECHECK_HANDOFF_KEY, type PreCheckHandoff } from "./handoff";
import { NumberInput } from "@/components/common/NumberInput";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import {
  GlobalAddressSearch,
  type AddressAnalysisSummary,
  type AddressEntry,
} from "@/components/common/GlobalAddressSearch";
import { FieldSourceBadge } from "@/components/common/FieldSourceBadge";
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { BulkParcelBatchPanel } from "@/components/common/BulkParcelBatchPanel";
import { LegalRefChip } from "@/components/common/LegalRefChip";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import type {
  InstantPreCheckRequest,
  InstantPreCheckResponse,
  PreCheckFeasibilityBand,
  PreCheckMethod,
  PreCheckScenario,
  PreCheckSignal,
  ZoningSignal,
  ZoningSignalsRequest,
  ZoningSignalsResponse,
} from "./types";

const ZoningSignalMap = dynamic(
  () => import("./ZoningSignalMap").then((m) => m.ZoningSignalMap),
  { ssr: false, loading: () => <MapSkeleton /> },
);

function MapSkeleton() {
  return (
    <div className="flex h-[360px] w-full items-center justify-center rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] text-xs text-[var(--text-hint)]">
      지도 불러오는 중…
    </div>
  );
}

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

const LEVEL_CHIP: Record<string, string> = {
  high: "border-[var(--status-success)]/40 bg-[var(--status-success)]/15 text-[var(--status-success)]",
  mid: "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/15 text-[var(--status-warning)]",
  low: "border-[var(--line-strong)] bg-[var(--surface-strong)] text-[var(--text-tertiary)]",
};
const LEVEL_LABEL: Record<string, string> = { high: "높음", mid: "중간", low: "낮음" };

type TabKey = "instant" | "zoning";

export function PreCheckWorkspace() {
  const router = useRouter();
  const { locale } = useParams() as { locale: string };

  const [address, setAddress] = useState("");
  // 다필지: 엑셀 업로드/다중 검색으로 등록된 전체 필지 주소(통합 개발방식 분석에 사용)
  const [parcels, setParcels] = useState<string[]>([]);
  const [areaSqm, setAreaSqm] = useState<number | null>(null);
  // 면적 출처: 주소검색의 토지특성 자동반영(auto) vs 사용자 직접입력(user)
  const [areaSource, setAreaSource] = useState<"auto" | "user" | null>(null);
  const [useLlm, setUseLlm] = useState(false);

  // WP-D: onAnalyzed는 비동기(종합분석 응답) 도착이라 stale 클로저가 그 사이
  // 사용자가 직접 입력한 면적을 덮지 않도록 areaSource 최신값을 ref로 가드한다.
  const areaSourceRef = useRef<"auto" | "user" | null>(null);
  useEffect(() => {
    areaSourceRef.current = areaSource;
  }, [areaSource]);

  /** 주소검색 선택 → 주소·면적 자동입력 (사용자 수동값은 덮지 않음) */
  function handleAddressChange(entries: AddressEntry[]) {
    // 다필지: 등록된 전 필지 주소 목록 갱신(엑셀 업로드/다중 검색)
    const all = entries
      .map((e) => e.jibunAddress || e.fullAddress || e.roadAddress)
      .filter(Boolean);
    setParcels(all);
    const entry = entries[0];
    if (!entry) return;
    const picked = entry.jibunAddress || entry.fullAddress || entry.roadAddress;
    if (picked) setAddress(picked);
    // 면적: 검색이 토지특성에서 가져온 값이 있고, 사용자가 직접 입력한 적 없을 때만 자동 채움
    if (entry.areaSqm != null && entry.areaSqm > 0 && areaSource !== "user") {
      setAreaSqm(entry.areaSqm);
      setAreaSource("auto");
    }
  }

  /** 종합 토지분석 도착 → 면적 자동채움 — WP-D: store 비기록 모드에서 콜백 데이터로 기존 동작 유지 */
  function handleAnalyzed(analysis: AddressAnalysisSummary) {
    if (
      analysis.landAreaSqm != null &&
      analysis.landAreaSqm > 0 &&
      areaSourceRef.current !== "user"
    ) {
      setAreaSqm(analysis.landAreaSqm);
      setAreaSource("auto");
    }
  }

  const [tab, setTab] = useState<TabKey>("instant");

  const [instant, setInstant] = useState<InstantPreCheckResponse | null>(null);
  const [instantLoading, setInstantLoading] = useState(false);
  const [instantError, setInstantError] = useState("");

  const [zoning, setZoning] = useState<ZoningSignalsResponse | null>(null);
  const [zoningLoading, setZoningLoading] = useState(false);
  const [zoningError, setZoningError] = useState("");

  const canRun = address.trim().length > 0 && !instantLoading;

  function readError(e: unknown, fallback: string): string {
    if (e instanceof ApiClientError) {
      const p = e.payload as { message?: string; detail?: string } | null;
      return p?.message || p?.detail || `${fallback} (${e.status})`;
    }
    return fallback;
  }

  async function runInstant() {
    if (!address.trim()) return;
    setInstantLoading(true);
    setInstantError("");
    setInstant(null);
    const body: InstantPreCheckRequest = {
      address: address.trim(),
      area_sqm: areaSqm,
      use_llm: useLlm,
    };
    try {
      const res = await apiClient.post<InstantPreCheckResponse>("/precheck/instant", {
        body: body as unknown as Record<string, unknown>,
        useMock: false,
        timeoutMs: 90_000,
      });
      setInstant(res);
    } catch (e) {
      setInstantError(readError(e, "즉시 진단을 불러오지 못했습니다."));
    } finally {
      setInstantLoading(false);
    }
  }

  async function runZoning() {
    if (!address.trim()) return;
    setZoningLoading(true);
    setZoningError("");
    setZoning(null);
    const body: ZoningSignalsRequest = {
      address: address.trim(),
      pnu: instant?.pnu ?? null,
      radius_m: 300,
    };
    try {
      const res = await apiClient.post<ZoningSignalsResponse>("/precheck/zoning-signals", {
        body: body as unknown as Record<string, unknown>,
        useMock: false,
        timeoutMs: 90_000,
      });
      setZoning(res);
    } catch (e) {
      setZoningError(readError(e, "조닝 시그널을 불러오지 못했습니다."));
    } finally {
      setZoningLoading(false);
    }
  }

  async function runAll() {
    setTab("instant");
    // 두 진단 병렬 — 90초 SLA 내 동시 실행
    await Promise.allSettled([runInstant(), runZoning()]);
  }

  /** PreCheck 결과를 프로젝트 생성 화면으로 승계(sessionStorage 단일 출처 → projects/new 선채움). */
  function startProject(data: InstantPreCheckResponse) {
    const best = data.methods?.find((m) => m.code === data.summary?.best);
    const handoff: PreCheckHandoff = {
      address: data.address || address.trim(),
      zoneType: data.zone_type || null,
      areaSqm: data.area_sqm ?? areaSqm,
      pnu: data.pnu ?? null,
      bestMethod: data.summary?.best ?? null,
      bestMethodName: best?.name ?? null,
    };
    try {
      window.sessionStorage.setItem(PRECHECK_HANDOFF_KEY, JSON.stringify(handoff));
    } catch {
      /* sessionStorage 불가 시에도 이동은 진행(주소 미선채움 fallback) */
    }
    router.push(`/${locale}/projects/new`);
  }

  return (
    <div className="grid gap-6">
      {/* ── 입력 바 (커맨드센터) ── */}
      <section className="cc-bracketed relative overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
        <div className="cc-grid-bg opacity-40" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 mb-1 flex items-center gap-2">
          <span className="cc-meta">PRECHECK · 90s DIAGNOSIS</span>
          <span className="cc-live"><i />READY</span>
          <span className="rounded-lg border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
            90초 PreCheck
          </span>
          <h1 className="text-lg font-bold text-[var(--text-primary)]">90초 사업성 진단</h1>
        </div>
        <p className="mb-4 text-[13px] text-[var(--text-secondary)]">
          주소만 입력하면 용도지역을 판독해 개발방식별 인허가 신호등과 주변 조닝 기회 시그널을
          즉시 진단합니다.
        </p>
        <div className="grid gap-3 sm:grid-cols-[1fr_180px_auto]">
          <div className="grid gap-1">
            <label htmlFor="precheck-address" className="text-[11px] font-semibold text-[var(--text-tertiary)]">
              주소 <span className="text-[var(--status-error)]">*</span>
            </label>
            {/* 카카오 주소검색 — 선택 시 토지특성(면적 등) 자동입력 + 종합분석 백그라운드 트리거.
                WP-D: PreCheck는 탐색 도구(활성 프로젝트와 무관한 임의 주소 진단)이므로
                store 비기록(writeToContext=false) — 면적 자동채움은 onAnalyzed 콜백으로 유지. */}
            <GlobalAddressSearch
              writeToContext={false}
              onChange={handleAddressChange}
              onAnalyzed={handleAnalyzed}
              placeholder="예) 서울특별시 강남구 테헤란로 152 · 다필지는 엑셀로 일괄 등록"
            />
            {address && (
              <p className="truncate text-[11px] text-[var(--text-hint)]" title={address}>
                선택됨: {address}{parcels.length > 1 ? ` 외 ${parcels.length - 1}필지 (통합 분석)` : ""}
              </p>
            )}
          </div>
          <div className="grid gap-1">
            <label htmlFor="precheck-area" className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--text-tertiary)]">
              대지면적(㎡, 선택)
              {areaSource && <FieldSourceBadge source={areaSource === "user" ? "user" : "auto"} />}
            </label>
            <NumberInput
              id="precheck-area"
              value={areaSqm}
              onChange={(v) => {
                setAreaSqm(v);
                setAreaSource(v == null ? null : "user");
              }}
              allowDecimal
              placeholder="미입력 시 토지특성 자동"
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            />
          </div>
          <div className="flex items-end">
            <button
              type="button"
              onClick={() => void runAll()}
              disabled={!canRun}
              className="h-[42px] whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
            >
              {instantLoading || zoningLoading ? "진단 중…" : "90초 사업성 진단"}
            </button>
          </div>
        </div>
        <label className="mt-3 flex w-fit cursor-pointer items-center gap-2 text-[12px] text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={useLlm}
            onChange={(e) => setUseLlm(e.target.checked)}
            className="accent-[var(--accent-strong)]"
          />
          AI 한 줄 요약 포함(소폭 지연)
        </label>
      </section>

      {/* ── 다필지 통합 개발방식 분석 — 엑셀/다중검색으로 2필지 이상 등록 시 ── */}
      {parcels.length > 1 && (
        <DevelopmentScenarioCard address={address} parcels={parcels} />
      )}

      {/* ── 대량 구역 일괄 분석 — 수백~수천 필지(PNU 목록/구역 bbox) 비동기 배치 ── */}
      <BulkParcelBatchPanel />

      {/* ── 탭 ── */}
      {(instant || zoning || instantLoading || zoningLoading || instantError || zoningError) && (
        <div className="flex gap-2">
          {([
            { key: "instant", label: "개발방식 신호등" },
            { key: "zoning", label: "조닝 기회 시그널" },
          ] as { key: TabKey; label: string }[]).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`rounded-xl border px-4 py-2 text-[13px] font-semibold transition-colors ${
                tab === t.key
                  ? "border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                  : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      <AnimatePresence mode="wait">
        {tab === "instant" ? (
          <motion.div
            key="instant"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <InstantPanel
              loading={instantLoading}
              error={instantError}
              data={instant}
              onStartProject={startProject}
            />
          </motion.div>
        ) : (
          <motion.div
            key="zoning"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <ZoningPanel loading={zoningLoading} error={zoningError} data={zoning} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ════════════════════ A. 즉시 룰체크 패널 ════════════════════ */

function InstantPanel({
  loading,
  error,
  data,
  onStartProject,
}: {
  loading: boolean;
  error: string;
  data: InstantPreCheckResponse | null;
  onStartProject: (data: InstantPreCheckResponse) => void;
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

      {/* 프로젝트 생성 핸드오프 — 진단 결과를 그대로 승계해 사업화 여정으로 연결 */}
      <section className="flex flex-col gap-3 rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-bold text-[var(--text-primary)]">이 부지로 프로젝트를 시작할까요?</p>
          <p className="mt-0.5 text-[12px] text-[var(--text-secondary)]">
            진단한 주소{data.zone_type ? ` · ${data.zone_type}` : ""}
            {summary.best ? ` · 추천 ${bestName(methods, summary.best)}` : ""}을(를) 그대로 가져가
            프로젝트 생성으로 이어집니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => onStartProject(data)}
          className="h-[42px] shrink-0 whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-bold text-white shadow-[var(--shadow-glow)] transition-opacity hover:opacity-90"
        >
          이 부지로 프로젝트 시작 →
        </button>
      </section>

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

      {/* 최저/기본/최대 사업성 밴드 */}
      {data.feasibility_band && <FeasibilityBandSection band={data.feasibility_band} />}

      {/* 산출 근거 트레이스 */}
      {Array.isArray(data.evidence) && data.evidence.length > 0 && (
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

/* ════════════════════ B. 조닝 시그널 패널 ════════════════════ */

function ZoningPanel({
  loading,
  error,
  data,
}: {
  loading: boolean;
  error: string;
  data: ZoningSignalsResponse | null;
}) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-hint)]">
        주변 필지 인접성 + 조닝 기회 분석 중…
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

  if (!data.ok) {
    return (
      <div className="rounded-2xl border border-[var(--status-warning)]/40 bg-[var(--status-warning)]/[0.06] p-5 text-sm text-[var(--status-warning)]">
        {data.message || "조닝 시그널을 산출하지 못했습니다."}
      </div>
    );
  }

  const signals = data.signals ?? [];

  return (
    <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
      <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-bold text-[var(--text-primary)]">조닝 기회 지도</p>
          <span className="text-[11px] text-[var(--text-hint)]">
            대상: {data.target?.zone_type || "-"} · {data.target?.address || data.target?.pnu || ""}
          </span>
        </div>
        <ZoningSignalMap geojson={data.geojson} signals={signals} />
      </section>

      <section className="grid gap-3">
        <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">
          기회 시그널 ({signals.length})
        </p>
        {signals.length === 0 ? (
          <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm text-[var(--text-hint)]">
            {data.note || "주변 필지에서 유의미한 조닝 기회 시그널을 찾지 못했습니다."}
          </div>
        ) : (
          signals.map((sig, i) => <SignalCard key={`${sig.type}-${i}`} signal={sig} />)
        )}
        {!!data.sources?.length && (
          <p className="text-[11px] text-[var(--text-hint)]">출처: {data.sources.join(" · ")}</p>
        )}
      </section>
    </div>
  );
}

function SignalCard({ signal }: { signal: ZoningSignal }) {
  const levelChip = LEVEL_CHIP[signal.level] || LEVEL_CHIP.low;
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="rounded-md border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
          {signal.type}
        </span>
        <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold ${levelChip}`}>
          {LEVEL_LABEL[signal.level] || signal.level}
        </span>
        <span className="cc-num ml-auto text-sm font-extrabold text-[var(--text-primary)]">
          {Math.round(signal.score)}
          <span className="text-[11px] font-semibold text-[var(--text-hint)]">/100</span>
        </span>
      </div>
      {signal.rationale && (
        <p className="mb-2.5 text-[12px] leading-relaxed text-[var(--text-secondary)]">{signal.rationale}</p>
      )}
      {signal.parcels?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {(signal.parcels ?? []).map((p, i) => (
            <span
              key={`${p.pnu}-${i}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-[11px]"
              title={p.pnu}
            >
              <span
                className={`inline-block h-2 w-2 rounded-sm ${p.adjacent ? "bg-[var(--status-success)]" : "bg-[var(--text-hint)]"}`}
                aria-hidden="true"
              />
              <span className="font-semibold text-[var(--text-secondary)]">{p.zone_type || "용도미상"}</span>
              {p.adjacent && <span className="text-[var(--status-success)]">인접</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default PreCheckWorkspace;
