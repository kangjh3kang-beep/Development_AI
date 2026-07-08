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
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { PRECHECK_HANDOFF_KEY, type PreCheckHandoff } from "./handoff";
import { NumberInput } from "@/components/common/NumberInput";
import {
  GlobalAddressSearch,
  type AddressAnalysisSummary,
  type AddressEntry,
} from "@/components/common/GlobalAddressSearch";
import { FieldSourceBadge } from "@/components/common/FieldSourceBadge";
import { DevelopmentScenarioCard } from "@/components/common/DevelopmentScenarioCard";
import { BulkParcelBatchPanel } from "@/components/common/BulkParcelBatchPanel";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { PreCheckInstantPanel } from "./PreCheckInstantPanel";
import { readSatongMapSelection, satongSelectionAddresses } from "./satong-map-selection";
import type {
  InstantPreCheckRequest,
  InstantPreCheckResponse,
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

  useEffect(() => {
    const stored = readSatongMapSelection();
    if (!stored?.parcels.length) return;
    const nextAddresses = satongSelectionAddresses(stored.parcels);
    if (nextAddresses.length === 0) return;
    setAddress(nextAddresses[0]);
    setParcels(nextAddresses);
    const totalArea = stored.parcels.reduce((sum, parcel) => sum + (parcel.areaSqm ?? 0), 0);
    if (totalArea > 0 && areaSourceRef.current !== "user") {
      setAreaSqm(totalArea);
      setAreaSource("auto");
    }
  }, []);

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
    <div className="grid grid-cols-1 gap-6 min-w-0">
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
        <UseLlmToggle
          checked={useLlm}
          onChange={setUseLlm}
          label="AI 한 줄 요약 포함(소폭 지연)"
          hint=""
          className="mt-3 flex w-fit cursor-pointer items-center gap-2 text-[12px] text-[var(--text-secondary)]"
        />
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
            <PreCheckInstantPanel
              controlled
              ctaVariant="project"
              loading={instantLoading}
              error={instantError}
              data={instant}
              onStartAnalysis={startProject}
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
