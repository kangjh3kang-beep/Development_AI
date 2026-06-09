"use client";

/**
 * 주변 실거래 인터랙티브 지도.
 *
 * 대상 지번 중심 + 반경 원 + 카테고리별(매매6·전월세4) 건물 마커.
 * 분류 탭(매매/전월세 + 부동산 유형)으로 필터, 마커 클릭 시 건물 정보(평균가·건수·
 * 면적·최근거래) 팝업. 백엔드 /zoning/nearby-map(카카오 지오코딩) 사용.
 *
 * 지도 엔진: 카카오맵 JS SDK(한국 지도·한글 라벨). 키=NEXT_PUBLIC_KAKAO_MAP_KEY,
 * 카카오 콘솔에 사이트 도메인 등록 필요. 좌표계 WGS84 동일.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";
import { loadKakaoMap } from "@/lib/kakao-map";

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
  name: string; dong: string; jibun: string;
  lat: number; lon: number; count: number; avg_area_m2: number;
  avg_price_10k?: number; min_price_10k?: number; max_price_10k?: number;
  avg_deposit_10k?: number; avg_monthly_10k?: number; deals: Deal[];
};
type Category = { label: string; type: string; kind: string; count: number; groups: Group[] };
export type NearbyMapPayload = {
  center: { lat: number | null; lon: number | null; address?: string } | null;
  radius_m: number; lawd_cd: string; months: string[];
  categories: Record<string, Category>;
};
type MapPayload = NearbyMapPayload;

const TRADE_TYPES = [
  { key: "apt", label: "아파트", color: "#14b8a6" },
  { key: "villa", label: "연립·다세대", color: "#3b82f6" },
  { key: "house", label: "단독·다가구", color: "#f59e0b" },
  { key: "officetel", label: "오피스텔", color: "#8b5cf6" },
  { key: "land", label: "토지", color: "#65a30d" },
  { key: "commercial", label: "상업·업무", color: "#ec4899" },
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

export function NearbyTransactionsMap({
  onPayload,
  onLoading,
  address: addressProp,
  pnu: pnuProp,
}: {
  /** 동일 nearby-map 데이터를 부모와 공유(중복 fetch 방지). 부지분석 등은 미전달=내부 사용만. */
  onPayload?: (p: NearbyMapPayload | null) => void;
  onLoading?: (b: boolean) => void;
  /** 주소/pnu 직접 주입(마켓 약식검색 등). 미전달 시 활성 프로젝트 store 사용. */
  address?: string;
  pnu?: string;
} = {}) {
  const siteAnalysis = useProjectContextStore((st) => st.siteAnalysis);
  // prop 우선(약식 검색 페이지) → 없으면 활성 프로젝트 store
  const address = addressProp !== undefined ? addressProp : siteAnalysis?.address || "";
  const pnu = pnuProp !== undefined ? pnuProp : (siteAnalysis?.pnu as string) || "";

  const [payload, setPayload] = useState<MapPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [kind, setKind] = useState<"trade" | "rent">("trade");
  const [type, setType] = useState("apt");
  const [sdkReady, setSdkReady] = useState(false);

  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]); // 건물 마커 오버레이 목록
  const circleRef = useRef<any>(null);
  const centerRef = useRef<any>(null);
  const infoRef = useRef<any>(null); // 현재 열린 정보창

  // 부모가 매 렌더 새 함수를 넘겨도(인라인 콜백) fetch가 재실행되지 않도록 ref로 안정화.
  // → 콜백을 의존성에서 제거해 fetch 폭주 차단(데이터/동작은 동일).
  const onPayloadRef = useRef(onPayload);
  const onLoadingRef = useRef(onLoading);
  onPayloadRef.current = onPayload;
  onLoadingRef.current = onLoading;

  useEffect(() => {
    let alive = true;
    loadKakaoMap().then(() => alive && setSdkReady(true)).catch((e) => alive && setError(String(e.message || e)));
    return () => { alive = false; };
  }, []);

  const fetchData = useCallback(async () => {
    if (!address) return;
    setLoading(true);
    onLoadingRef.current?.(true);
    setError("");
    try {
      const res = await apiClient.post<MapPayload>("/zoning/nearby-map", {
        body: { address, pnu, radius_m: 1000, months: 3 },
        useMock: false,
        timeoutMs: 90000,
      });
      setPayload(res);
      onPayloadRef.current?.(res); // 부모(마켓분석)가 동일 데이터로 실거래 현황·시세 산출
    } catch (e: any) {
      setError(e?.message || "주변 실거래 조회 실패");
      onPayloadRef.current?.(null);
    } finally {
      setLoading(false);
      onLoadingRef.current?.(false);
    }
  }, [address, pnu]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // 정보창 열기(이전 것 닫고 위치 기반으로 표시) — Leaflet bindPopup 대응.
  const openInfo = useCallback((latlng: any, html: string) => {
    const kakao = window.kakao;
    if (!kakao || !mapRef.current) return;
    try { infoRef.current?.close(); } catch { /* noop */ }
    const iw = new kakao.maps.InfoWindow({ position: latlng, content: html, removable: true, zIndex: 900 });
    iw.open(mapRef.current);
    infoRef.current = iw;
  }, []);

  // 지도 초기화 (중심 + 반경)
  useEffect(() => {
    if (!sdkReady || !payload?.center?.lat || !mapEl.current || mapRef.current) return;
    const kakao = window.kakao;
    const center = new kakao.maps.LatLng(payload.center.lat, payload.center.lon);
    const map = new kakao.maps.Map(mapEl.current, { center, level: 5 });
    mapRef.current = map;

    // 깜빡이는 펄스 중심 마커(대상 지번 강조) — CustomOverlay + CSS keyframes
    if (typeof document !== "undefined" && !document.getElementById("propai-pulse-style")) {
      const st = document.createElement("style");
      st.id = "propai-pulse-style";
      st.textContent = `@keyframes propaiPulse{0%{transform:scale(.6);opacity:.9}70%{transform:scale(2.4);opacity:0}100%{opacity:0}}
.propai-pin{position:relative;width:16px;height:16px}
.propai-pin .core{position:absolute;left:50%;top:50%;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:#ef4444;border:3px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.4);z-index:2;cursor:pointer}
.propai-pin .ring{position:absolute;left:50%;top:50%;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;background:rgba(239,68,68,.6);animation:propaiPulse 1.6s ease-out infinite;z-index:1}`;
      document.head.appendChild(st);
    }
    const pinEl = document.createElement("div");
    pinEl.className = "propai-pin";
    pinEl.innerHTML = '<div class="ring"></div><div class="core"></div>';
    pinEl.onclick = () =>
      openInfo(center, `<div style="padding:6px 10px;font-size:12px;"><b>분석 대상지</b><br/>${payload.center?.address || address}</div>`);
    centerRef.current = new kakao.maps.CustomOverlay({
      position: center, content: pinEl, xAnchor: 0.5, yAnchor: 0.5, zIndex: 1000,
    });
    centerRef.current.setMap(map);

    circleRef.current = new kakao.maps.Circle({
      center, radius: payload.radius_m, strokeWeight: 2, strokeColor: "#14b8a6",
      strokeOpacity: 0.9, strokeStyle: "dashed", fillColor: "#14b8a6", fillOpacity: 0.05,
    });
    circleRef.current.setMap(map);

    // 컨테이너가 숨김→표시 전환된 경우 레이아웃 보정(Leaflet invalidateSize 대응).
    const t = setTimeout(() => { try { map.relayout(); map.setCenter(center); } catch { /* noop */ } }, 100);
    return () => {
      clearTimeout(t);
      try { infoRef.current?.close(); } catch { /* noop */ }
      overlaysRef.current.forEach((o) => { try { o.setMap(null); } catch { /* noop */ } });
      try { circleRef.current?.setMap(null); } catch { /* noop */ }
      try { centerRef.current?.setMap(null); } catch { /* noop */ }
      overlaysRef.current = [];
      mapRef.current = null;
      circleRef.current = null;
      centerRef.current = null;
      infoRef.current = null;
    };
    // openInfo는 안정적(렌더 무관)이라 의존성에서 제외.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sdkReady, payload, address]);

  const activeCategory = useMemo(
    () => payload?.categories?.[`${type}_${kind}`],
    [payload, type, kind],
  );

  // 마커 갱신
  useEffect(() => {
    if (!mapRef.current || !window.kakao) return;
    const kakao = window.kakao;
    // 이전 건물 오버레이 제거
    overlaysRef.current.forEach((o) => { try { o.setMap(null); } catch { /* noop */ } });
    overlaysRef.current = [];
    try { infoRef.current?.close(); } catch { /* noop */ }
    const groups = activeCategory?.groups || [];
    const color = (kind === "trade" ? TRADE_TYPES : RENT_TYPES).find((t) => t.key === type)?.color || "#14b8a6";
    const pts: Array<[number, number]> = [];
    if (payload?.center?.lat != null && payload?.center?.lon != null) {
      pts.push([payload.center.lat, payload.center.lon]);
    }

    groups.forEach((g) => {
      if (!g.lat || !g.lon) return;
      pts.push([g.lat, g.lon]);
      // 평당가(만원/평) = 평균거래가 / (평균면적/3.305785)
      const ppyeong =
        kind === "trade" && g.avg_price_10k && g.avg_area_m2 > 0
          ? Math.round(g.avg_price_10k / (g.avg_area_m2 / 3.305785))
          : 0;
      const priceLine = kind === "trade"
        ? `평당 <b>${ppyeong ? `${ppyeong.toLocaleString()}만원/평` : "-"}</b>` +
          ` <span style="color:#94a3b8">· 총액 평균 ${won(g.avg_price_10k)}</span>`
        : `보증금 <b>${won(g.avg_deposit_10k)}</b>${g.avg_monthly_10k ? ` / 월 ${g.avg_monthly_10k.toLocaleString()}만` : ""}`;
      const dealsHtml = g.deals.slice(0, 5).map((d) => {
        const dpp = kind === "trade" && d.price_10k_won && d.area_m2 && d.area_m2 > 0
          ? `${Math.round(d.price_10k_won / (d.area_m2 / 3.305785)).toLocaleString()}만/평`
          : "";
        const p = kind === "trade" ? (dpp || won(d.price_10k_won))
          : `${won(d.deposit_10k_won)}${d.monthly_rent_10k_won ? `/${d.monthly_rent_10k_won}만` : ""}`;
        return `<div style="font-size:11px;color:#475569;">· ${d.deal_date || ""} ${p} · ${pyeong(d.area_m2)} ${d.floor ? `${d.floor}층` : ""}</div>`;
      }).join("");
      const html =
        `<div style="min-width:200px;max-width:260px;font-family:sans-serif;">
          <div style="font-weight:700;font-size:13px;color:#0f172a;">${g.name}</div>
          <div style="font-size:11px;color:#64748b;margin-bottom:6px;">${g.dong} ${g.jibun} · ${g.count}건 · 평균 ${pyeong(g.avg_area_m2)}</div>
          <div style="font-size:12px;color:#0f172a;margin-bottom:6px;">${priceLine}</div>${dealsHtml}
        </div>`;
      // 거래건수에 따라 마커 크기 가변(반지름 6~16 → 지름 px)
      const r = Math.min(16, 6 + Math.round(Math.sqrt(g.count) * 1.6));
      const d = r * 2;
      const dot = document.createElement("div");
      dot.style.cssText = `width:${d}px;height:${d}px;border-radius:50%;background:${color};` +
        `border:1.5px solid #fff;opacity:.9;cursor:pointer;box-shadow:0 0 4px rgba(0,0,0,.3)`;
      const pos = new kakao.maps.LatLng(g.lat, g.lon);
      dot.onclick = () => openInfo(pos, html);
      const ov = new kakao.maps.CustomOverlay({ position: pos, content: dot, xAnchor: 0.5, yAnchor: 0.5, clickable: true });
      ov.setMap(mapRef.current);
      overlaysRef.current.push(ov);
    });
    if (pts.length > 1) {
      try {
        const bounds = new kakao.maps.LatLngBounds();
        pts.forEach(([la, lo]) => bounds.extend(new kakao.maps.LatLng(la, lo)));
        mapRef.current.setBounds(bounds, 40, 40, 40, 40);
      } catch { /* noop */ }
    }
    // openInfo는 안정적이라 의존성 제외.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
            {payload?.center?.address || address} 중심 · 반경 {(payload?.radius_m || 1000) / 1000}km · 최근 {payload?.months?.length || 3}개월 · 마커 클릭 시 상세
          </p>
        </div>
        <div className="flex rounded-xl border border-[var(--line-strong)] overflow-hidden">
          {(["trade", "rent"] as const).map((k) => (
            <button key={k} onClick={() => { setKind(k); if (k === "rent" && ["land", "commercial"].includes(type)) setType("apt"); }}
              className={`px-4 py-1.5 text-xs font-bold transition-colors ${kind === k ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"}`}>
              {k === "trade" ? "매매" : "전월세"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {typeList.map((t) => {
          const cnt = payload?.categories?.[`${t.key}_${kind}`]?.count ?? 0;
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

      <div className="relative">
        <div ref={mapEl} className="w-full rounded-xl overflow-hidden border border-[var(--line-strong)] z-0" style={{ height: 440 }} />
        {(loading || !sdkReady) && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/40 backdrop-blur-sm z-[400]">
            <div className="flex items-center gap-2 text-white text-sm font-bold">
              <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              {!sdkReady ? "지도 로딩…" : "주변 실거래 수집·지오코딩 중…"}
            </div>
          </div>
        )}
        {error && !loading && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-xl bg-[var(--surface-muted)] z-[400]">
            <p className="text-sm text-[var(--text-secondary)]">지도 표시 실패: {error}</p>
            <button onClick={fetchData} className="rounded-lg bg-[var(--accent-strong)] px-4 py-1.5 text-xs font-bold text-white">다시 시도</button>
          </div>
        )}
        {payload && !loading && activeCategory && activeCategory.groups?.length === 0 && (
          <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-4 py-1.5 text-xs font-bold text-white z-[400]">
            해당 유형 최근 거래 없음
          </div>
        )}
      </div>
    </section>
  );
}
