"use client";

/**
 * 주변 실거래 지도 호환 컴포넌트.
 *
 * 데이터 조회와 필터 UI는 이 컴포넌트가 유지하고, 실제 지도 렌더링은
 * 사통팔땅 단일 엔진(SatongMultiMap)이 담당한다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { SatongMultiMap, type SatongMarketLayerState } from "@/components/map/SatongMultiMap";
import { apiClient } from "@/lib/api-client";
import { resolveMapCenter } from "@/lib/satong-map-layers";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type Deal = {
  price_10k_won?: number;
  deposit_10k_won?: number;
  monthly_rent_10k_won?: number;
  area_m2?: number;
  floor?: number | string;
  deal_date?: string;
};

type Group = {
  name: string;
  dong: string;
  jibun: string;
  lat: number;
  lon: number;
  count: number;
  avg_area_m2: number;
  avg_price_10k?: number;
  min_price_10k?: number;
  max_price_10k?: number;
  avg_deposit_10k?: number;
  avg_monthly_10k?: number;
  deals: Deal[];
};

type Category = {
  label: string;
  type: string;
  kind: string;
  count: number;
  groups: Group[];
};

export type NearbyMapPayload = {
  center: { lat: number | null; lon: number | null; address?: string } | null;
  radius_m: number;
  lawd_cd: string;
  months: string[];
  categories: Record<string, Category>;
  data_source?: string;
  fetch_failed?: boolean;
  partial_failed?: boolean;
  note?: string;
};

type PresaleItem = {
  house_manage_no: string;
  pblanc_no: string;
  name: string;
  address: string;
  area_name: string;
  status: string;
  receipt_begin: string;
  receipt_end: string;
  total_households: string;
  recruit_date: string;
  url: string;
  lat: number;
  lon: number;
  distance_m: number;
};

const TRADE_TYPES = [
  { key: "apt", label: "아파트", color: "#14b8a6" },
  { key: "villa", label: "연립·다세대", color: "#3b82f6" },
  { key: "house", label: "단독·다가구", color: "#f59e0b" },
  { key: "officetel", label: "오피스텔", color: "#8b5cf6" },
  { key: "land", label: "토지", color: "#65a30d" },
  { key: "commercial", label: "상업·업무", color: "#ec4899" },
];

const RENT_TYPES = TRADE_TYPES.slice(0, 4);
const PRESALE_COLOR: Record<string, string> = {
  접수중: "#ef4444",
  접수예정: "#0ea5e9",
  마감: "#94a3b8",
  미정: "#f59e0b",
};

export function NearbyTransactionsMap({
  onPayload,
  onLoading,
  address: addressProp,
  pnu: pnuProp,
}: {
  onPayload?: (p: NearbyMapPayload | null) => void;
  onLoading?: (b: boolean) => void;
  address?: string;
  pnu?: string;
} = {}) {
  const siteAnalysis = useProjectContextStore((st) => st.siteAnalysis);
  const projectId = useProjectContextStore((st) => st.projectId);
  const guardedSite = projectId ? siteAnalysis : null;
  const address = addressProp !== undefined ? addressProp : guardedSite?.address || "";
  const pnu = pnuProp !== undefined ? pnuProp : (guardedSite?.pnu as string) || "";

  const [payload, setPayload] = useState<NearbyMapPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // 백엔드 payload.center 가 null(지오코딩 실패)일 때 쓸 프론트 폴백 좌표.
  //   선택 필지의 pnu/주소를 구획도(parcel-boundaries) center 로 해석 — MOLIT 지오코딩과
  //   독립적인 경로라, 실거래 지오코딩이 실패해도 지도는 선택 위치로 이동한다(서울 폴백 제거).
  const [fallbackCenter, setFallbackCenter] = useState<{ lat: number; lon: number; address?: string } | null>(null);
  // 폴백 center 조회마저 실패(네트워크·타임아웃·center 부재)했는지 — true 면 지도는 기본
  //   위치에 머물므로 '위치 확인 불가' 정직 라벨을 띄운다(무날조: 기본 지도 위장 금지).
  const [fallbackFailed, setFallbackFailed] = useState(false);
  const [kind, setKind] = useState<"trade" | "rent">("trade");
  const [type, setType] = useState("apt");
  const [showPresale, setShowPresale] = useState(false);
  const [presale, setPresale] = useState<PresaleItem[] | null>(null);
  const [presaleLoading, setPresaleLoading] = useState(false);

  const onPayloadRef = useRef(onPayload);
  const onLoadingRef = useRef(onLoading);
  onPayloadRef.current = onPayload;
  onLoadingRef.current = onLoading;

  const fetchData = useCallback(async () => {
    if (!address) return;
    setLoading(true);
    onLoadingRef.current?.(true);
    setError("");
    try {
      const res = await apiClient.post<NearbyMapPayload>("/zoning/nearby-map", {
        body: { address, pnu, radius_m: 1000, months: 3 },
        useMock: false,
        timeoutMs: 90000,
      });
      setPayload(res);
      onPayloadRef.current?.(res);
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "주변 실거래 조회 실패";
      setError(message);
      setPayload(null);
      onPayloadRef.current?.(null);
    } finally {
      setLoading(false);
      onLoadingRef.current?.(false);
    }
  }, [address, pnu]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const fetchPresale = useCallback(async () => {
    // 분양 중심좌표: 백엔드 center 우선, 없으면 폴백 center(선택 필지) 사용.
    const cLat = payload?.center?.lat ?? fallbackCenter?.lat ?? null;
    const cLon = payload?.center?.lon ?? fallbackCenter?.lon ?? null;
    if (!payload || cLat == null || cLon == null) return;
    setPresaleLoading(true);
    try {
      const res = await apiClient.post<{ available: boolean; items: PresaleItem[] }>("/presale/nearby", {
        body: {
          lat: cLat,
          lon: cLon,
          lawd_cd: payload.lawd_cd,
          radius_m: 3000,
          months_back: 12,
        },
        useMock: false,
        timeoutMs: 90000,
      });
      setPresale(res.available ? res.items || [] : []);
    } catch {
      setPresale([]);
    } finally {
      setPresaleLoading(false);
    }
  }, [payload, fallbackCenter?.lat, fallbackCenter?.lon]);

  useEffect(() => {
    if (showPresale && presale === null) void fetchPresale();
  }, [fetchPresale, presale, showPresale]);

  // ── 좌표 폴백: payload.center 가 비면 선택 필지(pnu/주소)로 center 해석 ──
  //   parcel-boundaries 는 VWorld 지적도 geometry 로 center 를 계산하므로, 실거래 지오코딩
  //   실패와 무관하게 선택 위치를 얻는다. 주소·pnu 가 바뀌면 폴백은 초기화.
  const backendCenterOk = !!(payload?.center?.lat && payload?.center?.lon);
  useEffect(() => {
    setFallbackCenter(null);
    setFallbackFailed(false);
  }, [address, pnu]);
  useEffect(() => {
    // payload 가 왔는데 center 가 유효하면 폴백 불필요.
    if (!payload || backendCenterOk) return;
    if (!pnu && !address) return;
    let alive = true;
    void (async () => {
      try {
        const res = await apiClient.post<{ center: { lat: number; lon: number } | null }>(
          "/zoning/parcel-boundaries",
          {
            body: { parcels: [{ pnu: pnu || undefined, address: address || undefined }] },
            useMock: false,
            timeoutMs: 45000,
          },
        );
        if (!alive) return;
        if (res?.center?.lat && res.center.lon) {
          setFallbackCenter({ lat: res.center.lat, lon: res.center.lon, address });
          setFallbackFailed(false);
        } else {
          // 응답은 왔지만 center 가 없음 — 좌표 확인 실패로 정직하게 라벨링(가짜 좌표 금지).
          setFallbackFailed(true);
        }
      } catch {
        // 폴백 조회 자체가 실패(네트워크·타임아웃) — '위치 확인 불가' 라벨을 띄운다.
        if (alive) setFallbackFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [address, backendCenterOk, payload, pnu]);

  // 지도 중심 focusTarget — 백엔드 center 우선, 없으면 프론트 폴백. 둘 다 없으면 null(서울 폴백 X).
  const focusTarget = useMemo(
    () => resolveMapCenter(payload?.center, fallbackCenter),
    [payload?.center, fallbackCenter],
  );

  const activeCategory = useMemo(
    () => payload?.categories?.[`${type}_${kind}`],
    [kind, payload, type],
  );
  const typeList = kind === "trade" ? TRADE_TYPES : RENT_TYPES;
  const marketLayer = useMemo<SatongMarketLayerState>(
    () => ({
      kind,
      type,
      showPresale,
      presaleItems: presale,
    }),
    [kind, presale, showPresale, type],
  );
  // 지도로 넘길 payload — 백엔드 center 가 비면 폴백 center 를 채워, 중심 마커·반경원도
  //   선택 위치에 렌더된다(SatongMultiMap 계약 불변: null 이던 center 만 보강).
  const mapPayload = useMemo<NearbyMapPayload | null>(() => {
    if (!payload) return null;
    if (backendCenterOk || !focusTarget) return payload;
    return {
      ...payload,
      center: { lat: focusTarget.lat, lon: focusTarget.lon, address: payload.center?.address || address },
    };
  }, [payload, backendCenterOk, focusTarget, address]);

  if (!address) return null;

  return (
    <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-base font-bold text-[var(--text-primary)]">
            <span className="text-[var(--accent-strong)]">◉</span> 주변 실거래 지도
          </h3>
          <p className="mt-0.5 text-[11px] text-[var(--text-hint)]">
            {payload?.center?.address || address} 중심 · 반경 {(payload?.radius_m || 1000) / 1000}km · 최근 {payload?.months?.length || 3}개월 · 마커 클릭 시 상세
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex overflow-hidden rounded-xl border border-[var(--line-strong)]">
            {(["trade", "rent"] as const).map((nextKind) => (
              <button
                key={nextKind}
                type="button"
                onClick={() => {
                  setKind(nextKind);
                  if (nextKind === "rent" && ["land", "commercial"].includes(type)) setType("apt");
                }}
                className={`px-4 py-1.5 text-xs font-bold transition-colors ${
                  kind === nextKind
                    ? "bg-[var(--accent-strong)] text-white"
                    : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"
                }`}
              >
                {nextKind === "trade" ? "매매" : "전월세"}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setShowPresale((value) => !value)}
            aria-pressed={showPresale}
            className={`flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-colors ${
              showPresale
                ? "border-transparent bg-[#f59e0b] text-white"
                : "border-[var(--line-strong)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)]"
            }`}
          >
            <span className="inline-block h-2 w-2 rotate-45 bg-current" />
            분양 {showPresale ? `ON${presale?.length ? ` · ${presale.length}곳` : ""}` : "겹쳐보기"}
          </button>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {typeList.map((item) => {
          const count = payload?.categories?.[`${item.key}_${kind}`]?.count ?? 0;
          const active = type === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => setType(item.key)}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold transition-all ${
                active
                  ? "border-transparent text-white"
                  : "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)]"
              }`}
              style={active ? { backgroundColor: item.color } : undefined}
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
              {item.label}<span className="opacity-70">{count}</span>
            </button>
          );
        })}
        {showPresale && (
          <span className="ml-1 flex flex-wrap items-center gap-2 border-l border-[var(--line)] pl-2 text-[11px] text-[var(--text-secondary)]">
            <span className="font-bold text-[#f59e0b]">분양</span>
            {(["접수중", "접수예정", "마감"] as const).map((status) => (
              <span key={status} className="flex items-center gap-1">
                <span className="h-2 w-2 rotate-45" style={{ backgroundColor: PRESALE_COLOR[status] }} />
                {status}
              </span>
            ))}
            <span className="text-[var(--text-hint)]">청약홈·반경3km</span>
          </span>
        )}
      </div>

      <div className="relative">
        <SatongMultiMap
          readOnly
          chrome="immersive"
          height={440}
          marketPayload={mapPayload}
          marketLayer={marketLayer}
          focusTarget={focusTarget}
        />

        {(loading || presaleLoading) && (
          <div className="absolute inset-0 z-[400] flex items-center justify-center rounded-xl bg-black/40 backdrop-blur-sm">
            <div className="flex items-center gap-2 text-sm font-bold text-white">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              {presaleLoading ? "분양 단지 수집·지오코딩 중…" : "주변 실거래 수집·지오코딩 중…"}
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="absolute inset-0 z-[400] flex flex-col items-center justify-center gap-2 rounded-xl bg-[var(--surface-muted)]">
            <p className="text-sm text-[var(--text-secondary)]">지도 표시 실패: {error}</p>
            <button
              type="button"
              onClick={fetchData}
              className="rounded-lg bg-[var(--accent-strong)] px-4 py-1.5 text-xs font-bold text-white"
            >
              다시 시도
            </button>
          </div>
        )}

        {payload && !loading && !focusTarget && fallbackFailed && (
          <div className="absolute top-3 left-1/2 z-[400] flex max-w-[92%] -translate-x-1/2 items-center gap-2 rounded-xl border border-amber-400/40 bg-amber-500/15 px-4 py-2 text-center text-xs font-bold text-amber-800 backdrop-blur">
            <AlertTriangle className="size-4 shrink-0" aria-hidden />
            위치 확인 불가 — 선택 위치의 좌표를 확인하지 못해 지도가 기본 위치로 표시 중입니다. 아래 실거래 목록·건수는 정상 조회 결과입니다.
          </div>
        )}

        {payload && !loading && payload.fetch_failed && (
          <div className="absolute bottom-3 left-1/2 z-[400] flex max-w-[92%] -translate-x-1/2 items-center gap-2 rounded-xl border border-amber-400/40 bg-amber-500/15 px-4 py-2 text-center text-xs font-bold text-amber-800 backdrop-blur">
            <AlertTriangle className="size-4 shrink-0" aria-hidden /> {payload.note || "국토부 실거래 공공데이터가 일시적으로 응답하지 않습니다. 거래가 없는 것이 아니라 조회 실패입니다."}
          </div>
        )}

        {payload && !loading && !payload.fetch_failed && activeCategory && activeCategory.groups?.length === 0 && (
          <div className="absolute bottom-3 left-1/2 z-[400] -translate-x-1/2 rounded-full bg-black/60 px-4 py-1.5 text-xs font-bold text-white">
            해당 유형 최근 거래 없음
          </div>
        )}

        {showPresale && !presaleLoading && presale && presale.length === 0 && (
          <div className="absolute bottom-12 left-1/2 z-[400] -translate-x-1/2 rounded-full bg-[#f59e0b]/80 px-4 py-1.5 text-xs font-bold text-white">
            반경 내 분양 단지 없음 또는 청약홈 연동 필요
          </div>
        )}
      </div>
    </section>
  );
}

export default NearbyTransactionsMap;
