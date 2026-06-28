"use client";

/**
 * 다필지 통합 — 지도 중심 통합분석 화면(실데이터·한국어). 기존 뉴욕 영어 목업 전면 교체.
 *
 * 좌: 실 ParcelBoundaryMap(VWorld 연속지적도 정본 + Kakao 지적편집도 '용도지역 색면'=토지이음 동일 출처).
 * 우: /zoning/integrated-analysis 실데이터 — 통합 핵심지표·인접성·통합 시나리오·필지별 내역.
 * SSOT(useProjectContextStore) 단일 소비. 무목업: 미확보·degrade는 정직 표기(가짜값 금지). 무과금(use_llm=false).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Map as MapIcon, Layers, Building2, Link2, Scissors, HelpCircle, AlertTriangle,
  CheckCircle2, RefreshCw, ArrowRight, ListTree, Lightbulb, ExternalLink, MousePointerClick, ChevronDown,
} from "lucide-react";
import { dynamicMap } from "@/components/common/MapShell";
import type { ParcelBoundaryMap as ParcelBoundaryMapType } from "@/components/map/ParcelBoundaryMap";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { apiClient } from "@/lib/api-client";
import { GlobalAddressSearch } from "@/components/common/GlobalAddressSearch";
import { ParcelExportButton } from "@/components/projects/ParcelExportButton";

const ParcelBoundaryMap = dynamicMap<React.ComponentProps<typeof ParcelBoundaryMapType>>(
  () => import("@/components/map/ParcelBoundaryMap"),
  { pick: "ParcelBoundaryMap", height: 560, loadingMessage: "구획도 로딩…" },
);

const PYEONG = 3.305785;

type Integrated = {
  total_area_sqm?: number | null;
  blended_bcr_eff_pct?: number | null;
  blended_far_eff_pct?: number | null;
  blended_bcr_legal_pct?: number | null;
  blended_far_legal_pct?: number | null;
  far_basis_note?: string | null;
  integrated_gfa_sqm?: number | null;
  gfa_basis?: string | null;
};
type PerParcel = {
  pnu?: string | null; address?: string | null; area_sqm?: number | null;
  zone_type?: string | null; land_category?: string | null;
  bcr_eff_pct?: number | null; far_eff_pct?: number | null;
  special_parcel?: { developability?: string | null; label?: string | null } | null;
  status?: string | null; reason?: string | null;
};
type Scenario = {
  status?: string; disclosure?: string;
  recommendations?: unknown[];
  top3?: Record<string, unknown> | null;
};
type IntegratedResp = {
  parcel_count?: number; special_count?: number;
  zone_mix?: string[]; dominant_zone?: string | null;
  integrated?: Integrated | null;
  adjacency?: { contiguous?: boolean | null; note?: string | null } | null;
  developability?: string | null; resolvable?: string | null; honest_disclosure?: string | null;
  scenario?: Scenario | null;
  per_parcel?: PerParcel[];
  warnings?: string[];
};

const num = (v: number | null | undefined, suffix = ""): string =>
  v == null ? "—" : `${Math.round(v).toLocaleString()}${suffix}`;
const pct = (v: number | null | undefined): string => (v == null ? "—" : `${v}%`);

// 개발가능성 게이트 → 한국어 라벨·색.
function devLabel(d?: string | null): { text: string; tone: "ok" | "warn" | "bad" } {
  switch ((d || "").toUpperCase()) {
    case "POSSIBLE": return { text: "개발 가능", tone: "ok" };
    case "CONDITIONAL": case "PRECONDITION": return { text: "조건부(선행절차)", tone: "warn" };
    case "BLOCKED": return { text: "개발 제약", tone: "bad" };
    default: return { text: d || "미상", tone: "warn" };
  }
}
// 시나리오 상태 → 한국어 라벨·색.
function scnLabel(s?: string): { text: string; tone: "ok" | "warn" | "bad" } {
  switch (s) {
    case "computed": return { text: "확정", tone: "ok" };
    case "tentative": return { text: "잠정(확정 아님)", tone: "warn" };
    case "blocked": return { text: "차단", tone: "bad" };
    default: return { text: "미산정", tone: "warn" };
  }
}

const toneCls: Record<"ok" | "warn" | "bad", string> = {
  ok: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  bad: "border-rose-500/30 bg-rose-500/10 text-rose-400",
};

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3">
      <p className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-hint)]">{label}</p>
      <p className="mt-1 text-lg font-black text-[var(--text-primary)]">{value}</p>
      {sub && <p className="text-[10px] text-[var(--text-hint)]">{sub}</p>}
    </div>
  );
}

export default function MultiParcelPage() {
  const params = useParams();
  const locale = (params?.locale as string) || "ko";
  const id = params?.id as string;
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const ssotParcels = site?.parcels ?? null;
  const effArea = effectiveLandAreaSqm(site);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [data, setData] = useState<IntegratedResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // 통합 구획도 입력: 다필지 주소 배열(없으면 대표 주소).
  const mapAddresses = useMemo(() => {
    const list = (ssotParcels ?? [])
      .map((p) => p.address)
      .filter((a): a is string => !!a && a.trim().length > 0);
    if (list.length > 0) return list;
    return site?.address ? [site.address] : [];
  }, [ssotParcels, site?.address]);

  const isMulti = mapAddresses.length >= 2;
  const key = mapAddresses.join("||");
  const proj = (p: string) => `/${locale}/projects/${id}/${p}`;

  // 통합분석 실행(규칙기반 집계 — 무과금 use_llm=false). 다필지일 때만.
  const run = useCallback(async () => {
    if (!isMulti || loading) return;
    setLoading(true); setError("");
    try {
      const r = await apiClient.post<IntegratedResp>("/zoning/integrated-analysis", {
        body: { parcels: mapAddresses.map((address) => ({ address })), use_llm: false },
        useMock: false, timeoutMs: 90000,
      });
      setData(r ?? null);
    } catch {
      setError("통합분석 호출에 실패했습니다. 잠시 후 재시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [isMulti, loading, mapAddresses]);

  // 다필지면 진입 시 1회 자동 실행(무과금). 필지 구성 변경 시 재실행.
  useEffect(() => {
    setData(null);
    if (!isMulti) return;
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // ── 부지 미확정 — 바로 필지 검색/지도클릭/엑셀로 선택(SSOT 기록) ──
  if (!site?.address && !site?.pnu && mapAddresses.length === 0) {
    return (
      <div className="mx-auto max-w-2xl py-10">
        <div className="mb-4 text-center">
          <p className="inline-flex items-center gap-1.5 text-lg font-black text-[var(--text-primary)]">
            <Layers className="size-5 text-[var(--accent-strong)]" aria-hidden /> 다필지 통합 — 필지 선택
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            주소 검색·지도 클릭·엑셀로 2개 이상 필지를 선택하면 통합 구획도와 통합분석이 채워집니다.
          </p>
        </div>
        <GlobalAddressSearch placeholder="주소·지번을 검색하거나 지도에서 필지를 클릭하세요(다필지)" />
      </div>
    );
  }

  const integ = data?.integrated ?? null;
  const adj = data?.adjacency ?? null;
  const dev = devLabel(data?.developability);
  const scn = data?.scenario ?? null;
  const scnL = scnLabel(scn?.status);

  return (
    <div className="flex flex-col gap-3">
      {/* 상단: 주소 + 통합 배지 + 필지선택 + 구획도 다운로드 + 토지이음 정본 */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5">
        <p className="inline-flex flex-wrap items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <Layers className="size-4 text-[var(--accent-strong)]" aria-hidden />
          {site?.address || "다필지 통합"}
          <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${isMulti ? "bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]" : "bg-[var(--surface-muted)] text-[var(--text-hint)]"}`}>
            {isMulti ? `통합 ${mapAddresses.length}필지${effArea ? ` · ${Math.round(effArea).toLocaleString()}㎡` : ""}` : "단일 필지"}
          </span>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <a href="https://www.eum.go.kr/" target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-secondary)] transition hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)]">
            토지이음 정본 열람 <ExternalLink className="size-3" aria-hidden />
          </a>
          <button onClick={() => setPickerOpen((v) => !v)}
            className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-bold transition ${
              pickerOpen ? "border-[var(--accent-strong)] text-[var(--accent-strong)]"
                : "border-[var(--line)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"}`}>
            <MousePointerClick className="size-3.5" aria-hidden /> 필지 선택/변경
            <ChevronDown className={`size-3 transition ${pickerOpen ? "rotate-180" : ""}`} aria-hidden />
          </button>
          <ParcelExportButton
            parcels={ssotParcels?.map((p) => ({ pnu: p.pnu, address: p.address }))}
            address={site?.address}
            pnu={site?.pnu}
          />
        </div>
      </div>

      {pickerOpen && (
        <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--surface-soft)] p-3">
          <GlobalAddressSearch
            initialAddress={site?.address || undefined}
            placeholder="주소·지번 검색 또는 지도에서 필지 클릭(2개 이상 → 통합분석)"
          />
        </div>
      )}

      {/* 2분할: 좌 지도(토지이음급) + 우 통합분석 사이드바 */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_400px]">
        {/* 좌: 실 구획도 지도 — 용도지역 색면(지적편집도) 기본 ON */}
        <div className="overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
          {mapAddresses.length > 0 ? (
            <ParcelBoundaryMap parcels={mapAddresses} primaryZone={site?.zoneCode || undefined} defaultUseDistrict />
          ) : (
            <div className="flex h-[560px] items-center justify-center text-sm text-[var(--text-hint)]">표시할 필지가 없습니다.</div>
          )}
          <p className="mt-2 px-1 text-[10px] leading-relaxed text-[var(--text-hint)]">
            필지경계 = VWorld 연속지적도(정본) · 용도지역 색면 = 국토부 지적편집도(토지이음과 동일 출처).
            우측 상단 컨트롤로 위성/지적편집도·거리·면적 측정·전체화면을 사용하세요.
          </p>
        </div>

        {/* 우: 통합분석 사이드바(실데이터) */}
        <aside className="flex flex-col gap-3">
          <div className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2">
            <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
              <Building2 className="size-4 text-[var(--accent-strong)]" aria-hidden /> 다필지 통합분석
            </p>
            {isMulti && (
              <button onClick={run} disabled={loading}
                className="inline-flex items-center gap-1 rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[11px] font-bold text-white transition hover:opacity-90 disabled:opacity-50">
                <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} aria-hidden /> {loading ? "분석 중…" : data ? "재실행" : "통합분석 실행"}
              </button>
            )}
          </div>

          {/* 단일 필지 — 통합분석 미적용 정직고지 */}
          {!isMulti && (
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-xs leading-relaxed text-[var(--text-secondary)]">
              <p className="font-bold text-[var(--text-primary)]">단일 필지입니다.</p>
              <p className="mt-1">통합분석(면적가중 건폐·용적, 통합 GFA, 인접성)은 <b>2개 이상</b>의 필지를 선택했을 때 실행됩니다.
                위 “필지 선택/변경”에서 인접 필지를 추가하거나, 단일 필지는 부지분석을 이용하세요.</p>
              <Link href={proj("site-analysis")} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] transition hover:border-[var(--accent-strong)]">
                단일 부지분석으로 <ArrowRight className="size-3" aria-hidden />
              </Link>
            </div>
          )}

          {error && <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-400">{error}</p>}
          {isMulti && loading && !data && (
            <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-6 text-center text-xs text-[var(--text-hint)]">통합 용도·건폐·용적·인접성 집계 중…</div>
          )}

          {isMulti && data && (
            <>
              {/* 1) 통합 핵심지표 */}
              <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <p className="mb-2 text-[11px] font-black uppercase tracking-wide text-[var(--text-secondary)]">통합 핵심지표</p>
                <div className="grid grid-cols-2 gap-2">
                  <Metric label="통합 대지면적" value={integ?.total_area_sqm != null ? `${num(integ.total_area_sqm)}㎡` : "—"}
                    sub={integ?.total_area_sqm != null ? `${num(integ.total_area_sqm / PYEONG)}평` : undefined} />
                  <Metric label="대표 용도지역" value={data.dominant_zone || "혼재/미상"}
                    sub={data.zone_mix && data.zone_mix.length >= 2 ? `혼재 ${data.zone_mix.length}종` : undefined} />
                  <Metric label="면적가중 건폐율" value={pct(integ?.blended_bcr_eff_pct)}
                    sub={integ?.blended_bcr_legal_pct != null ? `법정 ${integ.blended_bcr_legal_pct}%` : undefined} />
                  <Metric label="면적가중 용적률" value={pct(integ?.blended_far_eff_pct)}
                    sub={integ?.blended_far_legal_pct != null ? `법정 ${integ.blended_far_legal_pct}%` : undefined} />
                  <div className="col-span-2">
                    <Metric label="통합 가능 연면적(GFA)" value={integ?.integrated_gfa_sqm != null ? `${num(integ.integrated_gfa_sqm)}㎡` : "—"}
                      sub={integ?.integrated_gfa_sqm != null ? `${num(integ.integrated_gfa_sqm / PYEONG)}평${integ?.gfa_basis ? ` · ${integ.gfa_basis}` : ""}` : undefined} />
                  </div>
                </div>
                {integ?.far_basis_note && <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-hint)]">근거: {integ.far_basis_note}</p>}
              </section>

              {/* 2) 통합개발 적합성(인접성·게이트·특이부지) */}
              <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <p className="mb-2 text-[11px] font-black uppercase tracking-wide text-[var(--text-secondary)]">통합개발 적합성</p>
                <div className="flex flex-col gap-2 text-[11px]">
                  {/* 인접성 */}
                  <div className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 ${
                    adj?.contiguous === true ? toneCls.ok : adj?.contiguous === false ? toneCls.bad : toneCls.warn}`}>
                    {adj?.contiguous === true ? <Link2 className="mt-0.5 size-3.5 shrink-0" aria-hidden /> : adj?.contiguous === false ? <Scissors className="mt-0.5 size-3.5 shrink-0" aria-hidden /> : <HelpCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
                    <span><b>{adj?.contiguous === true ? "인접(통합개발 가능)" : adj?.contiguous === false ? "비인접(통합개발 불가)" : "인접성 미상"}</b>{adj?.note ? ` — ${adj.note}` : ""}</span>
                  </div>
                  {/* 개발가능성 게이트 */}
                  <div className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 ${toneCls[dev.tone]}`}>
                    {dev.tone === "ok" ? <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" aria-hidden /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
                    <span><b>개발가능성: {dev.text}</b>{data.honest_disclosure ? ` — ${data.honest_disclosure}` : ""}</span>
                  </div>
                  {/* 특이부지 */}
                  {(data.special_count ?? 0) > 0 && (
                    <div className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 ${toneCls.warn}`}>
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                      <span><b>특이부지 {data.special_count}필지 포함</b> — 인허가·전용·구역해제 등 선행 검토 필요(필지별 내역 참고).</span>
                    </div>
                  )}
                </div>
              </section>

              {/* 3) 통합 시나리오 */}
              <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-[11px] font-black uppercase tracking-wide text-[var(--text-secondary)]">통합 시나리오</p>
                  <span className={`rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${toneCls[scnL.tone]}`}>{scnL.text}</span>
                </div>
                {scn?.disclosure ? (
                  <p className="text-[11px] leading-relaxed text-[var(--text-secondary)]">{scn.disclosure}</p>
                ) : scn?.status === "computed" ? (
                  <p className="inline-flex items-baseline gap-1.5 text-[11px] leading-relaxed text-[var(--text-primary)]">
                    <Lightbulb className="size-3.5 shrink-0 self-center" aria-hidden /> 통합 한도 기준 사업방식 추천이 산정되었습니다. 상세 추천·수지는 개발방식/수지 페이지에서 확인하세요.
                  </p>
                ) : (
                  <p className="text-[11px] text-[var(--text-hint)]">시나리오 정보가 없습니다.</p>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  <Link href={proj("permit")} className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] transition hover:border-[var(--accent-strong)]">개발방식·인허가 상세 <ArrowRight className="size-3" aria-hidden /></Link>
                  <Link href={proj("canvas")} className="inline-flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--accent-strong)] transition hover:border-[var(--accent-strong)]">중앙분석센터(전탭) <ArrowRight className="size-3" aria-hidden /></Link>
                </div>
              </section>

              {/* 4) 필지별 내역(실 per_parcel) */}
              {data.per_parcel && data.per_parcel.length > 0 && (
                <section className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                  <p className="mb-2 inline-flex items-center gap-1.5 text-[11px] font-black uppercase tracking-wide text-[var(--text-secondary)]">
                    <ListTree className="size-3.5" aria-hidden /> 필지별 내역 ({data.per_parcel.length})
                  </p>
                  <ul className="space-y-1.5">
                    {data.per_parcel.map((p, i) => {
                      const sp = p.special_parcel;
                      const spBad = sp && (sp.developability || "").toUpperCase() !== "POSSIBLE";
                      return (
                        <li key={(p.pnu || p.address || "") + i} className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[11px] font-bold text-[var(--text-primary)]">{p.address || p.pnu || `필지 ${i + 1}`}</span>
                            <span className="shrink-0 text-[10px] text-[var(--text-hint)]">{p.area_sqm != null ? `${num(p.area_sqm)}㎡` : "면적 미상"}</span>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-[var(--text-secondary)]">
                            <span>{p.zone_type || "용도 미상"}</span>
                            {p.land_category && <span>· {p.land_category}</span>}
                            {p.bcr_eff_pct != null && <span>· 건폐 {p.bcr_eff_pct}%</span>}
                            {p.far_eff_pct != null && <span>· 용적 {p.far_eff_pct}%</span>}
                            {spBad && <span className="rounded bg-amber-500/15 px-1 py-0.5 font-bold text-amber-500">{sp?.label || "특이부지"}</span>}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              )}

              {/* 경고(정직 degrade) */}
              {data.warnings && data.warnings.length > 0 && (
                <section className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                  <p className="mb-1 inline-flex items-center gap-1 text-[11px] font-bold text-amber-500"><AlertTriangle className="size-3.5" aria-hidden /> 데이터 유의사항</p>
                  <ul className="list-disc space-y-0.5 pl-4 text-[10px] leading-relaxed text-[var(--text-secondary)]">
                    {data.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </section>
              )}

              {/* 통합 구획도 다운로드 */}
              <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                <p className="mb-2 text-[11px] font-black uppercase tracking-wide text-[var(--text-secondary)]">통합 구획도 내려받기</p>
                <ParcelExportButton
                  parcels={ssotParcels?.map((p) => ({ pnu: p.pnu, address: p.address }))}
                  address={site?.address}
                  pnu={site?.pnu}
                />
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
