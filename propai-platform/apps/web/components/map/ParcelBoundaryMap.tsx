"use client";

/**
 * 필지 경계(구획도) 지도 — 단필지/다필지.
 *
 * /zoning/parcel-boundaries(VWORLD 지적도 geometry + 토지특성)를 호출해
 * 필지 경계 폴리곤을 카카오맵 위에 그리고, 용도지역별 색상·면적 라벨을 표시.
 */

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, BarChart3, HelpCircle, Info, Lightbulb, Link2, Map, Scissors } from "lucide-react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { normalizeZoning } from "@/lib/kr-building-regulations";
import { SatongMultiMap } from "@/components/map/SatongMultiMap";
import type { SatongMapFeature, SatongMapLayerState } from "@/lib/satong-map-layers";

type Feature = {
  pnu: string;
  address: string;
  area_sqm: number;
  area_source?: string | null;
  area_confidence?: "high" | "mid" | "low" | "none" | null;
  area_note?: string | null;
  area_ledger_sqm?: number | null;   // 토지대장(공부상) 면적
  area_cadastral_sqm?: number | null; // 지적도 등록면적
  zone_type: string | null;
  zone_type_2: string | null;
  zone_limits: { max_bcr_pct?: number; max_far_pct?: number } | null;
  official_price_per_sqm?: number | null;   // 개별공시지가(원/㎡) — P4 공시지가 레이어
  jimok?: string | null;
  land_use_situation?: string | null;
  terrain?: string | null;
  building_name?: string | null;
  main_purpose?: string | null;
  use_approval_date?: string | null;
  built_year?: number | null;
  building_age_years?: number | null;
  geometry: any;
};
type Adjacency = { contiguous: boolean | null; components: number | null; note: string };
type Neighbor = { pnu: string; jimok: string; is_road: boolean; geometry: any };
type Boundaries = {
  features: Feature[];
  center: { lat: number; lon: number } | null;
  total_area_sqm: number;
  parcel_count: number;
  adjacency?: Adjacency;
  neighbors?: Neighbor[];       // A+D: 주변 필지·도로(벡터 지적도)
  merged_geometry?: any;        // B: 통합개발 외곽선
  min_gap_m?: number | null;    // C: 실제 최소 이격(m)
  // 다필지 종합분석(실질용적률·건폐율·개발방법·추진방안)
  integrated_analysis?: {
    total_area_pyeong?: number | null;
    zone_types?: string[];
    zone_mixed?: boolean;
    effective_bcr_pct?: number | null;
    effective_far_pct?: number | null;
    total_gfa_sqm?: number | null;
    development_methods?: string[];
    recommendation?: string;
    notes?: string[];
  } | null;
};

const PALETTE = ["#14b8a6", "#3b82f6", "#f59e0b", "#8b5cf6", "#ec4899", "#65a30d"];
function zoneColor(zone: string | null, i: number): string {
  const z = zone || "";
  if (z.includes("상업")) return "#ec4899";
  if (z.includes("주거")) return "#14b8a6";
  if (z.includes("공업")) return "#f59e0b";
  if (z.includes("녹지") || z.includes("관리") || z.includes("농림")) return "#65a30d";
  return PALETTE[i % PALETTE.length];
}
function pyeong(sqm: number): string {
  return sqm ? `${Math.round(sqm / 3.305785).toLocaleString()}평` : "-";
}
const PRICE_RAMP = ["#bae6fd", "#7dd3fc", "#38bdf8", "#fb923c", "#ef4444"];
function priceManPyeong(perSqm: number | null | undefined): string {
  if (!perSqm || perSqm <= 0) return "-";
  // ㎡·평 병행 표기(공용 satong-map-layers.priceManPyeong과 동일 규칙).
  const manPerSqm = Math.round(perSqm / 1e4).toLocaleString();
  const manPerPyeong = Math.round((perSqm * 3.305785) / 1e4).toLocaleString();
  return `${manPerSqm}만원/㎡ (${manPerPyeong}만원/평)`;
}
const AGE_RAMP = ["#7dd3fc", "#34d399", "#facc15", "#fb923c", "#ef4444"];

export function ParcelBoundaryMap({
  parcels,
  statusColors,
  statusLabels,
  highlight,
  onParcelClick,
  primaryZone,
  defaultUseDistrict,
}: {
  parcels: string[];
  statusColors?: Record<string, string>; // 주소 → 채움색(계약/동의 상태강조)
  statusLabels?: Record<string, string>; // 주소 → 상태 라벨(팝업)
  highlight?: string; // 강조할 주소(토지조서 행 클릭)
  onParcelClick?: (address: string) => void;
  // 부지분석 확정 용도지역(siteAnalysis.zoneCode) — 구획도·시나리오 용도지역 표기를 단일 출처로
  // 정합시키기 위한 SSOT 오버레이. 주(첫) 필지에만 적용(지적도 토지특성 vs 확정값 불일치 해소).
  primaryZone?: string | null;
  // 지적편집도(용도지역 색면) 기본 ON — 토지이음式 용도지역 색면을 통합 구획도뷰에서 바로 표시.
  defaultUseDistrict?: boolean;
}) {
  const list = useMemo(() => parcels.map((s) => s.trim()).filter(Boolean), [parcels]);
  const key = list.join("||");
  // 주 필지의 표시 용도지역 = 확정 SSOT(primaryZone) 우선, 없으면 지적도 토지특성(zone_type).
  // 주소 정규화 비교로 첫 필지(분석 대상)에만 적용 — 다른 필지는 원래 토지특성 유지.
  const normAddr = (a?: string | null) => (a || "").replace(/\s+/g, "");
  const primaryAddr = normAddr(list[0]);
  // 지도 라벨을 계산 측 표준 명칭과 정합("일반상업"→"일반상업지역"). 매칭 실패 시 원문 유지.
  const primaryZoneLabel = primaryZone ? (normalizeZoning(primaryZone) ?? primaryZone) : primaryZone;
  const effZone = (f: Feature, i: number): string | null => {
    if (primaryZoneLabel && (i === 0 || normAddr(f.address) === primaryAddr)) return primaryZoneLabel;
    return f.zone_type;
  };
  const [data, setData] = useState<Boundaries | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // P4: 구획도 색상 모드 — 용도지역(기본) / 공시지가 코로플레스.
  const [colorMode, setColorMode] = useState<"zone" | "price" | "age">("zone");
  // 공시지가 색 정규화용 min/max(0 제외). 데이터 변경 시 재계산.
  const priceRange = useMemo(() => {
    const ps = (data?.features ?? [])
      .map((f) => f.official_price_per_sqm || 0)
      .filter((p) => p > 0);
    return ps.length ? { min: Math.min(...ps), max: Math.max(...ps) } : { min: 0, max: 0 };
  }, [data]);
  const hasPrice = priceRange.max > 0;
  const hasAge = (data?.features ?? []).some((f) => typeof f.building_age_years === "number");
  const boundaryMapFeatures = useMemo<SatongMapFeature[]>(
    () =>
      (data?.features ?? []).map((f, i) => ({
        id: f.pnu || f.address || `boundary-${i}`,
        pnu: f.pnu,
        address: f.address || f.pnu || `필지 ${i + 1}`,
        areaSqm: f.area_sqm ?? null,
        zoneType: effZone(f, i),
        zoneType2: f.zone_type_2 ?? null,
        jimok: f.jimok ?? null,
        officialPricePerSqm: f.official_price_per_sqm ?? null,
        builtYear: f.built_year ?? null,
        buildingAgeYears: f.building_age_years ?? null,
        geometry: f.geometry,
        source: "boundary",
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, primaryZoneLabel, primaryAddr],
  );
  const boundaryLayerState = useMemo<SatongMapLayerState>(() => {
    const controlsByLayer: SatongMapLayerState["controlsByLayer"] = {
      cadastre: ["parcel-boundary", "selected-parcel"],
      zoning: ["land-use"],
      "official-price": ["unit-price"],
      age: ["building-age"],
      terrain: ["hybrid"],
    };
    const enabledLayerIds: SatongMapLayerState["enabledLayerIds"] =
      colorMode === "price"
        ? ["cadastre", "official-price", "terrain"]
        : colorMode === "age"
          ? ["cadastre", "age", "terrain"]
          : defaultUseDistrict === false
            ? ["cadastre", "terrain"]
            : ["cadastre", "zoning", "terrain"];
    return { enabledLayerIds, controlsByLayer };
  }, [colorMode, defaultUseDistrict]);

  // 데이터 조회
  useEffect(() => {
    if (!list.length) { setData(null); return; }
    let alive = true;
    setLoading(true); setError("");
    apiClient
      .post<Boundaries>("/zoning/parcel-boundaries", {
        body: { parcels: list.map((a) => ({ address: a })) },
        useMock: false, timeoutMs: 45000,
      })
      .then((d) => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (!alive) return;
        // 에러 종류별 진단 문구 — apiClient는 타임아웃(408)·HTTP오류(5xx 등)는
        // ApiClientError(.status)로, 네트워크 실패는 status 없는 일반 에러로 던진다.
        if (e instanceof ApiClientError) {
          const s = e.status;
          if (s === 408) setError("응답 지연(VWorld 지적도 서버 지연) — 잠시 후 재시도");
          else if (s >= 500) setError("서버 오류로 필지 경계를 불러오지 못함");
          else if (s === 0) setError("네트워크 오류 — 연결 상태를 확인하세요");
          else setError("필지 경계를 불러오지 못했습니다.");
        } else {
          // ApiClientError가 아니면 fetch 자체 실패(네트워크 단절 등)
          setError("네트워크 오류 — 연결 상태를 확인하세요");
        }
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (!list.length) return null;

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
          <Map className="size-4 shrink-0" aria-hidden /> 필지 구획도 {data ? `(${data.parcel_count}필지 · 총 ${data.total_area_sqm?.toLocaleString()}㎡ / ${pyeong(data.total_area_sqm)})` : ""}
        </p>
        {loading && <span className="text-xs text-[var(--text-hint)]">불러오는 중…</span>}
      </div>
      {error && <p className="mb-2 text-xs text-rose-500">{error}</p>}
      {/* 면적 교차검증 — 주 필지(첫 필지)의 토지대장↔지적도 대조 결과 */}
      {(() => {
        const f0 = data?.features?.[0];
        if (!f0?.area_note || f0.area_confidence === "high") return null;
        const low = f0.area_confidence === "low";
        return (
          <div className={`mb-2 inline-flex flex-wrap items-baseline gap-1 rounded-lg border px-3 py-2 text-[11px] font-semibold ${
            low ? "border-amber-500/30 bg-amber-500/10 text-amber-400" : "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-secondary)]"
          }`}>
            {low ? <AlertTriangle className="size-3.5 self-center shrink-0" aria-hidden /> : <Info className="size-3.5 self-center shrink-0" aria-hidden />}
            {low ? "면적 검증 주의 — " : "면적 출처 — "}{f0.area_note}
            {f0.area_ledger_sqm && f0.area_cadastral_sqm && (
              <span className="ml-1 text-[var(--text-hint)]">(대장 {f0.area_ledger_sqm.toLocaleString()}㎡ · 지적 {f0.area_cadastral_sqm.toLocaleString()}㎡)</span>
            )}
          </div>
        );
      })()}
      {/* 다필지 인접성(통합개발 가능 여부) */}
      {data && data.parcel_count >= 2 && data.adjacency && (
        <div className={`mb-2 inline-flex flex-wrap items-baseline gap-1 rounded-lg border px-3 py-2 text-[11px] font-semibold ${
          data.adjacency.contiguous === true
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
            : data.adjacency.contiguous === false
              ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
              : "border-amber-500/30 bg-amber-500/10 text-amber-400"
        }`}>
          {data.adjacency.contiguous === true ? <Link2 className="size-3.5 self-center shrink-0" aria-hidden /> : data.adjacency.contiguous === false ? <Scissors className="size-3.5 self-center shrink-0" aria-hidden /> : <HelpCircle className="size-3.5 self-center shrink-0" aria-hidden />}
          {data.adjacency.contiguous === true ? "통합개발 가능 — " : data.adjacency.contiguous === false ? "통합개발 불가 — " : "인접성 미상 — "}
          {data.adjacency.note}
        </div>
      )}

      {/* 다필지 종합분석 — 실질 건폐율/용적률 + 개발방법 + 최적추진방안(개발사업분석 핵심) */}
      {data?.integrated_analysis && (data.parcel_count >= 2 || data.integrated_analysis.effective_far_pct) && (
        <div className="mb-2 rounded-lg border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-3 py-2.5">
          <p className="mb-1.5 inline-flex items-center gap-1.5 text-[11px] font-bold text-[var(--accent-strong)]"><BarChart3 className="size-3.5 shrink-0" aria-hidden /> 통합 종합분석</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--text-secondary)]">
            <span>총 <b className="text-[var(--text-primary)]">{data.integrated_analysis.total_area_pyeong?.toLocaleString()}평</b></span>
            {data.integrated_analysis.effective_bcr_pct != null && <span>실질 건폐율 <b className="text-[var(--text-primary)]">{data.integrated_analysis.effective_bcr_pct}%</b></span>}
            {data.integrated_analysis.effective_far_pct != null && <span>실질 용적률 <b className="text-[var(--text-primary)]">{data.integrated_analysis.effective_far_pct}%</b></span>}
            {data.integrated_analysis.total_gfa_sqm != null && <span>가능 연면적 <b className="text-[var(--text-primary)]">{Math.round(data.integrated_analysis.total_gfa_sqm).toLocaleString()}㎡</b></span>}
            {data.integrated_analysis.zone_mixed && <span className="inline-flex items-center gap-1 text-amber-500"><AlertTriangle className="size-3.5 shrink-0" aria-hidden /> 용도지역 혼재({data.integrated_analysis.zone_types?.join("·")})</span>}
          </div>
          {data.integrated_analysis.development_methods && data.integrated_analysis.development_methods.length > 0 && (
            <p className="mt-1.5 text-[11px] text-[var(--text-secondary)]">
              개발방법: {data.integrated_analysis.development_methods.map((m) => (
                <span key={m} className="mr-1 inline-block rounded bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--text-primary)]">{m}</span>
              ))}
            </p>
          )}
          {data.integrated_analysis.recommendation && (
            <p className="mt-1.5 inline-flex items-baseline gap-1.5 text-[11px] font-semibold text-[var(--text-primary)]"><Lightbulb className="size-3.5 self-center shrink-0" aria-hidden /> {data.integrated_analysis.recommendation}</p>
          )}
        </div>
      )}
      {/* 정밀 구획도 범례 — 주변 필지·도로(벡터 지적도) + 통합 외곽선 */}
      {data && (data.neighbors?.length || data.merged_geometry) && (
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[10px] text-[var(--text-hint)]">
          <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-teal-500/40 ring-1 ring-teal-500" />선택 필지</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-300/30 ring-1 ring-slate-400" />주변 필지</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-200/40 ring-1 ring-amber-600" />도로</span>
          {data.parcel_count >= 2 && (
            <span className="flex items-center gap-1"><span className="inline-block h-0 w-3 border-t-2 border-dashed border-sky-500" />통합개발 경계</span>
          )}
          <span className="ml-auto text-[var(--text-hint)]">지적도(VWorld) 벡터 · 위성 베이스 권장</span>
        </div>
      )}
      {/* P4: 색상 모드 토글(용도지역/공시지가) + 공시지가 코로플레스 범례 */}
      {data && data.features?.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-2 px-1">
          <div className="flex overflow-hidden rounded-lg border border-[var(--line-strong)]">
            <button type="button" onClick={() => setColorMode("zone")}
              className={`px-3 py-1 text-[11px] font-bold transition-colors ${colorMode === "zone" ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}>
              용도지역
            </button>
            <button type="button" onClick={() => hasPrice && setColorMode("price")} disabled={!hasPrice}
              title={hasPrice ? "" : "공시지가 데이터 없음(VWorld 미제공)"}
              className={`px-3 py-1 text-[11px] font-bold transition-colors disabled:opacity-40 ${colorMode === "price" ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}>
              공시지가
            </button>
            <button type="button" onClick={() => hasAge && setColorMode("age")} disabled={!hasAge}
              title={hasAge ? "" : "건축물대장 사용승인일 데이터 없음"}
              className={`px-3 py-1 text-[11px] font-bold transition-colors disabled:opacity-40 ${colorMode === "age" ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}>
              노후도
            </button>
          </div>
          {colorMode === "price" && hasPrice && (
            <span className="flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-hint)]">
              <span className="text-[var(--text-secondary)]">낮음</span>
              {PRICE_RAMP.map((c) => <span key={c} className="inline-block h-2.5 w-4" style={{ backgroundColor: c }} />)}
              <span className="text-[var(--text-secondary)]">높음</span>
              <span className="ml-1">{priceManPyeong(priceRange.min)} ~ {priceManPyeong(priceRange.max)}</span>
            </span>
          )}
          {colorMode === "age" && hasAge && (
            <span className="flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-hint)]">
              <span className="text-[var(--text-secondary)]">신축</span>
              {AGE_RAMP.map((c) => <span key={c} className="inline-block h-2.5 w-4" style={{ backgroundColor: c }} />)}
              <span className="text-[var(--text-secondary)]">40년+</span>
              <span className="ml-1">건축물대장 사용승인일 기준</span>
            </span>
          )}
        </div>
      )}
      <div className="relative">
        <SatongMultiMap
          readOnly
          height={340}
          chrome="immersive"
          selectedParcels={boundaryMapFeatures}
          layerState={boundaryLayerState}
          focusTarget={data?.center ? { lat: data.center.lat, lon: data.center.lon, label: list[0] } : null}
          onFeatureClick={(feature) => onParcelClick?.(feature.address)}
          featureStatusColors={statusColors}
          featureStatusLabels={statusLabels}
          highlightFeatureAddress={highlight}
        />
        {/* 로딩/빈결과 오버레이 — 무한 '불러오는 중' 방지 */}
        {(loading || (!loading && !error && (!data || !data.features?.length))) && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[var(--surface-soft)]/70 text-xs text-[var(--text-hint)]">
            {loading
              ? "지적도 경계 불러오는 중…"
              : "필지 경계를 찾지 못했습니다 (지번 정확도·VWorld 지적도 미제공 가능). 주소를 확인하세요."}
          </div>
        )}
      </div>
      {data && data.features?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {(data.features ?? []).map((f, i) => (
            <span key={f.pnu + i} className="flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1 text-[11px]">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: zoneColor(effZone(f, i), i) }} />
              <span className="font-semibold text-[var(--text-secondary)]">{i + 1}. {effZone(f, i) || "용도미상"}{f.zone_type_2 ? `·${f.zone_type_2}` : ""}</span>
              <span className="text-[var(--text-hint)]">{Math.round(f.area_sqm).toLocaleString()}㎡</span>
              {f.building_age_years != null && <span className="text-[var(--text-hint)]">노후 {f.building_age_years}년</span>}
              {f.terrain && <span className="text-[var(--text-hint)]">지형 {f.terrain}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default ParcelBoundaryMap;
