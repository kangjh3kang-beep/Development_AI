"use client";

/**
 * SatongMultiMap — 사통팔땅 지도 기반 통합 시스템의 단일 지도 엔진.
 *
 * 사용 방법:
 *   1. 지도를 클릭하면 해당 좌표의 필지 정보를 백엔드에서 조회한다.
 *   2. 조회 완료 후 지도 위에 '확인 카드'가 나타난다 (즉시 추가 안 함).
 *   3. 확인 카드에서 [＋추가]를 누르면 staged(선택 대기) 목록에 쌓인다.
 *   4. 하단 바의 [완료(N필지 등록)]를 누르면 onPickMany(staged) 콜백이 호출된다.
 *   5. 단일 선택용 onPick(하위호환)도 그대로 지원한다.
 *
 * SSR 안전: dynamicMap(ssr:false)로 감싸서 사용해야 한다(서버 컴포넌트에서 직접 import 금지).
 * 지도 엔진: Leaflet + VWorld WMTS 프록시 (CDN 동적 로드, 새 npm 의존성 없음).
 * 좌표 주의: Leaflet은 [lat, lng] 순, GeoJSON은 [lng, lat] 순이라 변환이 필요하다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import {
  AGE_LEGEND_ITEMS,
  ageColor,
  ageLabel,
  hasSatongLayer,
  hasSatongLayerControl,
  mergeSatongMapFeatures,
  priceColor,
  priceManPyeong,
  pricePyeongOnly,
  resolveVWorldBaseLayer,
  satongMapFeatureKey,
  type SatongMapFeature,
  type SatongMapLayerState,
  type VWorldBaseLayer,
  zoneColor,
} from "@/lib/satong-map-layers";
import { useMapFullscreen } from "@/hooks/useMapFullscreen";

declare global {
  interface Window {
    L: any;
  }
}

/** 백엔드 /zoning/parcel-at-point 응답 형태 */
export interface ParcelAtPointResult {
  found: boolean;
  pnu?: string;
  /** 지번 주소 */
  address?: string;
  jibun?: string;
  /** 법정동 코드(10자리) — PNU 앞 10자리 */
  bcode?: string;
  area_sqm?: number | null;
  zone_type?: string | null;
  jimok?: string | null;
  bcr_pct?: number | null;
  far_pct?: number | null;
  official_price_per_sqm?: number | null;
  built_year?: number | null;
  building_age_years?: number | null;
  /** GeoJSON Polygon/MultiPolygon — 필지 경계 */
  geometry?: any;
  lat?: number;
  lon?: number;
  reason?: string;
}

export interface SatongMultiMapProps {
  /** 단일 필지 선택 콜백 — 하위호환용. onPickMany와 함께 사용 가능 */
  onPick?: (parcel: ParcelAtPointResult) => void;
  /** 다중 필지 선택 완료 콜백 — 완료 버튼 클릭 시 staged 배열 전달 */
  onPickMany?: (parcels: ParcelAtPointResult[]) => void;
  /** 검색으로 확정한 필지 주변을 바로 고를 수 있도록 지도 중심 이동 */
  focusTarget?: { lat: number; lon: number; label?: string } | null;
  /** 검색된 필지를 지도에 자동으로 선택 표시 */
  autoPreviewFocus?: boolean;
  /** 지도 높이(px), 기본 360 */
  height?: number;
  /** 통합 지도 화면에서 외곽 설명/배경을 줄이는 표시 모드 */
  chrome?: "default" | "immersive";
  /** 통합 필지 입력 패널에서 확정된 실제 선택 필지. geometry가 없으면 boundary API로 보강한다. */
  selectedParcels?: SatongMapFeature[];
  /** 오른쪽 사통팔땅 레이어 탭에서 넘어온 지도 반영 상태. */
  layerState?: SatongMapLayerState;
  /** 필지 선택을 끄고 조회된 실데이터를 보기 전용으로 표시한다. */
  readOnly?: boolean;
  /** 주변 실거래/분양 등 시장 데이터 마커를 같은 엔진 위에 표시한다. */
  marketPayload?: SatongMarketPayload | null;
  marketLayer?: SatongMarketLayerState;
  /** 교통·편의 POI(지하철·학교·상권·공원·병원) 마커 — /site-score/poi-infra 응답. */
  poiPayload?: SatongPoiPayload | null;
  /** 주변 도시계획시설(철도·역사 등 개발계획) 마커 — /zoning/development-facilities 응답. */
  developmentPayload?: SatongDevelopmentPayload | null;
  /** 사용자 지도 이동(moveend) 시 현재 중심좌표 통지 — 선택필지 없을 때 지역레이어의 폴백 앵커용. */
  onCenterChange?: (center: { lat: number; lon: number }) => void;
  /** 보기 전용 지도에서 필지 폴리곤/마커 클릭 시 기존 화면과 연동한다. */
  onFeatureClick?: (feature: SatongMapFeature) => void;
  /** 기존 구획도/토지조서 상태색 호환. 키는 주소. */
  featureStatusColors?: Record<string, string>;
  /** 기존 구획도/토지조서 상태 라벨 호환. 키는 주소. */
  featureStatusLabels?: Record<string, string>;
  /** 기존 구획도 하이라이트 주소 호환. */
  highlightFeatureAddress?: string;
}

type BoundaryFeature = {
  pnu: string;
  address: string;
  area_sqm?: number | null;
  zone_type?: string | null;
  zone_type_2?: string | null;
  jimok?: string | null;
  official_price_per_sqm?: number | null;
  built_year?: number | null;
  building_age_years?: number | null;
  geometry?: any;
};

type BoundaryResponse = {
  features?: BoundaryFeature[];
  center?: { lat: number; lon: number } | null;
};

export type SatongMarketDeal = {
  price_10k_won?: number;
  deposit_10k_won?: number;
  monthly_rent_10k_won?: number;
  area_m2?: number;
  floor?: number | string;
  deal_date?: string;
};

export type SatongMarketGroup = {
  name: string;
  dong?: string;
  jibun?: string;
  lat: number;
  lon: number;
  count: number;
  avg_area_m2?: number;
  avg_price_10k?: number;
  avg_deposit_10k?: number;
  avg_monthly_10k?: number;
  deals?: SatongMarketDeal[];
};

export type SatongMarketCategory = {
  label?: string;
  type?: string;
  kind?: string;
  count?: number;
  groups?: SatongMarketGroup[];
};

export type SatongMarketPayload = {
  center: { lat: number | null; lon: number | null; address?: string } | null;
  radius_m?: number;
  categories?: Record<string, SatongMarketCategory>;
  fetch_failed?: boolean;
  note?: string;
};

/** /site-score/poi-infra 응답(부분집합) — 카테고리별 POI 항목(좌표 포함). */
export type SatongPoiItem = {
  name?: string | null;
  distance_m?: number | null;
  lat?: number | null;
  lon?: number | null;
};
export type SatongPoiCategory = {
  label?: string;
  count?: number;
  nearest_m?: number | null;
  items?: SatongPoiItem[];
};
export type SatongPoiPayload = {
  available?: boolean;
  reason?: string;
  coordinates?: { lat?: number | null; lon?: number | null };
  radius_m?: number;
  categories?: Record<string, SatongPoiCategory>;
};

// POI 컨트롤(역·학교·상권·공원·병원) → Kakao Local 카테고리 코드 매핑.
//   백엔드 poi_inventory 수집 코드(SW8 지하철·SC4 학교·MT1 마트·CS2 편의점·BK9 은행·
//   HP8 병원·PM9 약국·PARK 공원 키워드)와 정합 — 미수집 코드는 넣지 않는다(무날조).
const POI_CONTROL_CODES: Record<string, string[]> = {
  station: ["SW8"],
  school: ["SC4"],
  commerce: ["MT1", "CS2", "BK9"],
  park: ["PARK"],
  hospital: ["HP8", "PM9"],
};
// 마커 텍스트 상시노출 정책: 레이어별 마커 수가 이 값 이하일 때만 라벨을 permanent(상시)로 표시.
//   초과(밀집) 시 라벨이 겹쳐 지도를 가리므로 hover 툴팁으로 강등(예: POI 83곳 → hover 유지).
const TOOLTIP_PERMANENT_MAX = 32;

const POI_CONTROL_COLORS: Record<string, string> = {
  station: "#0ea5e9",   // 하늘 — 역
  school: "#8b5cf6",    // 보라 — 학교
  commerce: "#f59e0b",  // 주황 — 상권
  park: "#22c55e",      // 초록 — 공원
  hospital: "#ef4444",  // 빨강 — 병원
};

/** /zoning/development-facilities 응답(부분집합) — 주변 도시계획시설(철도·역사 등). */
export type SatongDevelopmentFacility = {
  type?: string | null;
  name?: string | null;
  status?: string | null;      // '계획'/'결정'/'확인필요' 등 속성 그대로(무날조)
  distance_m?: number | null;
  lat?: number | null;
  lon?: number | null;
};
export type SatongDevelopmentPayload = {
  facilities?: SatongDevelopmentFacility[];
  note?: string;
};

export type SatongPresaleItem = {
  name: string;
  address?: string;
  area_name?: string;
  status?: string;
  receipt_begin?: string;
  receipt_end?: string;
  total_households?: string;
  url?: string;
  lat: number;
  lon: number;
  distance_m?: number;
};

export type SatongAuctionItem = {
  address?: string;
  appraisal_price?: number;
  minimum_bid_price?: number;
  bid_date?: string;
  status?: string;
  url?: string;
  lat: number;
  lon: number;
  distance_m?: number;
};

export type SatongMarketLayerState = {
  kind?: "trade" | "rent";
  type?: string;
  showPresale?: boolean;
  presaleItems?: SatongPresaleItem[] | null;
  showAuction?: boolean;
  auctionItems?: SatongAuctionItem[] | null;
};

/** Leaflet CDN 단일 로딩 (AuctionItemsMap과 동일 패턴) */
let leafletLoading: Promise<void> | null = null;
function loadLeaflet(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.L) return Promise.resolve();
  if (leafletLoading) return leafletLoading;
  leafletLoading = new Promise((resolve, reject) => {
    if (!document.querySelector("link[data-leaflet]")) {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      css.setAttribute("data-leaflet", "1");
      document.head.appendChild(css);
    }
    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Leaflet 로드 실패"));
    document.head.appendChild(script);
  });
  return leafletLoading;
}

function createOfficialBaseMapLayer(
  L: any,
  baseLayer: VWorldBaseLayer,
  onTileState: (state: "ready" | "error") => void,
): any {
  // ★타일은 프론트 서버 프록시(/tiles/vworld) 경유 — (1)API키를 브라우저에 노출하지 않고
  //   (2)위성(Satellite)을 .jpeg로 요청하며 (3)VWorld 200+XML 오류를 투명타일로 흡수한다.
  //   (api.vworld.kr 직접호출은 키노출·위성 png 오류·XML 미처리로 회색지도를 유발하므로 금지.)
  const makeTile = (layerName: string) =>
    L.tileLayer(`/tiles/vworld/wmts/${layerName}/{z}/{y}/{x}.png`, {
      attribution: "VWorld · 국토교통부 공간정보 오픈플랫폼",
      maxZoom: 19,
      crossOrigin: true,
    });

  // ★VWorld의 Hybrid는 단독 베이스가 아니라 '위성영상 위에 얹는 투명 라벨·도로 오버레이'다
  //   (타일 실측: Hybrid=PNG RGBA 투명채널, Base=불투명 팔레트). 단독으로 깔면 밝은 배경에
  //   라벨만 뜨는 유령지도가 됨 → 항공뷰는 Satellite(베이스)+Hybrid(오버레이) 두 장을 합성한다.
  if (baseLayer === "Hybrid") {
    const sat = makeTile("Satellite");
    const overlay = makeTile("Hybrid");
    sat.on("tileload", () => onTileState("ready"));
    sat.on("tileerror", () => onTileState("error"));
    return L.layerGroup([sat, overlay]);
  }

  const vworld = makeTile(baseLayer);
  vworld.on("tileload", () => onTileState("ready"));
  vworld.on("tileerror", () => onTileState("error"));
  return vworld;
}

/**
 * GeoJSON Polygon/MultiPolygon 좌표([lng, lat])를
 * Leaflet 좌표([lat, lng]) 배열의 배열로 변환한다.
 */
function geoJsonToLeafletRings(geometry: any): [number, number][][] {
  if (!geometry) return [];
  const rings: [number, number][][] = [];
  const addRing = (coords: number[][]) => {
    const ring = coords
      .filter((c) => Array.isArray(c) && c.length >= 2)
      // GeoJSON은 [lng, lat]이므로 뒤집는다
      .map(([lng, lat]) => [lat, lng] as [number, number]);
    if (ring.length >= 3) rings.push(ring);
  };
  if (geometry.type === "Polygon") {
    (geometry.coordinates || []).forEach(addRing);
  } else if (geometry.type === "MultiPolygon") {
    (geometry.coordinates || []).forEach((poly: number[][][]) =>
      (poly || []).forEach(addRing),
    );
  }
  return rings;
}

/** ㎡ → 평 변환(소수점 1자리) */
function toP(sqm: number): string {
  return (sqm / 3.305785).toFixed(1);
}

function escapeHtml(value: string | number | null | undefined): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function pointResultToFeature(parcel: ParcelAtPointResult): SatongMapFeature {
  const address = parcel.address || parcel.jibun || parcel.pnu || "지도 선택 필지";
  return {
    id: parcel.pnu || address,
    pnu: parcel.pnu ?? null,
    address,
    lat: parcel.lat ?? null,
    lon: parcel.lon ?? null,
    areaSqm: parcel.area_sqm ?? null,
    zoneType: parcel.zone_type ?? null,
    jimok: parcel.jimok ?? null,
    officialPricePerSqm: parcel.official_price_per_sqm ?? null,
    builtYear: parcel.built_year ?? null,
    buildingAgeYears: parcel.building_age_years ?? null,
    geometry: parcel.geometry,
    source: "map",
  };
}

function boundaryFeatureToMapFeature(feature: BoundaryFeature): SatongMapFeature {
  return {
    id: feature.pnu || feature.address,
    pnu: feature.pnu ?? null,
    address: feature.address || feature.pnu || "필지",
    areaSqm: feature.area_sqm ?? null,
    zoneType: feature.zone_type ?? null,
    zoneType2: feature.zone_type_2 ?? null,
    jimok: feature.jimok ?? null,
    officialPricePerSqm: feature.official_price_per_sqm ?? null,
    builtYear: feature.built_year ?? null,
    buildingAgeYears: feature.building_age_years ?? null,
    geometry: feature.geometry,
    source: "boundary",
  };
}

function featurePopupHtml(feature: SatongMapFeature, statusLabel?: string): string {
  return [
    `<div style="padding:8px 10px;font-size:12px;line-height:1.55;min-width:180px;">`,
    `<b>${escapeHtml(feature.address || feature.pnu || "필지")}</b>${statusLabel ? ` <span style="color:#0e7490">[${escapeHtml(statusLabel)}]</span>` : ""}`,
    feature.zoneType ? `<br/>용도지역: ${escapeHtml(feature.zoneType)}${feature.zoneType2 ? ` / ${escapeHtml(feature.zoneType2)}` : ""}` : "",
    feature.areaSqm ? `<br/>면적: ${Math.round(feature.areaSqm).toLocaleString()}㎡ (${toP(feature.areaSqm)}평)` : "",
    feature.jimok ? `<br/>지목: ${escapeHtml(feature.jimok)}` : "",
    feature.officialPricePerSqm ? `<br/>공시지가: ${escapeHtml(priceManPyeong(feature.officialPricePerSqm))}` : "",
    feature.buildingAgeYears != null ? `<br/>노후도: ${feature.buildingAgeYears}년${feature.builtYear ? ` (${feature.builtYear}년)` : ""}` : "",
    `</div>`,
  ].join("");
}

function won(man?: number): string {
  if (!man || man <= 0) return "-";
  if (man >= 10000) {
    const eok = Math.floor(man / 10000);
    const rest = Math.round((man % 10000) / 1000);
    return rest > 0 ? `${eok}.${rest}억` : `${eok}억`;
  }
  return `${Math.round(man).toLocaleString()}만`;
}

function pyeongFromM2(m2?: number): string {
  return m2 && m2 > 0 ? `${(m2 / 3.305785).toFixed(1)}평` : "-";
}

const MARKET_TYPE_COLORS: Record<string, string> = {
  apt: "#14b8a6",
  villa: "#3b82f6",
  house: "#f59e0b",
  officetel: "#8b5cf6",
  land: "#65a30d",
  commercial: "#ec4899",
};

const PRESALE_STATUS_COLORS: Record<string, string> = {
  분양중: "#ef4444",
  접수중: "#ef4444",
  분양예정: "#0ea5e9",
  접수예정: "#0ea5e9",
  미분양: "#f59e0b",
  분양완료: "#94a3b8",
  마감: "#94a3b8",
  미정: "#64748b",
};

function marketPopupHtml(group: SatongMarketGroup, kind: "trade" | "rent"): string {
  const avgArea = group.avg_area_m2 ?? 0;
  const pyeong = pyeongFromM2(avgArea);
  const priceLine =
    kind === "trade"
      ? `평균 ${won(group.avg_price_10k)} · 평균 ${pyeong}`
      : `보증금 ${won(group.avg_deposit_10k)}${group.avg_monthly_10k ? ` / 월 ${Math.round(group.avg_monthly_10k).toLocaleString()}만` : ""} · 평균 ${pyeong}`;
  const dealRows = (group.deals ?? [])
    .slice(0, 4)
    .map((deal) => {
      const amount =
        kind === "trade"
          ? won(deal.price_10k_won)
          : `${won(deal.deposit_10k_won)}${deal.monthly_rent_10k_won ? `/${Math.round(deal.monthly_rent_10k_won).toLocaleString()}만` : ""}`;
      return `<div style="font-size:11px;color:#475569;">· ${escapeHtml(deal.deal_date || "")} ${escapeHtml(amount)} · ${escapeHtml(pyeongFromM2(deal.area_m2))}${deal.floor ? ` · ${escapeHtml(deal.floor)}층` : ""}</div>`;
    })
    .join("");
  return [
    `<div style="min-width:210px;max-width:280px;padding:8px 10px;font-size:12px;line-height:1.5;">`,
    `<b>${escapeHtml(group.name)}</b>`,
    `<div style="color:#64748b;font-size:11px;">${escapeHtml([group.dong, group.jibun].filter(Boolean).join(" "))} · ${escapeHtml(group.count)}건</div>`,
    `<div style="margin:6px 0;color:#0f172a;">${escapeHtml(priceLine)}</div>`,
    dealRows,
    `</div>`,
  ].join("");
}

function presalePopupHtml(item: SatongPresaleItem): string {
  const status = item.status || "미정";
  const url = item.url && /^https?:\/\//.test(item.url) ? item.url : "";
  return [
    `<div style="min-width:210px;max-width:280px;padding:8px 10px;font-size:12px;line-height:1.5;">`,
    `<b>${escapeHtml(item.name)}</b>`,
    `<div style="color:#64748b;font-size:11px;">${escapeHtml(item.area_name || "")}${item.address ? ` · ${escapeHtml(item.address)}` : ""}</div>`,
    `<div style="margin-top:6px;font-weight:700;color:${escapeHtml(PRESALE_STATUS_COLORS[status] || PRESALE_STATUS_COLORS["미정"])};">분양 · ${escapeHtml(status)}</div>`,
    `<div style="color:#475569;font-size:11px;">접수 ${escapeHtml(item.receipt_begin || "-")} ~ ${escapeHtml(item.receipt_end || "-")}</div>`,
    `<div style="color:#475569;font-size:11px;">공급 ${escapeHtml(item.total_households || "-")}세대${item.distance_m ? ` · ${Math.round(item.distance_m / 100) / 10}km` : ""}</div>`,
    url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-top:6px;color:#2563eb;font-size:11px;font-weight:700;">청약홈 공고 ↗</a>` : "",
    `</div>`,
  ].join("");
}

const AUCTION_STATUS_COLORS: Record<string, string> = {
  "진행": "#ef4444",
  "유찰": "#f59e0b",
  "매각": "#22c55e",
  "종결": "#64748b",
};

function auctionPopupHtml(item: SatongAuctionItem): string {
  const status = item.status || "진행";
  const url = item.url && /^https?:\/\//.test(item.url) ? item.url : "";
  const appraisal = item.appraisal_price ? `${(item.appraisal_price / 100000000).toFixed(1)}억` : "-";
  const minBid = item.minimum_bid_price ? `${(item.minimum_bid_price / 100000000).toFixed(1)}억` : "-";
  return [
    `<div style="min-width:210px;max-width:280px;padding:8px 10px;font-size:12px;line-height:1.5;">`,
    `<b>${escapeHtml(item.address || "경매/공매 물건")}</b>`,
    `<div style="margin-top:6px;font-weight:700;color:${escapeHtml(AUCTION_STATUS_COLORS[status] || AUCTION_STATUS_COLORS["진행"])};">경매 · ${escapeHtml(status)}</div>`,
    `<div style="color:#475569;font-size:11px;">감정가 ${escapeHtml(appraisal)} · 최저가 <span style="color:#ef4444;font-weight:700;">${escapeHtml(minBid)}</span></div>`,
    `<div style="color:#475569;font-size:11px;">입찰일 ${escapeHtml(item.bid_date || "-")}${item.distance_m ? ` · ${Math.round(item.distance_m / 100) / 10}km` : ""}</div>`,
    url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-top:6px;color:#2563eb;font-size:11px;font-weight:700;">상세보기 ↗</a>` : "",
    `</div>`,
  ].join("");
}

// ★기본값 배열을 매 렌더 새로 만들지 않도록 모듈 상수로 고정한다. selectedParcels prop 을
//   생략한 소비처(NearbyTransactionsMap 등)에서 기본값 [] 가 매 렌더 새 참조가 되어, 이를
//   dep 로 쓰는 boundary effect 가 무한 재실행되던 근본(참조 churn)을 차단한다.
const EMPTY_SELECTED_PARCELS: SatongMapFeature[] = [];

export function SatongMultiMap({
  onPick,
  onPickMany,
  focusTarget,
  autoPreviewFocus = false,
  height = 360,
  chrome = "default",
  selectedParcels = EMPTY_SELECTED_PARCELS,
  layerState,
  readOnly = false,
  marketPayload = null,
  marketLayer,
  poiPayload = null,
  developmentPayload = null,
  onCenterChange,
  onFeatureClick,
  featureStatusColors,
  featureStatusLabels,
  highlightFeatureAddress,
}: SatongMultiMapProps) {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const onCenterChangeRef = useRef(onCenterChange);
  onCenterChangeRef.current = onCenterChange;
  const moveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mapRef = useRef<any>(null);
  const {
    isFull: isMapFullscreen,
    toggle: toggleMapFullscreen,
    wrapperClass,
    wrapperRef,
  } = useMapFullscreen(mapRef, { mode: "css" });
  const [mapReady, setMapReady] = useState(false);
  const baseLayerRef = useRef<any>(null);
  const overlayLayerRef = useRef<any>(null);
  const marketLayerRef = useRef<any>(null);
  const poiLayerRef = useRef<any>(null);
  const developmentLayerRef = useRef<any>(null);
  const lastFitKeyRef = useRef("");
  const [tileStatus, setTileStatus] = useState<"idle" | "ready" | "error">("idle");
  const [boundaryStatus, setBoundaryStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [boundaryFeatures, setBoundaryFeatures] = useState<SatongMapFeature[]>([]);
  const [overlayNote, setOverlayNote] = useState("");
  const [marketNote, setMarketNote] = useState("");
  const [poiNote, setPoiNote] = useState("");
  const [developmentNote, setDevelopmentNote] = useState("");

  // 조회 상태
  const [status, setStatus] = useState<"idle" | "loading" | "found" | "notfound" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");

  // 확인 대기 중인 필지(클릭→조회완료, 아직 staged에 안 들어간 상태)
  const [pending, setPending] = useState<ParcelAtPointResult | null>(null);
  // 임시 마커 레이어(pending 상태일 때 지도 위에 표시, 취소/추가 시 제거)
  const pendingLayerRef = useRef<any>(null);

  // staged: 사용자가 [＋추가]로 확정한 필지 목록
  const [staged, setStaged] = useState<ParcelAtPointResult[]>([]);
  // staged 필지별 폴리곤 레이어 — pnu → Leaflet layerGroup
  const stagedLayersRef = useRef<Map<string, any>>(new Map());

  // 콜백 ref — useEffect 클로저에서 최신 onPick/onPickMany를 참조하기 위함
  const onPickRef = useRef(onPick);
  const onPickManyRef = useRef(onPickMany);
  const focusTargetRef = useRef(focusTarget);
  const focusLat = focusTarget?.lat ?? null;
  const focusLon = focusTarget?.lon ?? null;
  // staged를 ref로도 보관 — queryParcel이 staged를 의존하지 않게 해 지도 재생성(폴리곤 소실)을 막는다.
  const stagedRef = useRef<ParcelAtPointResult[]>([]);

  // 연타 응답 경합 가드: 마지막 클릭만 반영(stale 필지 폐기)
  const querySeqRef = useRef(0);
  const lastAutoFocusKeyRef = useRef("");
  const selectedParcelKey = useMemo(
    () =>
      selectedParcels
        .map((parcel) => parcel.pnu || parcel.address || parcel.id)
        .filter(Boolean)
        .join("||"),
    [selectedParcels],
  );
  const baseLayerMode = useMemo(() => resolveVWorldBaseLayer(layerState), [layerState]);
  const overlayFeatures = useMemo(
    () => mergeSatongMapFeatures([
      ...boundaryFeatures,
      ...staged.map(pointResultToFeature),
      ...(pending?.found ? [pointResultToFeature(pending)] : []),
    ]),
    [boundaryFeatures, pending, staged],
  );
  const priceRange = useMemo(() => {
    const prices = overlayFeatures
      .map((feature) => feature.officialPricePerSqm ?? 0)
      .filter((price) => price > 0);
    return prices.length ? { min: Math.min(...prices), max: Math.max(...prices) } : { min: 0, max: 0 };
  }, [overlayFeatures]);

  useEffect(() => {
    onPickRef.current = onPick;
  }, [onPick]);

  useEffect(() => {
    onPickManyRef.current = onPickMany;
  }, [onPickMany]);

  useEffect(() => {
    stagedRef.current = staged;
  }, [staged]);

  useEffect(() => {
    focusTargetRef.current = focusTarget;
  }, [focusTarget]);

  /* eslint-disable react-hooks/set-state-in-effect -- VWorld boundary fetch status is synchronized from an external API effect. */
  useEffect(() => {
    if (!selectedParcels.length) {
      // ★빈 선택 시 boundaryFeatures/status 를 '변화가 있을 때만' 갱신한다. 매번 새 [] 를
      //   setState 하면 참조가 바뀌어 불필요 리렌더가 발생한다(무한 업데이트 방지).
      setBoundaryFeatures((prev) => (prev.length ? [] : prev));
      setBoundaryStatus((prev) => (prev === "idle" ? prev : "idle"));
      return;
    }
    const hasAllGeometry = selectedParcels.every((parcel) => !!parcel.geometry);
    if (hasAllGeometry) {
      setBoundaryFeatures(mergeSatongMapFeatures(selectedParcels));
      setBoundaryStatus("ready");
      return;
    }
    let alive = true;
    setBoundaryStatus("loading");
    apiClient
      .post<BoundaryResponse>("/zoning/parcel-boundaries", {
        body: {
          parcels: selectedParcels.map((parcel) => ({
            pnu: parcel.pnu,
            address: parcel.address,
          })),
        },
        useMock: false,
        timeoutMs: 45000,
      })
      .then((response) => {
        if (!alive) return;
        const fromBoundary = (response.features ?? []).map(boundaryFeatureToMapFeature);
        setBoundaryFeatures(mergeSatongMapFeatures([...selectedParcels, ...fromBoundary]));
        setBoundaryStatus("ready");
      })
      .catch(() => {
        if (!alive) return;
        setBoundaryFeatures(mergeSatongMapFeatures(selectedParcels));
        setBoundaryStatus("error");
      });
    return () => {
      alive = false;
    };
  }, [selectedParcelKey, selectedParcels]);
  /* eslint-enable react-hooks/set-state-in-effect */

  /** pending 레이어(임시 마커·폴리곤) 지도에서 제거 */
  const clearPendingLayer = useCallback(() => {
    if (pendingLayerRef.current) {
      try { pendingLayerRef.current.remove(); } catch { /* noop */ }
      pendingLayerRef.current = null;
    }
  }, []);

  /** staged 특정 필지의 폴리곤 레이어 지도에서 제거 */
  const removeStagedLayer = useCallback((pnu: string) => {
    const layer = stagedLayersRef.current.get(pnu);
    if (layer) {
      try { layer.remove(); } catch { /* noop */ }
      stagedLayersRef.current.delete(pnu);
    }
  }, []);

  /** staged 모든 폴리곤 레이어 지도에서 제거 */
  const clearAllStagedLayers = useCallback(() => {
    stagedLayersRef.current.forEach((layer) => {
      try { layer.remove(); } catch { /* noop */ }
    });
    stagedLayersRef.current.clear();
  }, []);

  /**
   * staged 필지를 '선택됨' 녹색 폴리곤으로 지도에 고정 표시.
   * 이미 레이어가 있으면 건너뛴다.
   */
  const addStagedLayer = useCallback((parcel: ParcelAtPointResult) => {
    const map = mapRef.current;
    const L = window.L;
    if (!map || !L || !parcel.pnu) return;
    if (stagedLayersRef.current.has(parcel.pnu)) return; // 이미 표시됨

    const layer = L.layerGroup().addTo(map);

    // 선택됨 — 녹색 폴리곤
    if (parcel.geometry) {
      const rings = geoJsonToLeafletRings(parcel.geometry);
      if (rings.length > 0) {
        L.polygon(rings, {
          color: "#22c55e", weight: 2.5, fillColor: "#22c55e", fillOpacity: 0.28,
        }).addTo(layer);
      }
    }

    // 중심 마커(녹색)
    if (parcel.lat != null && parcel.lon != null) {
      L.circleMarker([parcel.lat, parcel.lon], {
        radius: 7, color: "#22c55e", weight: 2.5, fillColor: "#22c55e", fillOpacity: 0.9,
      }).addTo(layer);
    }

    stagedLayersRef.current.set(parcel.pnu, layer);
  }, []);

  /** 클릭한 좌표로 필지를 조회하고 결과를 pending 상태로 둔다 */
  const queryParcel = useCallback(async (lat: number, lon: number, opts: { autoStage?: boolean } = {}) => {
    const seq = ++querySeqRef.current;
    setStatus("loading");
    setStatusMsg("필지 조회 중…");
    setPending(null);
    clearPendingLayer();

    const L = window.L;
    const map = mapRef.current;
    if (!map) return;

    // 클릭 위치에 임시 파란 마커 표시(조회 중 피드백)
    const tempMarker = L.circleMarker([lat, lon], {
      radius: 6, color: "#3b82f6", weight: 2, fillColor: "#3b82f6", fillOpacity: 0.5,
    }).addTo(map);

    let result: ParcelAtPointResult;
    try {
      result = await apiClient.post<ParcelAtPointResult>(
        "/zoning/parcel-at-point",
        { body: { lat, lon }, useMock: false, timeoutMs: 20000 },
      );
    } catch {
      tempMarker.remove();
      if (seq !== querySeqRef.current) return; // 더 새로운 클릭이 있었으면 무시
      setStatus("error");
      setStatusMsg("조회 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
      return;
    }

    tempMarker.remove();
    if (seq !== querySeqRef.current) return; // stale 응답 폐기(연타 시 마지막 클릭만 반영)

    if (!result.found) {
      // 클릭 지점에서 필지를 못 찾은 경우 — 정직하게 안내(가짜 생성 없음)
      const msg = result.reason || "클릭 지점에서 필지를 찾지 못했습니다. 건물 내부나 지적도 제공 구역을 클릭해 주세요.";
      setStatus("notfound");
      setStatusMsg(msg);
      // 클릭 위치에 빨간 'X' 마커로 미확인 표시
      const notFoundLayer = L.layerGroup().addTo(map);
      L.circleMarker([lat, lon], {
        radius: 7, color: "#ef4444", weight: 2, fillColor: "#ef4444", fillOpacity: 0.3,
      }).bindPopup(`<div style="font-size:12px;max-width:200px;">${msg}</div>`, { maxWidth: 220 }).openPopup().addTo(notFoundLayer);
      pendingLayerRef.current = notFoundLayer;
      return;
    }

    // 이미 staged에 있는 필지인지 확인(ref로 읽어 deps 오염 방지)
    const alreadyStaged = stagedRef.current.some((s) => s.pnu && s.pnu === result.pnu);

    setStatus("found");
    setStatusMsg("");
    // lat/lon 정보 보완(확인 카드·staged 레이어에서 좌표 재사용)
    result.lat = lat;
    result.lon = lon;

    if (opts.autoStage) {
      if (!alreadyStaged) {
        setStaged((prev) => {
          if (result.pnu && prev.some((s) => s.pnu === result.pnu)) return prev;
          return [...prev, result];
        });
        addStagedLayer(result);
      }
      clearPendingLayer();
      setPending(null);
      setStatus("idle");
      setStatusMsg("");
      return;
    }

    setPending(result);

    // 임시 pending 레이어 표시(파란 폴리곤 + 마커)
    const layer = L.layerGroup().addTo(map);
    pendingLayerRef.current = layer;

    if (result.geometry && !alreadyStaged) {
      const rings = geoJsonToLeafletRings(result.geometry);
      if (rings.length > 0) {
        const poly = L.polygon(rings, {
          color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.22,
        }).addTo(layer);
        // 폴리곤 경계에 맞춰 지도 이동
        try { map.fitBounds(poly.getBounds(), { padding: [40, 40], maxZoom: 17 }); } catch { /* noop */ }
      }
    }

    // 중심점 마커(폴리곤 없을 때도 위치 표시)
    L.circleMarker([lat, lon], {
      radius: 7, color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.8,
    }).addTo(layer);

    // 하위호환: 단일 모드(onPick만, onPickMany 없음)에서만 즉시 호출.
    // 다중 모드(onPickMany 존재)에선 확인 카드 [＋추가] 승인 흐름을 거쳐야 하므로 즉시 호출하지 않는다.
    if (onPickRef.current && !onPickManyRef.current) {
      onPickRef.current(result);
    }
  }, [addStagedLayer, clearPendingLayer]);

  /** [＋추가] 버튼: pending 필지를 staged에 넣고 녹색 폴리곤으로 고정 */
  const handleConfirmAdd = useCallback(() => {
    if (!pending || !pending.found) return;
    const pnu = pending.pnu;

    // 같은 pnu 중복 방지
    if (pnu && staged.some((s) => s.pnu === pnu)) {
      clearPendingLayer();
      setPending(null);
      setStatus("idle");
      return;
    }

    setStaged((prev) => [...prev, pending]);
    // pending 레이어 제거 후 staged 녹색 레이어 고정
    clearPendingLayer();
    addStagedLayer(pending);
    setPending(null);
    setStatus("idle");
  }, [pending, staged, clearPendingLayer, addStagedLayer]);

  /** [취소] 버튼: pending 상태 취소(임시 마커·폴리곤 제거) */
  const handleCancelPending = useCallback(() => {
    clearPendingLayer();
    setPending(null);
    setStatus("idle");
  }, [clearPendingLayer]);

  /** [제거] 버튼: 이미 staged된 필지를 목록과 지도에서 제거 */
  const handleRemoveStaged = useCallback((pnu: string) => {
    setStaged((prev) => prev.filter((s) => s.pnu !== pnu));
    removeStagedLayer(pnu);
    clearPendingLayer();
    setPending(null);
    setStatus("idle");
  }, [removeStagedLayer, clearPendingLayer]);

  /** [전체취소] 버튼: staged 전부 제거 */
  const handleClearAll = useCallback(() => {
    setStaged([]);
    clearAllStagedLayers();
    clearPendingLayer();
    setPending(null);
    setStatus("idle");
  }, [clearAllStagedLayers, clearPendingLayer]);

  /** [완료(N필지 등록)] 버튼: onPickMany 콜백 호출 */
  const handleComplete = useCallback(() => {
    if (staged.length === 0) return;
    onPickManyRef.current?.(staged);
  }, [staged]);

  // Leaflet 지도 초기화 (컴포넌트 마운트 시 1회)
  useEffect(() => {
    let alive = true;
    const stagedLayers = stagedLayersRef.current;
    loadLeaflet()
      .then(() => {
        if (!alive || !mapEl.current || mapRef.current) return;
        const L = window.L;
        // 서울 중심으로 초기화, 스크롤 줌 활성
        const map = L.map(mapEl.current, {
          center: [37.5665, 126.978],
          zoom: 12,
          scrollWheelZoom: true,
          attributionControl: false,
        });
        L.control.attribution({ prefix: false, position: "bottomright" })
          .addTo(map)
          .addAttribution("VWorld · 국토교통부 공간정보 오픈플랫폼");
        mapRef.current = map;
        setMapReady(true);
        const focus = focusTargetRef.current;
        if (focus) {
          map.setView([focus.lat, focus.lon], 17);
        }

        // 지도 클릭 → 필지 조회
        map.on("click", (e: any) => {
          if (readOnly) return;
          void queryParcel(e.latlng.lat, e.latlng.lng);
        });

        // 지도 이동 완료 → 현재 중심 통지(선택필지 없을 때 지역레이어 폴백 앵커). 디바운스+
        //   좌표 반올림(4자리≈11m)으로 미세 이동/프로그램적 fitBounds에 의한 재조회 폭주를 억제.
        //   ★타이머는 ref로 관리해 언마운트 cleanup에서 해제(리뷰 LOW — setTimeout 누수 방지).
        let lastCenterKey = "";
        map.on("moveend", () => {
          if (moveTimerRef.current) clearTimeout(moveTimerRef.current);
          moveTimerRef.current = setTimeout(() => {
            const cb = onCenterChangeRef.current;
            if (!cb) return;
            const c = map.getCenter();
            const lat = Math.round(c.lat * 1e4) / 1e4;
            const lon = Math.round(c.lng * 1e4) / 1e4;
            const key = `${lat},${lon}`;
            if (key === lastCenterKey) return;
            lastCenterKey = key;
            cb({ lat, lon });
          }, 500);
        });
      })
      .catch(() => {
        setStatus("error");
        setStatusMsg("지도 로딩에 실패했습니다.");
      });

    return () => {
      alive = false;
      if (moveTimerRef.current) { clearTimeout(moveTimerRef.current); moveTimerRef.current = null; }
      if (mapRef.current) {
        try { mapRef.current.remove(); } catch { /* noop */ }
        mapRef.current = null;
      }
      baseLayerRef.current = null;
      overlayLayerRef.current = null;
      marketLayerRef.current = null;
      setMapReady(false);
      // staged 레이어 맵도 초기화(지도가 사라지면 참조 불필요)
      stagedLayers.clear();
      leafletLoading = null; // 다음 마운트에서 재로딩 가능하도록 초기화
    };
  }, [queryParcel, readOnly]);

  /* eslint-disable react-hooks/set-state-in-effect -- Tile loading status comes from Leaflet/VWorld tile lifecycle. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;
    if (baseLayerRef.current) {
      try { map.removeLayer(baseLayerRef.current); } catch { /* noop */ }
      baseLayerRef.current = null;
    }
    setTileStatus("idle");
    const layer = createOfficialBaseMapLayer(L, baseLayerMode, setTileStatus).addTo(map);
    layer.bringToBack?.();
    baseLayerRef.current = layer;
    return () => {
      try { map.removeLayer(layer); } catch { /* noop */ }
      if (baseLayerRef.current === layer) baseLayerRef.current = null;
    };
  }, [baseLayerMode, mapReady]);

  // VWorld 연속지적도 전체 오버레이 타일 (showCadastre 활성화 시 지도 전체 렌더)
  const cadastreTileRef = useRef<any>(null);
  const showCadastreTile = hasSatongLayer(layerState, "cadastre");

  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (cadastreTileRef.current) {
      try { map.removeLayer(cadastreTileRef.current); } catch { /* noop */ }
      cadastreTileRef.current = null;
    }

    if (showCadastreTile) {
      const apiKey = process.env.NEXT_PUBLIC_VWORLD_API_KEY || "E98ECD12-DB7F-3993-B043-E34B03229126";
      const cadastreLayer = L.tileLayer.wms("https://api.vworld.kr/req/wms", {
        layers: "LP_PA_CBND_BUDB,LP_PA_CBND_BONB",
        styles: "LP_PA_CBND_BUDB,LP_PA_CBND_BONB",
        format: "image/png",
        transparent: true,
        maxZoom: 19,
        minZoom: 10,
        key: apiKey,
        domain: "www.4t8t.net",
        attribution: "VWorld 연속지적도",
      }).addTo(map);
      cadastreTileRef.current = cadastreLayer;
    }

    return () => {
      if (cadastreTileRef.current) {
        try { map.removeLayer(cadastreTileRef.current); } catch { /* noop */ }
        cadastreTileRef.current = null;
      }
    };
  }, [mapReady, showCadastreTile]);
  /* eslint-enable react-hooks/set-state-in-effect */

  /* eslint-disable react-hooks/set-state-in-effect -- Overlay notes are derived from imperative Leaflet layer rendering. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (overlayLayerRef.current) {
      try { overlayLayerRef.current.remove(); } catch { /* noop */ }
      overlayLayerRef.current = null;
    }

    const showCadastre = hasSatongLayer(layerState, "cadastre");
    const showZoning = hasSatongLayer(layerState, "zoning") && hasSatongLayerControl(layerState, "zoning", "land-use");
    const showPrice = hasSatongLayer(layerState, "official-price") && hasSatongLayerControl(layerState, "official-price", "unit-price");
    const showAge = hasSatongLayer(layerState, "age") && hasSatongLayerControl(layerState, "age", "building-age");
    const needsOverlay = showCadastre || showZoning || showPrice || showAge;

    if (!needsOverlay || overlayFeatures.length === 0) {
      // ★레이어는 켜졌는데 그릴 필지가 0 → 침묵 blank 대신 명확 안내(활성배지-무반영 모순 해소).
      setOverlayNote(needsOverlay ? "필지를 선택하면 레이어가 지도에 표시됩니다" : "");
      return;
    }

    const group = L.layerGroup().addTo(map);
    overlayLayerRef.current = group;
    const bounds = L.latLngBounds([]);
    let cadastreCount = 0;
    let zoningCount = 0;
    let priceCount = 0;
    let ageCount = 0;
    let markerCount = 0;

    overlayFeatures.forEach((feature, index) => {
      const rings = geoJsonToLeafletRings(feature.geometry);
      const hasGeometry = rings.length > 0;
      const statusColor = featureStatusColors?.[feature.address];
      const statusLabel = featureStatusLabels?.[feature.address];
      const isHighlighted = !!highlightFeatureAddress && feature.address === highlightFeatureAddress;
      const popup = featurePopupHtml(feature, statusLabel);

	    const drawPolygon = (style: Record<string, unknown>) => {
	      if (!hasGeometry) return;
        const resolvedStyle = {
          ...style,
          ...(statusColor ? { color: statusColor, fillColor: statusColor } : {}),
          ...(isHighlighted ? { color: "#ef4444", weight: 4, fillOpacity: 0.5 } : {}),
        };
	      const polygon = L.polygon(rings, resolvedStyle).bindPopup(popup, { maxWidth: 280 }).addTo(group);
        polygon.on("click", () => onFeatureClick?.(feature));
	      try { bounds.extend(polygon.getBounds()); } catch { /* noop */ }
	    };

	    if (showCadastre && hasGeometry) {
	      cadastreCount += 1;
	      drawPolygon({
          color: "#14532d",
          weight: 2,
          fillColor: "#22c55e",
          fillOpacity: showZoning || showPrice || showAge ? 0.08 : 0.18,
          dashArray: feature.source === "boundary" ? undefined : "4 4",
        });
      }

      if (showZoning && hasGeometry && feature.zoneType) {
        zoningCount += 1;
        const color = zoneColor(feature.zoneType, index);
        drawPolygon({
          color,
          weight: 2.5,
          fillColor: color,
          fillOpacity: 0.34,
        });
      }

      if (showPrice && hasGeometry && feature.officialPricePerSqm) {
        priceCount += 1;
        const color = priceColor(feature.officialPricePerSqm, priceRange.min, priceRange.max);
        drawPolygon({
          color,
          weight: 2.5,
          fillColor: color,
          fillOpacity: 0.42,
        });
      }

      if (showAge && hasGeometry && feature.buildingAgeYears != null) {
        ageCount += 1;
        const color = ageColor(feature.buildingAgeYears);
        drawPolygon({
          color,
          weight: 2.5,
          fillColor: color,
          fillOpacity: 0.55,
        });
      }

      if (!hasGeometry && feature.lat != null && feature.lon != null) {
        markerCount += 1;
        L.circleMarker([feature.lat, feature.lon], {
          radius: 8,
          color: "#1d4ed8",
          weight: 2,
          fillColor: "#bfdbfe",
          fillOpacity: 0.95,
        }).bindPopup(popup, { maxWidth: 280 }).on("click", () => onFeatureClick?.(feature)).addTo(group);
        bounds.extend([feature.lat, feature.lon]);
      }
    });

	    const notes: string[] = [];
	    if (cadastreCount) notes.push(`지적 ${cadastreCount}건`);
    if (showZoning) notes.push(zoningCount ? `용도지역 ${zoningCount}건` : "용도지역 무자료");
    if (showPrice) notes.push(priceCount ? `공시지가 ${priceCount}건` : "공시지가 무자료");
    if (showAge) notes.push(ageCount ? `노후도 ${ageCount}건` : "노후도 무자료");
    if (markerCount) notes.push(`좌표 ${markerCount}건`);
    setOverlayNote(notes.join(" · "));

    const fitKey = overlayFeatures.map(satongMapFeatureKey).join("||");
    if (fitKey && fitKey !== lastFitKeyRef.current && bounds.isValid()) {
      lastFitKeyRef.current = fitKey;
      try { map.fitBounds(bounds, { padding: [36, 36], maxZoom: 17 }); } catch { /* noop */ }
    }

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (overlayLayerRef.current === group) overlayLayerRef.current = null;
	    };
	  }, [
    featureStatusColors,
    featureStatusLabels,
    highlightFeatureAddress,
    layerState,
    mapReady,
    onFeatureClick,
    overlayFeatures,
    priceRange.max,
    priceRange.min,
  ]);
  /* eslint-enable react-hooks/set-state-in-effect */

  /* eslint-disable react-hooks/set-state-in-effect -- Market markers are rendered into an imperative Leaflet layer group. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (marketLayerRef.current) {
      try { marketLayerRef.current.remove(); } catch { /* noop */ }
      marketLayerRef.current = null;
    }

    if (!marketPayload?.center?.lat || !marketPayload.center.lon || marketPayload.fetch_failed) {
      setMarketNote(marketPayload?.fetch_failed ? marketPayload.note || "실거래 공공데이터 조회 실패" : "");
      return;
    }

    const group = L.layerGroup().addTo(map);
    marketLayerRef.current = group;
    const bounds = L.latLngBounds([]);
    const kind = marketLayer?.kind ?? "trade";
    const type = marketLayer?.type ?? "apt";
    const category = marketPayload.categories?.[`${type}_${kind}`];
    const groups = category?.groups ?? [];
    const typeColor = MARKET_TYPE_COLORS[type] || "#2563eb";
    let marketCount = 0;
    let presaleCount = 0;

    bounds.extend([marketPayload.center.lat, marketPayload.center.lon]);
    L.circleMarker([marketPayload.center.lat, marketPayload.center.lon], {
      radius: 9,
      color: "#ef4444",
      weight: 3,
      fillColor: "#ffffff",
      fillOpacity: 0.95,
    })
      .bindPopup(`<div style="padding:8px 10px;font-size:12px;"><b>분석 대상지</b><br/>${escapeHtml(marketPayload.center.address || "")}</div>`)
      .addTo(group);

    if (marketPayload.radius_m) {
      L.circle([marketPayload.center.lat, marketPayload.center.lon], {
        radius: marketPayload.radius_m,
        color: "#14b8a6",
        weight: 2,
        opacity: 0.85,
        fillColor: "#14b8a6",
        fillOpacity: 0.05,
        dashArray: "6 6",
      }).addTo(group);
    }

    groups.forEach((item) => {
      if (!item.lat || !item.lon) return;
      marketCount += 1;
      const radius = Math.min(18, 7 + Math.round(Math.sqrt(Math.max(1, item.count)) * 1.5));
      L.circleMarker([item.lat, item.lon], {
        radius,
        color: "#ffffff",
        weight: 2,
        fillColor: typeColor,
        fillOpacity: 0.9,
      })
        .bindTooltip(`<div class="font-bold text-[10.5px] bg-white/95 px-2 py-1 rounded shadow-sm border border-slate-200">${escapeHtml(item.name || "실거래")}</div>`, { permanent: groups.filter((g) => g.lat && g.lon).length <= TOOLTIP_PERMANENT_MAX, direction: "top", offset: [0, -radius], className: "bg-transparent border-none shadow-none" })
        .bindPopup(marketPopupHtml(item, kind), { maxWidth: 300 })
        .addTo(group);
      bounds.extend([item.lat, item.lon]);
    });

    if (marketLayer?.showPresale) {
      (marketLayer.presaleItems ?? []).forEach((item) => {
        if (!item.lat || !item.lon) return;
        presaleCount += 1;
        const status = item.status || "미정";
        const color = PRESALE_STATUS_COLORS[status] || PRESALE_STATUS_COLORS["미정"];
        const icon = L.divIcon({
          className: "",
          html: `<div style="width:18px;height:18px;border-radius:5px;background:${escapeHtml(color)};border:2px solid #fff;box-shadow:0 4px 12px rgba(15,23,42,.28);transform:rotate(45deg);"></div>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        });
        L.marker([item.lat, item.lon], { icon })
          .bindTooltip(`<div class="font-bold text-[10.5px] bg-white/95 px-2 py-1 rounded shadow-sm border border-slate-200">${escapeHtml(item.name || "분양")}</div>`, { permanent: (marketLayer?.presaleItems?.length ?? 0) <= TOOLTIP_PERMANENT_MAX, direction: "top", offset: [0, -11], className: "bg-transparent border-none shadow-none" })
          .bindPopup(presalePopupHtml(item), { maxWidth: 300 })
          .addTo(group);
        bounds.extend([item.lat, item.lon]);
      });
    }

    let auctionCount = 0;
    if (marketLayer?.showAuction) {
      (marketLayer.auctionItems ?? []).forEach((item) => {
        if (!item.lat || !item.lon) return;
        auctionCount += 1;
        const status = item.status || "진행";
        const color = AUCTION_STATUS_COLORS[status] || AUCTION_STATUS_COLORS["진행"];
        const icon = L.divIcon({
          className: "",
          html: `<div style="width:20px;height:20px;border-radius:10px;background:${escapeHtml(color)};border:2px solid #fff;box-shadow:0 4px 12px rgba(15,23,42,.28);display:flex;align-items:center;justify-content:center;"><span style="color:#fff;font-size:10px;font-weight:900;">경</span></div>`,
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        });
        L.marker([item.lat, item.lon], { icon })
          .bindTooltip(`<div class="font-bold text-[10.5px] bg-white/95 px-2 py-1 rounded shadow-sm border border-slate-200">경매물건</div>`, { permanent: (marketLayer?.auctionItems?.length ?? 0) <= TOOLTIP_PERMANENT_MAX, direction: "top", offset: [0, -12], className: "bg-transparent border-none shadow-none" })
          .bindPopup(auctionPopupHtml(item), { maxWidth: 300 })
          .addTo(group);
        bounds.extend([item.lat, item.lon]);
      });
    }

    const notes = [
      marketCount ? `실거래 ${marketCount}곳` : "실거래 무자료",
      marketLayer?.showPresale ? (presaleCount ? `분양 ${presaleCount}곳` : "분양 무자료") : "",
      marketLayer?.showAuction ? (auctionCount ? `경매 ${auctionCount}곳` : "경매 무자료") : "",
    ].filter(Boolean);
    setMarketNote(notes.join(" · "));

    // ★선택필지가 있을 때만 fitBounds(선택 대상지로 이동). 선택 없이 지도중심으로 탐색(브라우즈
    //   모드)할 땐 fitBounds 금지 — 사용자가 보던 화면을 유지하고, moveend→재조회 루프를 끊는다.
    if (bounds.isValid() && selectedParcels.length > 0) {
      try { map.fitBounds(bounds, { padding: [44, 44], maxZoom: 15 }); } catch { /* noop */ }
    }

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (marketLayerRef.current === group) marketLayerRef.current = null;
    };
  }, [mapReady, marketLayer, marketPayload]);
  /* eslint-enable react-hooks/set-state-in-effect */

  /* eslint-disable react-hooks/set-state-in-effect -- POI markers are rendered into an imperative Leaflet layer group. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (poiLayerRef.current) {
      try { poiLayerRef.current.remove(); } catch { /* noop */ }
      poiLayerRef.current = null;
    }

    if (!poiPayload) {
      setPoiNote("");
      return;
    }
    if (poiPayload.available === false) {
      // 키 미설정/조회 실패 — 정직 표기(가짜 마커 금지).
      setPoiNote(poiPayload.reason || "POI 조회 불가");
      return;
    }

    const cats = poiPayload.categories || {};
    const group = L.layerGroup().addTo(map);
    poiLayerRef.current = group;
    let poiCount = 0;

    // 상시라벨 여부 — 켜진 컨트롤의 유효(좌표有) 마커 총수 기준(밀집 시 hover 강등).
    let poiTotalForLabel = 0;
    for (const [control, codes] of Object.entries(POI_CONTROL_CODES)) {
      if (!hasSatongLayerControl(layerState, "poi", control)) continue;
      for (const code of codes) {
        poiTotalForLabel += (cats[code]?.items || []).filter(
          (item) => typeof item.lat === "number" && typeof item.lon === "number",
        ).length;
      }
    }
    const poiPermanent = poiTotalForLabel <= TOOLTIP_PERMANENT_MAX;

    // 컨트롤(역·학교·상권·공원·병원)별로 켜진 것만 렌더 — 컨트롤 상태는 layerState가 SSOT.
    for (const [control, codes] of Object.entries(POI_CONTROL_CODES)) {
      if (!hasSatongLayerControl(layerState, "poi", control)) continue;
      const color = POI_CONTROL_COLORS[control] || "#0ea5e9";
      for (const code of codes) {
        const items = cats[code]?.items || [];
        const label = cats[code]?.label || code;
        for (const item of items) {
          if (typeof item.lat !== "number" || typeof item.lon !== "number") continue;
          poiCount += 1;
          L.circleMarker([item.lat, item.lon], {
            radius: 5,
            color,
            weight: 2,
            fillColor: "#ffffff",
            fillOpacity: 0.9,
          })
            .bindTooltip(`<div class="font-bold text-[10.5px] bg-white/95 px-2 py-1 rounded shadow-sm border border-slate-200">${escapeHtml(item.name || label)}</div>`, { permanent: poiPermanent, direction: "top", offset: [0, -5], className: "bg-transparent border-none shadow-none" })
            .bindPopup(
              `<div style="padding:6px 9px;font-size:12px;line-height:1.5;">` +
                `<b>${escapeHtml(item.name || label)}</b>` +
                `<br/>${escapeHtml(label)}${item.distance_m != null ? ` · ${Math.round(item.distance_m).toLocaleString()}m` : ""}` +
                `</div>`,
              { maxWidth: 260 },
            )
            .addTo(group);
        }
      }
    }
    setPoiNote(poiCount ? `POI ${poiCount}곳` : "POI 무자료");

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (poiLayerRef.current === group) poiLayerRef.current = null;
    };
  }, [mapReady, poiPayload, layerState]);
  /* eslint-enable react-hooks/set-state-in-effect */

  /* eslint-disable react-hooks/set-state-in-effect -- Development-facility markers are rendered into an imperative Leaflet layer group. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (developmentLayerRef.current) {
      try { developmentLayerRef.current.remove(); } catch { /* noop */ }
      developmentLayerRef.current = null;
    }

    if (!developmentPayload) {
      setDevelopmentNote("");
      return;
    }

    const facilities = developmentPayload.facilities || [];
    const group = L.layerGroup().addTo(map);
    developmentLayerRef.current = group;
    let devCount = 0;
    // 상시라벨 여부 — 유효(좌표有) 시설 수 기준(밀집 시 hover 강등, 예: 67건 → hover).
    const devPermanent =
      facilities.filter((fac) => typeof fac.lat === "number" && typeof fac.lon === "number").length <=
      TOOLTIP_PERMANENT_MAX;
    for (const fac of facilities) {
      if (typeof fac.lat !== "number" || typeof fac.lon !== "number") continue;
      devCount += 1;
      L.circleMarker([fac.lat, fac.lon], {
        radius: 6,
        color: "#7c3aed",       // 보라 — 개발계획(도시계획시설)
        weight: 2,
        fillColor: "#ede9fe",
        fillOpacity: 0.9,
      })
        .bindTooltip(`<div class="font-bold text-[10.5px] bg-white/95 px-2 py-1 rounded shadow-sm border border-slate-200">${escapeHtml(fac.name || "개발계획")}</div>`, { permanent: devPermanent, direction: "top", offset: [0, -6], className: "bg-transparent border-none shadow-none" })
        .bindPopup(
          `<div style="padding:6px 9px;font-size:12px;line-height:1.5;">` +
            `<b>${escapeHtml(fac.name || "(명칭 미상)")}</b>` +
            `<br/>${escapeHtml(fac.type || "도시계획시설")} · ${escapeHtml(fac.status || "확인필요")}` +
            `${fac.distance_m != null ? `<br/>거리 ${Math.round(fac.distance_m).toLocaleString()}m` : ""}` +
            `</div>`,
          { maxWidth: 260 },
        )
        .addTo(group);
    }
    // 좌표 미상 시설(마커 불가)도 정직 집계 — 목록엔 있으나 지도에 못 찍는 건수를 구분 고지.
    const noCoord = facilities.length - devCount;
    if (facilities.length === 0) {
      setDevelopmentNote(developmentPayload.note || "개발계획 무자료");
    } else {
      setDevelopmentNote(`개발계획 ${devCount}건${noCoord > 0 ? ` (좌표미상 ${noCoord}건 제외)` : ""}`);
    }

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (developmentLayerRef.current === group) developmentLayerRef.current = null;
    };
  }, [mapReady, developmentPayload]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    const map = mapRef.current;
    if (!map || focusLat == null || focusLon == null) return;
    map.setView([focusLat, focusLon], 17, { animate: true });
    if (readOnly || !autoPreviewFocus) return;
    const key = `${focusLat.toFixed(7)},${focusLon.toFixed(7)}`;
    if (lastAutoFocusKeyRef.current === key) return;
    lastAutoFocusKeyRef.current = key;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Auto-preview intentionally queries parcel data after focusing the imperative map.
    void queryParcel(focusLat, focusLon, { autoStage: true });
  }, [autoPreviewFocus, focusLat, focusLon, queryParcel, readOnly]);

  // staged 합산 면적 계산
  const totalAreaSqm = staged.reduce((acc, p) => acc + (p.area_sqm ?? 0), 0);

  // pending이 이미 staged에 있는지 여부(확인 카드 표시용)
  const pendingAlreadyStaged = pending?.pnu
    ? staged.some((s) => s.pnu === pending.pnu)
    : false;

  return (
    <div
      className={
        chrome === "immersive"
          ? "flex flex-col gap-2"
          : "flex flex-col gap-2 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-3"
      }
    >
      {/* 안내 메시지 */}
      {chrome === "default" && !readOnly && (
        <p className="text-[11px] font-semibold text-[var(--text-secondary)]">
          지도를 클릭하면 해당 필지가 확인 카드로 표시됩니다. [＋추가]로 선택 목록에 담고 [완료]로 등록하세요.
          {focusTarget?.label && <span className="ml-1 text-[var(--accent-strong)]">검색 위치: {focusTarget.label}</span>}
          <span className="ml-1 text-[var(--text-hint)]">(건물 외곽선이나 도로도 선택 가능, 지목은 카드에서 확인)</span>
        </p>
      )}

      {/* 상태 메시지 — 로딩/오류/미발견 표시 */}
      {status === "loading" && (
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--accent-strong)]">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
          {statusMsg}
        </div>
      )}
      {status === "notfound" && (
        <p className="inline-flex items-baseline gap-1 text-[11px] font-semibold text-amber-500"><AlertTriangle className="size-3.5 self-center shrink-0" aria-hidden /> {statusMsg}</p>
      )}
      {status === "error" && (
        <p className="inline-flex items-baseline gap-1 text-[11px] font-semibold text-red-500"><X className="size-3.5 self-center shrink-0" aria-hidden /> {statusMsg}</p>
      )}

      {/* Leaflet 지도 캔버스 — useMapFullscreen 래퍼 */}
      <div ref={wrapperRef} className={wrapperClass("relative")}>
        <div
          ref={mapEl}
          className="w-full overflow-hidden rounded-lg border border-[var(--line)]"
          style={{
            flex: isMapFullscreen ? "1 1 auto" : undefined,
            height: isMapFullscreen ? "100%" : height,
            minHeight: isMapFullscreen ? 0 : undefined,
          }}
        />

        {/* 풀스크린 버튼 */}
        <button
          type="button"
          onClick={toggleMapFullscreen}
          title={isMapFullscreen ? "전체화면 종료" : "전체화면"}
          className="absolute right-2 top-2 z-[400] rounded-lg border border-[var(--line-strong)] bg-[var(--surface)]/90 p-1.5 text-[var(--text-secondary)] shadow hover:bg-[var(--surface-muted)] transition-colors"
          aria-label="전체화면"
        >
          {isMapFullscreen ? (
            // 전체화면 종료 아이콘
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/></svg>
          ) : (
            // 전체화면 열기 아이콘
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8V5a2 2 0 0 1 2-2h3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M21 16v3a2 2 0 0 1-2 2h-3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/></svg>
          )}
        </button>

        {(tileStatus === "error" || boundaryStatus === "loading" || boundaryStatus === "error" || overlayNote || marketNote || poiNote || developmentNote) && (
          <div className="pointer-events-none absolute bottom-3 left-3 z-[410] max-w-[calc(100%-96px)] space-y-1">
            {overlayNote && (
              <span className="inline-flex rounded-full bg-white/92 px-3 py-1.5 text-[11px] font-black text-slate-700 shadow">
                {overlayNote}
              </span>
            )}
            {marketNote && (
              <span className="inline-flex rounded-full bg-white/92 px-3 py-1.5 text-[11px] font-black text-slate-700 shadow">
                {marketNote}
              </span>
            )}
            {poiNote && (
              <span className="inline-flex rounded-full bg-white/92 px-3 py-1.5 text-[11px] font-black text-slate-700 shadow">
                {poiNote}
              </span>
            )}
            {developmentNote && (
              <span className="inline-flex rounded-full bg-white/92 px-3 py-1.5 text-[11px] font-black text-slate-700 shadow">
                {developmentNote}
              </span>
            )}
            {boundaryStatus === "loading" && (
              <span className="inline-flex rounded-full bg-blue-50/95 px-3 py-1.5 text-[11px] font-black text-blue-700 shadow">
                VWorld 필지 경계 보강 중
              </span>
            )}
            {boundaryStatus === "error" && (
              <span className="inline-flex rounded-full bg-amber-50/95 px-3 py-1.5 text-[11px] font-black text-amber-800 shadow">
                일부 필지 경계 보강 실패 · 확보된 실데이터만 표시
              </span>
            )}
            {tileStatus === "error" && (
              <span className="inline-flex rounded-full bg-rose-50/95 px-3 py-1.5 text-[11px] font-black text-rose-700 shadow">
                VWorld 기본지도 타일 연결 실패
              </span>
            )}
          </div>
        )}

        {/* 노후도 범례 레전드 UI */}
        {hasSatongLayer(layerState, "age") && (
          <div className="absolute bottom-3 right-3 z-[410] rounded-xl border border-slate-200 bg-white/95 p-2.5 shadow-lg backdrop-blur">
            <div className="mb-1.5 text-[11px] font-extrabold text-slate-800">🏢 건물 노후도 구분</div>
            <div className="flex flex-col gap-1 text-[10.5px]">
              {AGE_LEGEND_ITEMS.map((item) => (
                <div key={item.label} className="flex items-center gap-1.5 font-semibold text-slate-700">
                  <span className="h-3 w-3 rounded-sm border border-black/10 shadow-xs" style={{ backgroundColor: item.color }} />
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 초기 안내 오버레이(아직 클릭 전) */}
        {!readOnly && status === "idle" && staged.length === 0 && overlayFeatures.length === 0 && !marketPayload && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg">
            <span className="rounded-lg bg-[var(--surface)]/80 px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] shadow">
              지도를 클릭해 필지 선택
            </span>
          </div>
        )}

        {/* ── 확인 카드 오버레이 — 조회 완료 후 사용자가 추가/취소를 결정하는 카드 ── */}
        {!readOnly && status === "found" && pending && (
          <div className="absolute bottom-10 left-1/2 z-[500] -translate-x-1/2 w-[calc(100%-32px)] max-w-sm">
            <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface)]/95 p-3 shadow-[var(--shadow-lg)] backdrop-blur-sm">
              {/* 필지 요약 정보 */}
              <div className="mb-2 space-y-0.5">
                <p className="text-[12px] font-bold text-[var(--text-primary)] leading-snug">
                  {/* 주소 또는 PNU 표시 */}
                  {pending.address || pending.jibun || pending.pnu}
                </p>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--text-secondary)]">
                  {/* 면적(㎡·평) */}
                  {pending.area_sqm != null && pending.area_sqm > 0 && (
                    <span className="font-semibold text-[var(--accent-strong)]">
                      {Math.round(pending.area_sqm).toLocaleString()}㎡ ({toP(pending.area_sqm)}평)
                    </span>
                  )}
                  {/* 용도지역 */}
                  {pending.zone_type && (
                    <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 font-semibold">
                      {pending.zone_type}
                    </span>
                  )}
                  {/* 지목 — 도로 등도 그대로 표기(필터 없음) */}
                  {pending.jimok && (
                    <span>지목 <b>{pending.jimok}</b></span>
                  )}
                </div>
              </div>

              {/* 버튼 영역 */}
              {pendingAlreadyStaged ? (
                // 이미 staged에 있는 필지 → 제거 옵션 표시
                <div className="flex items-center gap-2">
                  <span className="flex-1 text-[11px] font-bold text-emerald-500">이미 선택됨</span>
                  <button
                    type="button"
                    onClick={() => pending.pnu && handleRemoveStaged(pending.pnu)}
                    className="rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-1.5 text-[11px] font-bold text-red-500 hover:bg-red-500/20 transition-colors"
                  >
                    제거
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelPending}
                    className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:bg-[var(--surface)] transition-colors"
                  >
                    닫기
                  </button>
                </div>
              ) : (
                // 신규 필지 → 추가/취소 버튼
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleConfirmAdd}
                    className="flex-1 rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 transition-opacity"
                  >
                    ＋추가
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelPending}
                    className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:bg-[var(--surface)] transition-colors"
                  >
                    취소
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── 하단 고정 바 — 선택 필지 수·합산 면적·완료/전체취소 ── */}
      {!readOnly && (
      <div className="flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/60 px-3 py-2">
        {/* 선택 현황 */}
        <div className="flex-1 text-[11px]">
          {staged.length > 0 ? (
            <span className="font-bold text-[var(--text-primary)]">
              선택 <span className="text-[var(--accent-strong)]">{staged.length}필지</span>
              {totalAreaSqm > 0 && (
                <span className="ml-1.5 font-normal text-[var(--text-secondary)]">
                  · 합산 {Math.round(totalAreaSqm).toLocaleString()}㎡ ({toP(totalAreaSqm)}평)
                </span>
              )}
            </span>
          ) : (
            <span className="text-[var(--text-hint)]">아직 선택된 필지 없음</span>
          )}
        </div>

        {/* 전체취소 버튼 — staged가 있을 때만 활성 */}
        {staged.length > 0 && (
          <button
            type="button"
            onClick={handleClearAll}
            className="rounded-lg border border-[var(--line-strong)] px-2.5 py-1.5 text-[10px] font-bold text-[var(--text-secondary)] hover:border-red-400/50 hover:text-red-500 hover:bg-red-500/10 transition-colors"
          >
            전체취소
          </button>
        )}

        {/* 완료 버튼 — staged가 있을 때만 활성(없으면 비활성 스타일) */}
        <button
          type="button"
          disabled={staged.length === 0}
          onClick={handleComplete}
          className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 transition-opacity"
        >
          완료({staged.length}필지 등록)
        </button>
      </div>
      )}
    </div>
  );
}

export default SatongMultiMap;
