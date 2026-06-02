"use client";

/**
 * 주변 실거래 인터랙티브 지도.
 *
 * 대상 지번 중심 + 반경 원 + 카테고리별(매매6·전월세4) 건물 마커.
 * 분류 탭(매매/전월세 + 부동산 유형)으로 필터, 마커 클릭 시 건물 정보(평균가·건수·
 * 면적·최근거래) InfoWindow 표시. 백엔드 /zoning/nearby-map(카카오 지오코딩) 사용.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    kakao: any;
  }
}

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
type Category = { label: string; type: string; kind: string; count: number; groups: Group[] };
type MapPayload = {
  center: { lat: number | null; lon: number | null; address?: string } | null;
  radius_m: number;
  lawd_cd: string;
  months: string[];
  categories: Record<string, Category>;
};

const KAKAO_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_KEY;

const TRADE_TYPES: { key: string; label: string; color: string }[] = [
  { key: "apt", label: "아파트", color: "#2dd4bf" },
  { key: "villa", label: "연립·다세대", color: "#60a5fa" },
  { key: "house", label: "단독·다가구", color: "#f59e0b" },
  { key: "officetel", label: "오피스텔", color: "#a78bfa" },
  { key: "land", label: "토지", color: "#84cc16" },
  { key: "commercial", label: "상업·업무", color: "#f472b6" },
];
const RENT_TYPES = TRADE_TYPES.slice(0, 4);

function won(man?: number): string {
  if (!man || man <= 0) return "-";
  if (man >= 10000) {
    const eok = Math.floor(man / 10000);
    const rest = Math.round((man % 10000) / 1000);
    return rest > 0 ? `${eok}.${rest}억` : `${eok}억`;
  }
  return `${man.toLocaleString()}만`;
}
const pyeong = (m2?: number) => (m2 && m2 > 0 ? `${(m2 / 3.305785).toFixed(1)}평` : "-");

let kakaoLoading: Promise<void> | null = null;
function loadKakao(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.kakao?.maps) return Promise.resolve();
  if (kakaoLoading) return kakaoLoading;
  kakaoLoading = new Promise((resolve, reject) => {
    if (!KAKAO_KEY) {
      reject(new Error("KAKAO key 없음"));
      return;
    }
    const script = document.createElement("script");
    script.src = `//dapi.kakao.com/v2/maps/sdk.js?appkey=${KAKAO_KEY}&autoload=false&libraries=services`;
    script.async = true;
    script.onload = () => window.kakao.maps.load(() => resolve());
    script.onerror = () => reject(new Error("Kakao SDK 로드 실패"));
    document.head.appendChild(script);
  });
  return kakaoLoading;
}

export function NearbyTransactionsMap() {
  const siteAnalysis = useProjectContextStore((st) => st.siteAnalysis);
  const address = siteAnalysis?.address || "";
  const pnu = (siteAnalysis?.pnu as string) || "";

  const [payload, setPayload] = useState<MapPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [kind, setKind] = useState<"trade" | "rent">("trade");
  const [type, setType] = useState("apt");
  const [sdkReady, setSdkReady] = useState(false);

  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const circleRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const infoRef = useRef<any>(null);
  const centerMarkerRef = useRef<any>(null);

  // Kakao SDK 로드
  useEffect(() => {
    let alive = true;
    loadKakao().then(() => alive && setSdkReady(true)).catch((e) => alive && setError(String(e.message || e)));
    return () => { alive = false; };
  }, []);

  // 데이터 fetch
  const fetchData = useCallback(async () => {
    if (!address) return;
    setLoading(true);
    setError("");
    try {
      const res = await apiClient.post<MapPayload>("/zoning/nearby-map", {
        body: { address, pnu, radius_m: 1000, months: 3 },
        useMock: false,
        timeoutMs: 90000,
      });
      setPayload(res);
    } catch (e: any) {
      setError(e?.message || "주변 실거래 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [address, pnu]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // 지도 초기화
  useEffect(() => {
    if (!sdkReady || !payload?.center?.lat || !mapEl.current || mapRef.current) return;
    const { kakao } = window;
    const center = new kakao.maps.LatLng(payload.center.lat, payload.center.lon);
    const map = new kakao.maps.Map(mapEl.current, { center, level: 5 });
    mapRef.current = map;
    infoRef.current = new kakao.maps.InfoWindow({ removable: true, zIndex: 10 });
    // 대상지 중심 마커(별표) + 반경 원
    centerMarkerRef.current = new kakao.maps.Marker({
      position: center, map,
      image: new kakao.maps.MarkerImage(
        "data:image/svg+xml;base64," + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="34" height="34"><circle cx="17" cy="17" r="9" fill="#ef4444" stroke="#fff" stroke-width="3"/></svg>'),
        new kakao.maps.Size(34, 34),
      ),
    });
    circleRef.current = new kakao.maps.Circle({
      center, radius: payload.radius_m, strokeWeight: 2, strokeColor: "#2dd4bf",
      strokeOpacity: 0.8, strokeStyle: "dashed", fillColor: "#2dd4bf", fillOpacity: 0.06,
    });
    circleRef.current.setMap(map);
  }, [sdkReady, payload]);

  const activeCategory: Category | undefined = useMemo(
    () => payload?.categories?.[`${type}_${kind}`],
    [payload, type, kind],
  );

  // 마커 갱신
  useEffect(() => {
    if (!mapRef.current || !window.kakao) return;
    const { kakao } = window;
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];
    infoRef.current?.close();
    const groups = activeCategory?.groups || [];
    const color = (kind === "trade" ? TRADE_TYPES : RENT_TYPES).find((t) => t.key === type)?.color || "#2dd4bf";
    const bounds = new kakao.maps.LatLngBounds();
    if (payload?.center?.lat) bounds.extend(new kakao.maps.LatLng(payload.center.lat, payload.center.lon));

    groups.forEach((g) => {
      if (!g.lat || !g.lon) return;
      const pos = new kakao.maps.LatLng(g.lat, g.lon);
      bounds.extend(pos);
      const marker = new kakao.maps.Marker({
        position: pos, map: mapRef.current,
        image: new kakao.maps.MarkerImage(
          "data:image/svg+xml;base64," + btoa(
            `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="34"><path d="M13 0C6 0 0 5 0 12c0 8 13 22 13 22s13-14 13-22C26 5 20 0 13 0z" fill="${color}" stroke="#fff" stroke-width="2"/><circle cx="13" cy="12" r="5" fill="#fff"/></svg>`
          ),
          new kakao.maps.Size(26, 34), { offset: new kakao.maps.Point(13, 34) },
        ),
      });
      kakao.maps.event.addListener(marker, "click", () => {
        const priceLine = kind === "trade"
          ? `평균 <b>${won(g.avg_price_10k)}</b> (${won(g.min_price_10k)}~${won(g.max_price_10k)})`
          : `보증금 <b>${won(g.avg_deposit_10k)}</b>${g.avg_monthly_10k ? ` / 월 ${g.avg_monthly_10k.toLocaleString()}만` : ""}`;
        const dealsHtml = g.deals.slice(0, 5).map((d) => {
          const p = kind === "trade" ? won(d.price_10k_won)
            : `${won(d.deposit_10k_won)}${d.monthly_rent_10k_won ? `/${d.monthly_rent_10k_won}만` : ""}`;
          return `<div style="font-size:11px;color:#475569;">· ${d.deal_date || ""} ${p} · ${pyeong(d.area_m2)} ${d.floor ? `${d.floor}층` : ""}</div>`;
        }).join("");
        infoRef.current.setContent(
          `<div style="padding:10px 12px;min-width:200px;max-width:260px;font-family:sans-serif;">
            <div style="font-weight:700;font-size:13px;color:#0f172a;margin-bottom:2px;">${g.name}</div>
            <div style="font-size:11px;color:#64748b;margin-bottom:6px;">${g.dong} ${g.jibun} · ${g.count}건 · 평균 ${pyeong(g.avg_area_m2)}</div>
            <div style="font-size:12px;color:#0f172a;margin-bottom:6px;">${priceLine}</div>
            ${dealsHtml}
          </div>`
        );
        infoRef.current.open(mapRef.current, marker);
      });
      markersRef.current.push(marker);
    });
    if (groups.length && mapRef.current) mapRef.current.setBounds(bounds);
  }, [activeCategory, kind, type, payload]);

  const typeList = kind === "trade" ? TRADE_TYPES : RENT_TYPES;

  if (!address) return null;

  return (
    <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-base font-bold text-[var(--text-primary)] flex items-center gap-2">
            <span className="text-[var(--accent-strong)]">◉</span> 주변 실거래 지도
          </h3>
          <p className="text-[11px] text-[var(--text-hint)] mt-0.5">
            {payload?.center?.address || address} 중심 · 반경 {(payload?.radius_m || 1000) / 1000}km · 최근 {payload?.months?.length || 3}개월
          </p>
        </div>
        {/* 매매/전월세 토글 */}
        <div className="flex rounded-xl border border-[var(--line-strong)] overflow-hidden">
          {(["trade", "rent"] as const).map((k) => (
            <button key={k} onClick={() => { setKind(k); if (k === "rent" && ["land", "commercial"].includes(type)) setType("apt"); }}
              className={`px-4 py-1.5 text-xs font-bold transition-colors ${kind === k ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}>
              {k === "trade" ? "매매" : "전월세"}
            </button>
          ))}
        </div>
      </div>

      {/* 유형 분류 탭 */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {typeList.map((t) => {
          const cat = payload?.categories?.[`${t.key}_${kind}`];
          const cnt = cat?.count ?? 0;
          const active = type === t.key;
          return (
            <button key={t.key} onClick={() => setType(t.key)}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold border transition-all ${active ? "border-transparent text-white" : "border-[var(--line)] text-[var(--text-secondary)] bg-[var(--surface-muted)] hover:border-[var(--text-tertiary)]"}`}
              style={active ? { backgroundColor: t.color } : undefined}>
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: t.color }} />
              {t.label}<span className="opacity-70">{cnt}</span>
            </button>
          );
        })}
      </div>

      {/* 지도 */}
      <div className="relative">
        <div ref={mapEl} className="w-full rounded-xl overflow-hidden border border-[var(--line-strong)]" style={{ height: 440 }} />
        {(loading || !sdkReady) && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/40 backdrop-blur-sm">
            <div className="flex items-center gap-2 text-white text-sm font-bold">
              <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {!sdkReady ? "지도 로딩…" : "주변 실거래 수집·지오코딩 중…"}
            </div>
          </div>
        )}
        {error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-xl bg-[var(--surface-muted)]">
            <p className="text-sm text-[var(--text-secondary)]">{KAKAO_KEY ? `지도 표시 실패: ${error}` : "지도 키(NEXT_PUBLIC_KAKAO_MAP_KEY) 미설정"}</p>
            <button onClick={fetchData} className="rounded-lg bg-[var(--accent-strong)] px-4 py-1.5 text-xs font-bold text-white">다시 시도</button>
          </div>
        )}
        {payload && !loading && activeCategory && activeCategory.groups.length === 0 && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-4 py-1.5 text-xs font-bold text-white">
            해당 유형 최근 거래 없음
          </div>
        )}
      </div>
    </section>
  );
}
