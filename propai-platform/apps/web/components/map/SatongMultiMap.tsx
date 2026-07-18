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

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, Building2, LandPlot, MapPin, Ruler, Search, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import {
  AGE_LEGEND_ITEMS,
  CAPACITY_LEGEND_ITEMS,
  capacityColor,
  ageColor,
  ageLabel,
  geometryRepresentativePoint,
  hasSatongLayer,
  hasSatongLayerControl,
  mergeSatongMapFeatures,
  priceColor,
  priceManPyeong,
  pricePyeongOnly,
  resolveRegulationWmsLayers,
  resolveVWorldBaseLayer,
  satongMapFeatureKey,
  type SatongMapFeature,
  type SatongMapLayerState,
  type VWorldBaseLayer,
  zoneColor,
} from "@/lib/satong-map-layers";
import { bindSatongLabel, planSatongLabels, satongLabelLOD } from "@/lib/satong-map-labels";
import { SATONG_PANE_Z, SATONG_UI_Z } from "@/lib/satong-map-z";
import { clampClickMenuPosition, findFeatureAtPoint, shortJibunLabel } from "@/lib/satong-click-menu";
import {
  formatAreaSqm,
  formatDistance,
  polygonAreaSqm,
  totalDistanceMeters,
  type MeasurePoint,
} from "@/lib/satong-measure";
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
  /** 경계 API(/zoning/parcel-boundaries)가 보강한 필지 속성(면적·용도·좌표·경계) 역전파 —
   *  부모가 선택목록·SSOT에 병합해 다필지 통합분석이 면적을 받도록 한다. */
  onBoundaryEnriched?: (features: SatongMapFeature[]) => void;
  /** 경계보강 진행상태 통지 — 부모(Shell)가 "좌표 확인 중" 노트를 실패 시 정직 강등하는 데 쓴다. */
  onBoundaryStatusChange?: (status: "idle" | "loading" | "ready" | "error") => void;
  /** 분양 상태 노트(좌표 대기·조회 실패 등) — 설정 시 건수 라벨 대신 표기(정직원칙).
   *  ★marketLayer 객체에 넣지 않고 별도 prop으로 받는다 — 노트만 바뀔 때 마커 이펙트가
   *  전체 재생성되던 낭비(리뷰 LOW)를 차단. */
  presaleNote?: string | null;
  /** 경매 상태 노트(로그인 필요·권한 없음·좌표 대기 등) — 위와 동일 규약. */
  auctionNote?: string | null;
  /** 보기 전용 지도에서 필지 폴리곤/마커 클릭 시 기존 화면과 연동한다. */
  onFeatureClick?: (feature: SatongMapFeature) => void;
  /** 기존 구획도/토지조서 상태색 호환. 키는 주소. */
  featureStatusColors?: Record<string, string>;
  /** 기존 구획도/토지조서 상태 라벨 호환. 키는 주소. */
  featureStatusLabels?: Record<string, string>;
  /** 기존 구획도 하이라이트 주소 호환. */
  highlightFeatureAddress?: string;
  /** 부모(Shell) "초기화"(clearParcels) 신호 — 증가할 때마다 지도 staged·녹색 폴리곤·pending을
   *  청소한다(WP-M2). 종전엔 목록만 비고 지도엔 잔존했다. undefined면 무동작(하위호환). */
  clearSignal?: number;
  /** 하단 도크 우측 슬롯 — 베이스맵 스위처 등 부모 소유 컨트롤을 도크 flow 안에 배치한다.
   *  ★겹침 구조 진단(2026-07-17): 독립 absolute 섬(스위처 bottom-20 right-4)과 칩 행의
   *  암묵 예약값(max-w calc 152px)이 겹침의 근원 — 같은 flex 행에 흘리면 겹침이 문법적으로
   *  불가능하고 예약값 자체가 사라진다. 슬롯이 있으면 도크는 칩이 없어도 항상 렌더된다. */
  bottomDockSlot?: ReactNode;
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
  // 노후도 무자료 사유(no_building/lookup_failed/skipped_bulk) — 값 있으면 null(WP-M3).
  age_status?: string | null;
  /** WS-D 개발여력 — 서버 산정 실효/현황 용적률(%). 미상 None. */
  effective_far_pct?: number | null;
  current_far_pct?: number | null;
  effective_bcr_pct?: number | null;
  total_floor_area_sqm?: number | null;
  geometry?: any;
  // 서버가 대표좌표를 줄 경우 대비(additive) — 없으면 geometry 대표점으로 파생한다.
  lat?: number | null;
  lon?: number | null;
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
// 마커 상시 라벨 노출 정책은 satong-map-labels 로 이관됨(전역 버짓 + 줌 LOD 단일 판정).
//   종전 레이어별 `개수 ≤ 32` 독립 판정(합산 ~160개 살포)을 planSatongLabels 로 대체한다.

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
  // 상태 노트(presaleNote/auctionNote)는 SatongMultiMapProps의 별도 prop — 객체에 접어 넣으면
  // 노트 변경마다 marketLayer identity가 바뀌어 마커 이펙트가 전체 재실행된다(리뷰 LOW).
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

/** buildOverlayNotes 입력 — 오버레이 이펙트에서 집계한 레이어별 표시 상태. */
export interface OverlayNoteCounts {
  showCadastre: boolean;
  cadastreCount: number;
  showZoning: boolean;
  zoningCount: number;
  showPrice: boolean;
  priceCount: number;
  showAge: boolean;
  ageCount: number;
  /** WS-D 개발여력 — 미지정(구 호출부·테스트)이면 종전 문구와 동일(무회귀). */
  showCapacity?: boolean;
  capacityCount?: number;
  markerCount: number;
  // 노후도 무자료 사유 세분화(WP-M3) — ageCount=0일 때 "나대지 N·미준공 P·조회실패 M·대량생략 K"로 고지.
  //   미지정(구 호출부·테스트)이면 종전과 동일하게 단일 "노후도 무자료"로 폴백(무회귀).
  ageNoBuilding?: number;
  // ★리뷰(MEDIUM1): 건물이 실재하나(building_name 등 존재) 사용승인일 미기재(미준공 등)로 연식
  //   계산 불가한 경우 — 'no_building'(나대지)과 구분한다. 건물 있는 땅을 나대지로 오표기하면
  //   정직성 위배(M3 취지 정면 위배)이므로 별도 사유값으로 분리.
  ageNoApprovalDate?: number;
  ageLookupFailed?: number;
  ageSkippedBulk?: number;
}

/** 노후도 무자료 사유 세분 문구(공용) — "나대지 3·미준공 2·조회실패 9·대량생략 41". 사유 0건이면 "". */
export function buildAgeGapDetail(counts: {
  ageNoBuilding?: number;
  ageNoApprovalDate?: number;
  ageLookupFailed?: number;
  ageSkippedBulk?: number;
}): string {
  const parts: string[] = [];
  if (counts.ageNoBuilding) parts.push(`나대지 ${counts.ageNoBuilding}`);
  if (counts.ageNoApprovalDate) parts.push(`미준공 ${counts.ageNoApprovalDate}`);
  if (counts.ageLookupFailed) parts.push(`조회실패 ${counts.ageLookupFailed}`);
  if (counts.ageSkippedBulk) parts.push(`대량생략 ${counts.ageSkippedBulk}`);
  return parts.join("·");
}

/**
 * 오버레이 상태 메모(순수 함수) — 정직 라벨 원칙.
 * 켜져 있는 레이어는 자료가 0건이어도 반드시 '무자료'로 표기한다
 * (지적 포함 — 켰는데 아무 표기가 없으면 사용자가 자료 부재를 알 수 없다).
 */
export function buildOverlayNotes(counts: OverlayNoteCounts): string {
  const notes: string[] = [];
  if (counts.showCadastre) notes.push(counts.cadastreCount ? `지적 ${counts.cadastreCount}건` : "지적 무자료");
  if (counts.showZoning) notes.push(counts.zoningCount ? `용도지역 ${counts.zoningCount}건` : "용도지역 무자료");
  if (counts.showPrice) notes.push(counts.priceCount ? `공시지가 ${counts.priceCount}건` : "공시지가 무자료");
  if (counts.showAge) {
    if (counts.ageCount) {
      notes.push(`노후도 ${counts.ageCount}건`);
    } else {
      const detail = buildAgeGapDetail(counts);
      notes.push(detail ? `노후도 무자료(${detail})` : "노후도 무자료");
    }
  }
  if (counts.showCapacity) notes.push(counts.capacityCount ? `개발여력 ${counts.capacityCount}건` : "개발여력 무자료(실효·현황 용적률 필요)");
  if (counts.markerCount) notes.push(`좌표 ${counts.markerCount}건`);
  return notes.join(" · ");
}

/** 선택 상태 SSOT 멤버십 키(공용) — pnu 우선, 없으면 주소 정규화(공백 축약) 폴백.
 *  Shell parcelKey(pnu||normalizeKey(address))와 동일 규약 — selectedParcels(프로젝트 필지)와
 *  staged/pending(지도 선택)을 같은 기준으로 대조해 이중 등록·중복 카운트를 차단한다(WP-M2). */
export function parcelMembershipKey(p: { pnu?: string | null; address?: string | null }): string {
  const pnu = (p.pnu || "").trim();
  if (pnu) return pnu;
  return (p.address || "").trim().replace(/\s+/g, " ");
}

/**
 * 경계 조회 준비 판정(WP-M3 재조회 루프 제거) — 순수 함수.
 *
 * 종전 hasAllGeometryAndMetadata 는 필지마다 `buildingAgeYears != null` 을 요구했다. 나대지(연식
 * 없음이 정상)가 1필지라도 있으면 항상 false → 재마운트마다 전체 경계(45s)를 재조회하는 루프였다.
 * 여기서는 (1) geometry 존재 + (2) 노후도 '조회 시도됨'(age 값이 있거나 ageStatus 로 시도 흔적)만
 * 요구한다 — 나대지는 ageStatus 로 '시도됨'을 표시하므로 재조회 없이 준비 완료로 판정된다.
 */
export function selectionBoundaryReady(
  parcels: Array<Pick<SatongMapFeature, "geometry" | "buildingAgeYears" | "ageStatus">>,
): boolean {
  if (!parcels.length) return false;
  return parcels.every(
    (p) => !!p.geometry && (p.buildingAgeYears != null || p.ageStatus != null),
  );
}

/**
 * ★WP-M2 리뷰(HIGH) 방어선 — pnu/주소 키 이중성 보강.
 *
 * 시드 필지(엑셀·지오코딩)는 pnu 미확보 상태로 selectedParcels 에 들어오는 경우가 있다. 이후
 * boundary 보강이 real pnu 를 채워 넣기까지(비동기 왕복) 짧은 과도기 동안, autoStage(프로젝트
 * 연결 시 focusTarget→같은 지점 재조회)가 parcelMembershipKey 로만 판정하면 "기등록 필지를
 * 새 staged로" 오카운트할 수 있다(주된 치유는 SatongMapShell.handleBoundaryEnriched의 pnu 승격 —
 * healParcelPnu). 이 함수는 그 과도기를 메우는 2차 방어선: autoStage 는 항상 selectedParcels 의
 * 좌표(focusTarget)와 '정확히 같은 지점'을 재조회하므로(같은 float 값), 매우 좁은 허용오차
 * (기본 1e-5도≈1.1m — 지적 필지 간 간격보다 훨씬 좁아 인접한 '다른' 필지를 오탐하지 않는다)로
 * "같은 지점 재조회"만 잡아낸다. 수동 지도 클릭(비-autoStage)에는 적용하지 않는다.
 */
export function isSameSpotAsAny(
  lat: number,
  lon: number,
  parcels: Array<{ lat?: number | null; lon?: number | null }>,
  epsilonDeg = 1e-5,
): boolean {
  return parcels.some(
    (p) =>
      typeof p.lat === "number" &&
      typeof p.lon === "number" &&
      Math.abs(p.lat - lat) < epsilonDeg &&
      Math.abs(p.lon - lon) < epsilonDeg,
  );
}

/** [MAP-007] 기반 타일 실패 오버레이 내용. null이면 오버레이를 띄우지 않는다. */
export interface TileFailureNotice {
  message: string;
  retryLabel: string;
}

/**
 * [MAP-007] 기반 타일 실패 오버레이 판정(순수 함수) — 정직 라벨 원칙.
 * 타일 실패 시 지도는 회색 배경+초기 줌으로 정지해 '로딩 중'과 구분이 안 되므로,
 * error 상태를 명시 오버레이(실패 메시지+재시도)로 승격한다.
 * idle(로딩 전/중)·ready(정상)에서는 null — 로딩을 실패로 위장하지 않는다.
 */
export function buildTileFailureNotice(
  tileStatus: "idle" | "ready" | "error",
): TileFailureNotice | null {
  if (tileStatus !== "error") return null;
  return {
    message: "기본지도(VWorld) 타일 로드 실패 — 필지·오버레이는 유지되며 배경지도만 미표시입니다.",
    retryLabel: "재시도",
  };
}

function createOfficialBaseMapLayer(
  L: any,
  baseLayer: VWorldBaseLayer,
  onTileState: (state: "ready" | "error") => void,
): any {
  // ★타일은 프론트 서버 프록시(/tiles/vworld) 경유 — (1)API키를 브라우저에 노출하지 않고
  //   (2)위성(Satellite)을 .jpeg로 요청하며 (3)VWorld 200+XML 오류를 투명타일로 흡수한다.
  //   (api.vworld.kr 직접호출은 키노출·위성 png 오류·XML 미처리로 회색지도를 유발하므로 금지.)
  const makeTile = (layerName: string, pane?: string) =>
    L.tileLayer(`/tiles/vworld/wmts/${layerName}/{z}/{y}/{x}.png`, {
      attribution: "VWorld · 국토교통부 공간정보 오픈플랫폼",
      maxZoom: 19,
      crossOrigin: true,
      ...(pane ? { pane } : {}),
    });

  // ★VWorld의 Hybrid는 단독 베이스가 아니라 '위성영상 위에 얹는 투명 라벨·도로 오버레이'다
  //   (타일 실측: Hybrid=PNG RGBA 투명채널, Base=불투명 팔레트). 단독으로 깔면 밝은 배경에
  //   라벨만 뜨는 유령지도가 됨 → 항공뷰는 Satellite(베이스)+Hybrid(오버레이) 두 장을 합성한다.
  //   텍스트/라벨이 폴리곤(overlayPane, 400) 위로 올라오도록 overlay 타일은 labelPane(450)에 그린다.
  //   사용자가 일반지도(Base)나 회색지도(white — VWorld tiletype 정본, UI 라벨 "회색")를
  //   볼 때도 폴리곤에 텍스트가 덮이지 않도록 Hybrid 라벨 타일을 labelPane에 함께 얹는다.
  if (baseLayer === "Hybrid" || baseLayer === "Base" || baseLayer === "white") {
    const base = makeTile(baseLayer === "Hybrid" ? "Satellite" : baseLayer);
    const overlay = makeTile("Hybrid", "labelPane");
    base.on("tileload", () => onTileState("ready"));
    base.on("tileerror", () => onTileState("error"));
    return L.layerGroup([base, overlay]);
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
  // 좌표는 서버가 준 값만 통과시킨다(현재 /zoning/parcel-boundaries는 per-feature 좌표 없음).
  // ★대표점(경계상자 중심) 파생좌표는 여기서 만들지 않는다 — 만들면 역전파(onBoundaryEnriched)를
  //   타고 프로젝트 SSOT(/analysis·산출물)의 정본 필지좌표로 영속돼, 근사좌표가 "좌표미상" 분기를
  //   전역에서 우회한다(리뷰 MEDIUM). 좌표 앵커(분양·경매·개발계획)의 자기치유는
  //   resolveSelectionAnchor 규칙②가 geometry에서 앵커 해석 시점에 임시 계산하므로 이것으로 충분.
  return {
    id: feature.pnu || feature.address,
    pnu: feature.pnu ?? null,
    address: feature.address || feature.pnu || "필지",
    lat: typeof feature.lat === "number" ? feature.lat : null,
    lon: typeof feature.lon === "number" ? feature.lon : null,
    areaSqm: feature.area_sqm ?? null,
    zoneType: feature.zone_type ?? null,
    zoneType2: feature.zone_type_2 ?? null,
    jimok: feature.jimok ?? null,
    officialPricePerSqm: feature.official_price_per_sqm ?? null,
    builtYear: feature.built_year ?? null,
    buildingAgeYears: feature.building_age_years ?? null,
    ageStatus: feature.age_status ?? null,
    effectiveFarPct: feature.effective_far_pct ?? null,
    currentFarPct: feature.current_far_pct ?? null,
    effectiveBcrPct: feature.effective_bcr_pct ?? null,
    geometry: feature.geometry,
    source: "boundary",
  };
}

function featurePopupHtml(feature: SatongMapFeature, statusLabel?: string): string {
  return [
    `<div style="padding:10px 12px;font-size:12px;line-height:1.6;min-width:200px;">`,
    feature.zoneType ? `<div style="margin-bottom:6px;"><span style="background:#0e7490;color:#fff;padding:3px 8px;border-radius:6px;font-weight:900;font-size:11.5px;letter-spacing:-0.2px;">용도지역: ${escapeHtml(feature.zoneType)}</span></div>` : "",
    `<b>${escapeHtml(feature.address || feature.pnu || "필지")}</b>${statusLabel ? ` <span style="color:#0e7490">[${escapeHtml(statusLabel)}]</span>` : ""}`,
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
    let eok = Math.floor(man / 10000);
    let rest = Math.round((man % 10000) / 1000);
    // ★R1 발견(발견즉시 수정): 9,900만대 반올림 시 rest=10이 되어 "4.10억"으로 오표기 —
    //   자리올림해 "5억"으로 정직 표기.
    if (rest >= 10) {
      eok += 1;
      rest = 0;
    }
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
  bottomDockSlot,
  marketPayload = null,
  marketLayer,
  poiPayload = null,
  developmentPayload = null,
  onCenterChange,
  onBoundaryEnriched,
  onBoundaryStatusChange,
  presaleNote = null,
  auctionNote = null,
  onFeatureClick,
  featureStatusColors,
  featureStatusLabels,
  highlightFeatureAddress,
  clearSignal,
}: SatongMultiMapProps) {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const onCenterChangeRef = useRef(onCenterChange);
  onCenterChangeRef.current = onCenterChange;
  const onBoundaryEnrichedRef = useRef(onBoundaryEnriched);
  onBoundaryEnrichedRef.current = onBoundaryEnriched;
  const onBoundaryStatusChangeRef = useRef(onBoundaryStatusChange);
  onBoundaryStatusChangeRef.current = onBoundaryStatusChange;
  const moveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mapRef = useRef<any>(null);
  const {
    isFull: isMapFullscreen,
    toggle: toggleMapFullscreen,
    wrapperClass,
    wrapperRef,
  } = useMapFullscreen(mapRef, { mode: "css" });
  const [mapReady, setMapReady] = useState(false);
  // 현재 줌 레벨 — 라벨 LOD(z≥17 전체 / 15~16 상위 N / <15 hover-only) 판정 입력.
  //   zoomend 에서만 갱신하고, 임계(15·17) 교차 시에만 버짓이 바뀌어 라벨 이펙트가 재부착된다.
  const [mapZoom, setMapZoom] = useState(12);
  // 실거래 fitBounds 1회성 가드 — 라벨 재부착(줌 교차)로 이펙트가 재실행돼도 사용자 줌을 덮지 않게.
  const lastMarketFitKeyRef = useRef("");
  const baseLayerRef = useRef<any>(null);
  const overlayLayerRef = useRef<any>(null);
  const marketLayerRef = useRef<any>(null);
  const presaleAuctionLayerRef = useRef<any>(null);
  const poiLayerRef = useRef<any>(null);
  const developmentLayerRef = useRef<any>(null);
  const lastFitKeyRef = useRef("");
  const [tileStatus, setTileStatus] = useState<"idle" | "ready" | "error">("idle");
  // [MAP-007] 타일 재시도 트리거 — 증가 시 기본지도 레이어 이펙트가 레이어를 재생성한다.
  const [tileRetryNonce, setTileRetryNonce] = useState(0);
  const [boundaryStatus, setBoundaryStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [boundaryFeatures, setBoundaryFeatures] = useState<SatongMapFeature[]>([]);
  const [overlayNote, setOverlayNote] = useState("");
  const [marketNote, setMarketNote] = useState("");
  const [poiNote, setPoiNote] = useState("");
  const [developmentNote, setDevelopmentNote] = useState("");
  // ★PR#329 R1 리뷰(MEDIUM2) 반영: 지적 WMS 타일 실패(키 미설정·상류 인증오류 등)를
  //   무음 회색지도로 남기지 않고 다른 레이어 노트와 동일한 칩 체계로 표면화한다.
  const [cadastreTileNote, setCadastreTileNote] = useState("");

  // I9 자가진단: 지적 오류 배지 클릭 → 프록시 1회 프로브로 실제 원인(code)을 배지에 표면화.
  //   #347/#354가 프록시 오류에 ServiceException code를 담으므로, 배지만으로 '키/도메인/
  //   파라미터/네트워크'를 현장에서 즉시 구분할 수 있다(서버 로그 접근 불요).
  const diagnoseBusyRef = useRef(false);
  const lastAutoDiagnoseAtRef = useRef(0);
  const aerialViewRef = useRef(false);
  const autoDiagnoseRef = useRef<(() => void) | null>(null);
  const diagnoseCadastreTiles = useCallback(async () => {
    if (diagnoseBusyRef.current) return; // 연타 가드(R1)
    diagnoseBusyRef.current = true;
    setCadastreTileNote("지적 프록시 진단 중…");
    try {
      // ★R1(SW 캐시 오진): fetch cache:no-store는 브라우저 HTTP 캐시만 통제하고 서비스워커
      //   Cache Storage(staleWhileRevalidate)는 우회하지 못한다 — 과거 성공본이 '정상' 오진을
      //   만들 수 있어 타임스탬프 캐시버스터로 SW 캐시 키를 매번 미스시킨다(항상 라이브).
      // ★R1 M2: 프로브는 부설과 '같은 스타일'을 써야 한다 — 선 스타일만 실패하는 경우를
      //   채움 프로브가 "정상"으로 오진하지 않게 활성 뷰 모드와 일원화.
      const probeStyles = aerialViewRef.current
        ? "lp_pa_cbnd_bubun_line,lp_pa_cbnd_bonbun_line"
        : "lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun";
      const probe =
        "/tiles/vworld/wms?service=WMS&request=GetMap&layers=lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun" +
        `&styles=${probeStyles}&format=image/png&transparent=true&version=1.3.0` +
        `&width=64&height=64&crs=EPSG:3857&bbox=14134000,4518000,14136000,4520000&_ts=${Date.now()}`;
      const resp = await fetch(probe, { cache: "no-store" });
      const contentType = resp.headers.get("content-type") || "";
      if (resp.ok && contentType.startsWith("image/")) {
        setCadastreTileNote("지적 프록시 정상 — 지도를 이동/새로고침해도 안 보이면 줌·영역을 확인하세요");
        return;
      }
      const body = await resp.json().catch(() => null);
      const errText: string = body?.error ?? `HTTP ${resp.status}`;
      // 긴 원문 대신 원인 코드만 요약 — 키 무효(INVALID/INCORRECT_KEY)면 복구 경로 안내.
      const code = /\(([A-Z_/]+)\)/.exec(errText)?.[1];
      const keyFault = code === "INVALID_KEY" || code === "INCORRECT_KEY";
      setCadastreTileNote(
        `지적 타일 오류 — ${code ?? errText}${keyFault ? " · 인증키 무효(관리자 화면에 유효 키 등록 시 자동 복구)" : ""}`,
      );
    } catch {
      setCadastreTileNote("지적 타일 조회 실패 — 네트워크 오류(진단)");
    } finally {
      diagnoseBusyRef.current = false;
    }
  }, []);

  // tileerror 자동진단 배선 — 60초 스로틀(연속 타일 실패의 프로브 폭주 방지).
  useEffect(() => {
    autoDiagnoseRef.current = () => {
      const now = Date.now();
      if (now - lastAutoDiagnoseAtRef.current < 60_000) return;
      lastAutoDiagnoseAtRef.current = now;
      void diagnoseCadastreTiles();
    };
  }, [diagnoseCadastreTiles]);

  // 조회 상태
  const [status, setStatus] = useState<"idle" | "loading" | "found" | "notfound" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");

  // 확인 대기 중인 필지(클릭→조회완료, 아직 staged에 안 들어간 상태)
  const [pending, setPending] = useState<ParcelAtPointResult | null>(null);
  // 임시 마커 레이어(pending 상태일 때 지도 위에 표시, 취소/추가 시 제거)
  const pendingLayerRef = useRef<any>(null);

  // staged: 사용자가 [＋추가]로 확정한 필지 목록
  const [staged, setStaged] = useState<ParcelAtPointResult[]>([]);

  // ── 지도 클릭 팝오버(단일 팝오버 계약 — 디자인컴프) & 거리재기 ──
  //   클릭 즉시 필지조회 대신 그 지점에 액션 메뉴 1개를 띄운다(오클릭 API 호출 절감 +
  //   색깔점/색면 오클릭으로 필지선택이 발동하던 혼선 제거). x/y = 지도 컨테이너 픽셀 좌표.
  //   w/h = 클릭 시점의 지도 컨테이너 크기(렌더 중 ref 접근 금지 — 클릭 핸들러에서 캡처).
  const [clickMenu, setClickMenu] = useState<{
    lat: number; lon: number; x: number; y: number; w: number; h: number;
  } | null>(null);
  const [measureOn, setMeasureOn] = useState(false);
  // 측정 모드(I6): distance=폴리라인 누적거리 / area=폴리곤 면적(등장방형 신발끈 — satong-measure).
  const [measureMode, setMeasureMode] = useState<"distance" | "area">("distance");
  const measureOnRef = useRef(false);
  const [measurePoints, setMeasurePoints] = useState<MeasurePoint[]>([]);
  const measureLayerRef = useRef<any>(null);
  // 노후도 범례 접기(기본 접힘) — 하단 도크 과점 해소(U1).
  const [legendOpen, setLegendOpen] = useState(false);
  // 팝오버 좌표 복사 피드백 — 복사한 좌표 문자열(현재 팝오버와 일치할 때만 '복사됨' 표시).
  const [copiedCoord, setCopiedCoord] = useState<string | null>(null);
  // I4 저줌 안내(jootek 패턴): 라벨이 롤업되는 줌(<15)에서 "확대하면 표시" 안내+원클릭 확대.
  const [zoomHintDismissed, setZoomHintDismissed] = useState(false);

  // 선택 필지 및 staged 필지 통합 평균 노후도 계산
  const avgAge = useMemo(() => {
    const allFeatures = new Map<string, { buildingAgeYears?: number | null }>();
    
    boundaryFeatures.forEach((p) => {
      if (p.id) allFeatures.set(p.id, { buildingAgeYears: p.buildingAgeYears });
    });
    
    staged.forEach((s) => {
      const id = s.pnu || s.address || s.jibun || "staged";
      allFeatures.set(id, { buildingAgeYears: s.building_age_years });
    });

    const validAges = Array.from(allFeatures.values())
      .map((p) => p.buildingAgeYears)
      .filter((age): age is number => typeof age === "number" && age >= 0);

    if (validAges.length === 0) return null;
    const sum = validAges.reduce((a, b) => a + b, 0);
    return Math.round((sum / validAges.length) * 10) / 10;
  }, [boundaryFeatures, staged]);

  // ★WP-M3: 노후도 무자료 사유 세분 집계 — 연식이 없는 필지만 age_status로 나눈다
  //   (나대지 / 미준공(리뷰 MEDIUM1) / 조회실패 / 대량생략). 칩 문구와 범례 무자료 표기의 단일 출처.
  const ageStatusCounts = useMemo(() => {
    let ageNoBuilding = 0;
    let ageNoApprovalDate = 0;
    let ageLookupFailed = 0;
    let ageSkippedBulk = 0;
    boundaryFeatures.forEach((f) => {
      if (f.buildingAgeYears != null) return; // 연식 있음 → 무자료 아님
      if (f.ageStatus === "no_building") ageNoBuilding += 1;
      else if (f.ageStatus === "no_approval_date") ageNoApprovalDate += 1;
      else if (f.ageStatus === "lookup_failed") ageLookupFailed += 1;
      else if (f.ageStatus === "skipped_bulk") ageSkippedBulk += 1;
    });
    return { ageNoBuilding, ageNoApprovalDate, ageLookupFailed, ageSkippedBulk };
  }, [boundaryFeatures]);
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
  // ★WP-M2 선택 상태 SSOT: 프로젝트 필지(selectedParcels)의 멤버십 키 집합. autoStage·확인카드·
  //   CTA 이중표기·reconcile 이펙트가 모두 이 하나로 "이미 등록됨"을 판정한다(칩 12 vs 완료 1 봉합).
  const selectedMembershipKeys = useMemo(
    () => new Set(selectedParcels.map(parcelMembershipKey).filter(Boolean)),
    [selectedParcels],
  );
  // queryParcel(안정 useCallback)이 최신 멤버십을 deps 없이 읽도록 ref 병행 — 지도 재생성 방지.
  const selectedMembershipKeysRef = useRef(selectedMembershipKeys);
  selectedMembershipKeysRef.current = selectedMembershipKeys;
  // ★WP-M2 리뷰(HIGH) 방어선: 좌표 근접(isSameSpotAsAny) 판정용 원본 selectedParcels ref —
  //   pnu 미확보 시드 필지도 lat/lon은 갖고 있을 수 있어(검색·엑셀 지오코딩), 키 불일치 과도기에도
  //   "같은 지점 재조회"를 잡아낸다.
  const selectedParcelsRef = useRef(selectedParcels);
  selectedParcelsRef.current = selectedParcels;
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

  // addStagedLayer(useCallback [])가 최신 onFeatureClick을 보도록 ref 경유(onPickRef 관례).
  const onFeatureClickRef = useRef(onFeatureClick);
  useEffect(() => {
    onFeatureClickRef.current = onFeatureClick;
  }, [onFeatureClick]);

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
      onBoundaryStatusChangeRef.current?.("idle");
      return;
    }
    // ★WP-M3: 준비 판정을 selectionBoundaryReady 로 위임 — 나대지(연식 null) 1필지에 의한
    //   전체 경계 재조회 루프 제거(geometry 존재 + '노후도 조회 시도됨'이면 준비 완료).
    const hasAllGeometryAndMetadata = selectionBoundaryReady(selectedParcels);
    if (hasAllGeometryAndMetadata) {
      setBoundaryFeatures(mergeSatongMapFeatures(selectedParcels));
      setBoundaryStatus("ready");
      onBoundaryStatusChangeRef.current?.("ready");
      return;
    }
    let alive = true;
    setBoundaryStatus("loading");
    onBoundaryStatusChangeRef.current?.("loading");
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
        onBoundaryStatusChangeRef.current?.("ready");
        // ★P1(감사): 경계 API가 받아온 면적·용도·좌표·경계를 부모(Shell)로 역전파 —
        //   종전엔 지도 내부 상태(dead-end)에만 남아, 검색 등록 필지가 면적 없음 →
        //   통합분석이 침묵 단일 격하되는 원인이었다.
        if (fromBoundary.length) onBoundaryEnrichedRef.current?.(fromBoundary);
      })
      .catch(() => {
        if (!alive) return;
        setBoundaryFeatures(mergeSatongMapFeatures(selectedParcels));
        setBoundaryStatus("error");
        // 부모(Shell)가 "좌표 확인 중" 노트를 "확인 실패"로 정직 강등할 수 있도록 통지.
        onBoundaryStatusChangeRef.current?.("error");
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

    // 선택 확정 — primary 블루 폴리곤(디자인컴프: 선택 필지 = primary. 종전 녹색 교체)
    if (parcel.geometry) {
      const rings = geoJsonToLeafletRings(parcel.geometry);
      if (rings.length > 0) {
        L.polygon(rings, {
          color: "#135bec", weight: 2.5, fillColor: "#135bec", fillOpacity: 0.24,
          bubblingMouseEvents: false, // 확정 필지 재클릭이 지점 팝오버를 열지 않게(R1 L3)
        })
          // 확정 필지 클릭 = 상세 패널(WS-C) — 레이어 토글 없이도 상세 접근 가능한 통로.
          .on("click", () => onFeatureClickRef.current?.(pointResultToFeature(parcel)))
          .addTo(layer);
      }
    }

    // 중심 마커(primary)
    if (parcel.lat != null && parcel.lon != null) {
      L.circleMarker([parcel.lat, parcel.lon], {
        radius: 7, color: "#135bec", weight: 2.5, fillColor: "#135bec", fillOpacity: 0.9,
        bubblingMouseEvents: false,
      }).addTo(layer);
    }

    stagedLayersRef.current.set(parcel.pnu, layer);
  }, []);

  /** 클릭한 좌표로 필지를 조회하고 결과를 pending 상태로 둔다 */
  const isMapClickSelectionRef = useRef(false);

  const queryParcel = useCallback(async (lat: number, lon: number, opts: { autoStage?: boolean } = {}) => {
    const seq = ++querySeqRef.current;
    setStatus("loading");
    setStatusMsg("필지 조회 중…");
    setPending(null);
    clearPendingLayer();

    const L = window.L;
    const map = mapRef.current;
    if (!map) return;

    // 클릭 위치에 <16ms 즉시 반응 펄스 마커(Pulsing Wave Ripple) 표출
    const rippleIcon = L.divIcon({
      className: "custom-ripple-icon",
      html: `<div style="position:relative;width:32px;height:32px;display:flex;align-items:center;justify-content:center;">
        <span style="position:absolute;width:100%;height:100%;border-radius:50%;background:#3b82f6;opacity:0.6;animation:ping 1s cubic-bezier(0,0,0.2,1) infinite;"></span>
        <span style="position:relative;width:14px;height:14px;border-radius:50%;background:#1d4ed8;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.3);"></span>
      </div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });
    const tempMarker = L.marker([lat, lon], { icon: rippleIcon }).addTo(map);

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
        bubblingMouseEvents: false, // X 클릭 = 사유 팝업만(지점 팝오버 동시 표출 방지 — R1 L3)
      }).bindPopup(`<div style="font-size:12px;max-width:200px;">${msg}</div>`, { maxWidth: 220 }).openPopup().addTo(notFoundLayer);
      pendingLayerRef.current = notFoundLayer;
      return;
    }

    // 이미 staged에 있는 필지인지 확인(ref로 읽어 deps 오염 방지)
    const alreadyStaged = stagedRef.current.some((s) => s.pnu && s.pnu === result.pnu);
    // ★WP-M2: 프로젝트에 이미 등록된 필지인지도 확인 — autoStage(프로젝트 연결 시 첫 필지
    //   focusTarget)가 기등록 필지를 staged에 재등록해 "1필지 추가"가 뜨던 원천을 차단한다.
    //   ★리뷰(HIGH) 방어선: 멤버십 키(pnu/주소)가 boundary 치유 전 과도기에 불일치할 수 있어,
    //   autoStage 한정으로 "정확히 같은 지점 재조회"도 함께 검사한다(주된 치유는 Shell의
    //   healParcelPnu — pnu 승격). 수동 클릭에는 좌표검사를 적용하지 않는다(인접 다른 필지 오탐 방지).
    const alreadyRegistered =
      selectedMembershipKeysRef.current.has(parcelMembershipKey(result)) ||
      (opts.autoStage === true && isSameSpotAsAny(lat, lon, selectedParcelsRef.current));

    setStatus("found");
    setStatusMsg("");
    // lat/lon 정보 보완(확인 카드·staged 레이어에서 좌표 재사용)
    result.lat = lat;
    result.lon = lon;

    if (opts.autoStage) {
      // 기등록(selectedParcels 멤버) 또는 기staged면 재등록하지 않는다 — 기등록 필지는 경계
      //   오버레이가 이미 그리므로 별도 staged 녹색 레이어도 불필요(이중 표시 방지).
      if (!alreadyStaged && !alreadyRegistered) {
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
        // 확인 대기(pending) = 점선 파랑 — 확정(primary 실선)과 시각 구분.
        const poly = L.polygon(rings, {
          color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.22, dashArray: "6 4",
          bubblingMouseEvents: false, // 확인 대기 필지 재클릭 = 무동작(팝오버 중복 방지 — R1 L3)
        }).addTo(layer);
        // 폴리곤 경계에 맞춰 지도 이동
        try { map.fitBounds(poly.getBounds(), { padding: [40, 40], maxZoom: 17 }); } catch { /* noop */ }
      }
    }

    // 중심점 마커(폴리곤 없을 때도 위치 표시)
    L.circleMarker([lat, lon], {
      radius: 7, color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.8,
      bubblingMouseEvents: false,
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

  // ★WP-M2 reconcile: selectedParcels(프로젝트 필지)에 편입된 staged 항목을 청소한다.
  //   완료(onPickMany)→부모가 addParcels→selectedParcels 증가→여기서 해당 staged를 제거하고
  //   임시 녹색 레이어도 걷어 이중 카운트/이중 표시를 없앤다(경계 오버레이가 대신 그린다).
  //   ★리뷰(MEDIUM3): removeStagedLayer(Leaflet DOM 조작) 부수효과를 setState 업데이터 밖으로
  //   뺐다 — 업데이터는 React가 재호출(StrictMode 이중호출 등)할 수 있어 순수해야 한다. 최신
  //   staged는 이미 동기화된 stagedRef(위 useEffect)로 읽고, 변화가 있을 때만 setStaged(값)로
  //   직접 세팅한다(업데이터 함수 자체를 쓰지 않음).
  /* eslint-disable-next-line react-hooks/set-state-in-effect -- staged reconcile follows the selectedParcels SSOT. */
  useEffect(() => {
    const prevStaged = stagedRef.current;
    const toRemove: string[] = [];
    const keep = prevStaged.filter((s) => {
      const matched = selectedMembershipKeys.has(parcelMembershipKey(s));
      if (matched && s.pnu) toRemove.push(s.pnu);
      return !matched;
    });
    if (keep.length === prevStaged.length) return; // 변화 없음 — setState·레이어 조작 생략
    toRemove.forEach((pnu) => removeStagedLayer(pnu));
    setStaged(keep);
  }, [selectedMembershipKeys, removeStagedLayer]);

  // ★WP-M2 초기화 배선: 부모(Shell) clearParcels가 clearSignal을 증가시키면 지도 staged·폴리곤·
  //   pending을 함께 청소한다(종전엔 목록만 비고 지도엔 잔존). 초기값과 같으면 무동작(마운트 무해).
  const lastClearSignalRef = useRef(clearSignal ?? 0);
  useEffect(() => {
    const sig = clearSignal ?? 0;
    if (sig === lastClearSignalRef.current) return;
    lastClearSignalRef.current = sig;
    handleClearAll();
  }, [clearSignal, handleClearAll]);

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
          zoomControl: false, // 아래에서 좌하단으로 재부착(디자인컴프: 줌 좌하단)
        });
        L.control.zoom({ position: "bottomleft" }).addTo(map);

        // 텍스트/라벨 레이어가 폴리곤(overlayPane, 400) 위로 올라오도록 커스텀 Pane 생성
        const labelPane = map.createPane("labelPane");
        labelPane.style.zIndex = String(SATONG_PANE_Z.label);
        labelPane.style.pointerEvents = "none";
        L.control.attribution({ prefix: false, position: "bottomright" })
          .addTo(map)
          .addAttribution("VWorld · 국토교통부 공간정보 오픈플랫폼");
        mapRef.current = map;
        setMapReady(true);
        setMapZoom(map.getZoom());
        // 줌 변경 → 라벨 LOD 재판정(임계 교차 시에만 버짓이 바뀌어 라벨이 재부착된다).
        map.on("zoomend", () => setMapZoom(map.getZoom()));
        const focus = focusTargetRef.current;
        if (focus) {
          map.setView([focus.lat, focus.lon], 17);
        }

        // 지도 클릭 → 단일 팝오버(필지 선택·정보/거리재기) — 디자인컴프 계약.
        //   종전 '클릭 즉시 필지조회'는 팝오버의 [필지 선택·정보] 액션으로 이동(오클릭 시
        //   불필요한 /zoning/parcel-at-point 호출도 함께 제거). 거리재기 모드에선 클릭이
        //   측정점 추가로 전환된다.
        map.on("click", (e: any) => {
          if (readOnly) return;
          if (measureOnRef.current) {
            setMeasurePoints((prev) => {
              // Leaflet은 dblclick 전에 click을 2회 발화(알려진 동작) — 동일 좌표 중복점 스킵(R1 L1).
              const last = prev[prev.length - 1];
              if (last && Math.abs(last.lat - e.latlng.lat) < 1e-9 && Math.abs(last.lon - e.latlng.lng) < 1e-9) {
                return prev;
              }
              return [...prev, { lat: e.latlng.lat, lon: e.latlng.lng }];
            });
            return;
          }
          const pt = map.latLngToContainerPoint(e.latlng);
          const size = map.getSize();
          setClickMenu({ lat: e.latlng.lat, lon: e.latlng.lng, x: pt.x, y: pt.y, w: size.x, h: size.y });
        });
        // 팝오버는 지도 조작 시작과 함께 닫는다(고정 픽셀 앵커라 이동 시 어긋남 방지).
        map.on("movestart zoomstart", () => setClickMenu(null));
        // 더블클릭 = 측정 종료(측정 중 doubleClickZoom은 별도 이펙트에서 비활성).
        map.on("dblclick", () => {
          if (measureOnRef.current) setMeasureOn(false);
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
      presaleAuctionLayerRef.current = null;
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
  // (결합 해소: #182의 타일 재시도 tileRetryNonce 의존성 + main #197의 연속지적도 오버레이 이펙트 모두 보존)
  }, [baseLayerMode, mapReady, tileRetryNonce]);

  // VWorld 연속지적도 전체 오버레이 타일 (showCadastre 활성화 시 지도 전체 렌더)
  const cadastreTileRef = useRef<any>(null);
  const showCadastreTile = hasSatongLayer(layerState, "cadastre");
  // V1: 항공(위성·하이브리드) 뷰 여부 — 지적을 '선 스타일'로 전환(채움은 항공 가독 저해).
  //   boolean 파생으로 dep을 좁혀 동일 범주 내 베이스 전환(Base↔gray 등)의 재부설을 막는다(R1 L1).
  const aerialView = baseLayerMode === "Satellite" || baseLayerMode === "Hybrid";
  useEffect(() => {
    aerialViewRef.current = aerialView;
  }, [aerialView]);

  // ── 전국 지적편집도(용도지역 LT_C_UQ111) 오버레이 — jootek/카카오 지적편집도 패리티 ──
  //   기존 '용도지역'은 선택 필지만 색칠 → land-use-wide 컨트롤을 켜면 화면 전체를
  //   VWorld 용도지역 색상으로 덮는다(프록시 화이트리스트에 2026-07-17 허용).
  const zoningWideTileRef = useRef<any>(null);
  const [zoningWideNote, setZoningWideNote] = useState("");
  const showZoningWide =
    hasSatongLayer(layerState, "zoning") && hasSatongLayerControl(layerState, "zoning", "land-use-wide");
  /* eslint-disable react-hooks/set-state-in-effect -- Imperative Leaflet tile layer wiring. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;
    if (zoningWideTileRef.current) {
      try { map.removeLayer(zoningWideTileRef.current); } catch { /* noop */ }
      zoningWideTileRef.current = null;
    }
    if (!showZoningWide) {
      setZoningWideNote("");
      return;
    }
    const tile = L.tileLayer.wms("/tiles/vworld/wms", {
      layers: "lt_c_uq111",
      styles: "lt_c_uq111",
      format: "image/png",
      transparent: true,
      version: "1.3.0", // VWorld WMS는 1.3.0만 허용(#347 채증)
      opacity: 0.55, // 베이스맵 지형·도로가 비치게(전면 오버레이의 가독 균형)
      zIndex: 3, // 베이스 타일 위, 폴리곤(overlayPane)·라벨 pane 아래
      maxZoom: 19,
      minZoom: 7,
      attribution: "VWorld 용도지역(지적편집도)",
    });
    tile.on("tileerror", () => setZoningWideNote("지적편집도 타일 조회 실패 — 지적 배지의 자가진단으로 원인 확인"));
    tile.on("tileload", () => setZoningWideNote((prev) => (prev ? "" : prev)));
    tile.addTo(map);
    zoningWideTileRef.current = tile;
    return () => {
      try { map.removeLayer(tile); } catch { /* noop */ }
      if (zoningWideTileRef.current === tile) zoningWideTileRef.current = null;
    };
  }, [mapReady, showZoningWide]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // ── 규제 오버레이(지구단위·개발행위 제한·상수원·교육환경·고도지구) — WMS 다중 레이어 ──
  //   zoning 플레이스홀더 컨트롤의 잠금 해제(2026-07-17 — GetCapabilities+GetMap 매트릭스
  //   채증 후 활성화). 활성 컨트롤들을 콤마 조인한 한 장의 WMS 타일로 부설한다(조합이
  //   바뀌면 재부설). 매핑 SSOT는 satong-map-layers.REGULATION_WMS_BY_CONTROL.
  const regulationTileRef = useRef<any>(null);
  const [regulationNote, setRegulationNote] = useState("");
  const regulationWmsLayers = useMemo(() => resolveRegulationWmsLayers(layerState), [layerState]);
  /* eslint-disable react-hooks/set-state-in-effect -- Imperative Leaflet tile layer wiring. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;
    if (regulationTileRef.current) {
      try { map.removeLayer(regulationTileRef.current); } catch { /* noop */ }
      regulationTileRef.current = null;
    }
    if (!regulationWmsLayers) {
      setRegulationNote("");
      return;
    }
    const tile = L.tileLayer.wms("/tiles/vworld/wms", {
      layers: regulationWmsLayers,
      styles: regulationWmsLayers, // VWorld는 레이어명과 동명 스타일 사용(uq111 관례 동일)
      format: "image/png",
      transparent: true,
      version: "1.3.0", // VWorld WMS는 1.3.0만 허용(#347 채증)
      opacity: 0.6,
      zIndex: 4, // z 스케일: zoningWide(3) < 규제(4) < 지적선(5) — 채움이 지적선을 못 덮는다
      maxZoom: 19,
      minZoom: 7,
      attribution: "VWorld 규제(도시계획·보호구역)",
    });
    tile.on("tileerror", () => setRegulationNote("규제 오버레이 타일 조회 실패 — 지적 배지의 자가진단으로 원인 확인"));
    tile.on("tileload", () => setRegulationNote((prev) => (prev ? "" : prev)));
    tile.addTo(map);
    regulationTileRef.current = tile;
    return () => {
      try { map.removeLayer(tile); } catch { /* noop */ }
      if (regulationTileRef.current === tile) regulationTileRef.current = null;
    };
  }, [mapReady, regulationWmsLayers]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (cadastreTileRef.current) {
      try { map.removeLayer(cadastreTileRef.current); } catch { /* noop */ }
      cadastreTileRef.current = null;
    }

    if (!showCadastreTile) {
      setCadastreTileNote("");
      return;
    }

    // ★WP-M5: 연속지적도만 프론트 서버 프록시(/tiles/vworld/wms) 경유로 부설한다.
    //   (1) API 키를 브라우저 번들에 노출하지 않는다 — 키·domain 은 프록시가 서버측에서 주입.
    //       (종전 하드코딩 폴백 키 + api.vworld.kr 직결 = 자기 원칙(타일 프록시) 위반이었다.)
    //   (2) 용도지역 WMS(LT_C_UQ111)는 여기서 함께 깔지 않는다 — '용도지역' 레이어 소관
    //       (의미 1:1). 지적 토글에 겹쳐 부설하면 위성 가림·표현 중복을 유발했다.
    // ★V1(R1 블로킹 → 라이브 매트릭스 재채증): _line은 '레이어'가 아니라 '스타일'이다 —
    //   LAYERS=_line은 XML 오류, LAYERS=채움+STYLES=_line이 image/png(항공 위 경계선 룩).
    //   위성·하이브리드에서만 선 스타일, 일반/회색은 채움 스타일.
    const cadastreLayers = "lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun";
    const cadastreStyles = aerialView
      ? "lp_pa_cbnd_bubun_line,lp_pa_cbnd_bonbun_line"
      : cadastreLayers;
    const cadastreTile = L.tileLayer.wms("/tiles/vworld/wms", {
      layers: cadastreLayers,
      styles: cadastreStyles,
      format: "image/png",
      transparent: true,
      // ★근본원인 수정(2026-07-17 라이브 채증): VWorld WMS는 VERSION 1.3.0만 허용한다 —
      //   1.1.1은 키 검증보다도 먼저 INVALID_RANGE로 거부된다("유효한 파라미터 값의 범위:
      //   [1.3.0]"). Leaflet 기본값이 1.1.1이라 version 미지정 시 지적 타일 전체가 실패했고,
      //   프록시 분류기가 이 XML을 auth로 승격해 "키 미설정" 오해 메시지가 표시됐다.
      //   1.3.0에서는 Leaflet이 SRS 대신 CRS 파라미터를 전송한다(정상 — VWorld 수용).
      version: "1.3.0",
      // ★z 스케일(2026-07-18 R1 MAJOR 반영): zoningWide=3 < regulation=4 < cadastre=5.
      //   종전 지적=4는 규제 오버레이(4)와 동률 — 같은 pane에서 동률 z는 DOM 삽입 순서로
      //   갈려, 나중에 켠 규제 채움(opacity .6)이 기본-온 지적선을 덮었다(불변식 위반).
      //   지적선은 모든 채움 오버레이 '위'가 계약이므로 5로 승격.
      zIndex: 5,
      maxZoom: 19,
      minZoom: 10,
      attribution: "VWorld 연속지적도",
    });
    // ★PR#329 R1 리뷰(MEDIUM2) 반영: 종전엔 tileerror 핸들러가 없어 키 미설정/상류 오류
    //   시 지도가 빈 채로(무노트) 남았다(무목업 원칙 위반). 실패를 관측 가능한 노트로
    //   표면화하고, 이후 로드가 성공하면(부분 성공 포함) 노트를 지운다.
    cadastreTile.on("tileerror", () => {
      // 모호한 고정 문구 대신 자동진단으로 실원인 코드를 표면화(60초 스로틀 — 타일 다발 오류 대비).
      setCadastreTileNote((prev) => prev || "지적 타일 오류 — 원인 진단 중…");
      autoDiagnoseRef.current?.();
    });
    cadastreTile.on("tileload", () => {
      setCadastreTileNote((prev) => (prev ? "" : prev));
    });
    cadastreTile.addTo(map);
    cadastreTileRef.current = cadastreTile;

    return () => {
      if (cadastreTileRef.current) {
        try { map.removeLayer(cadastreTileRef.current); } catch { /* noop */ }
        cadastreTileRef.current = null;
      }
    };
  }, [mapReady, showCadastreTile, aerialView]);
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
    const showCapacity = hasSatongLayer(layerState, "capacity") && hasSatongLayerControl(layerState, "capacity", "far-headroom");
    const needsOverlay = showCadastre || showZoning || showPrice || showAge || showCapacity;

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
    let capacityCount = 0;
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
          // 색면 클릭이 지도 클릭(팝오버)으로 번지지 않게 — 색면 클릭 = 자기 정보 팝업만(U6).
          bubblingMouseEvents: false,
          ...style,
          ...(statusColor ? { color: statusColor, fillColor: statusColor } : {}),
          // 하이라이트(선택 강조) = primary 블루 — 디자인컴프 정합(#ef4444 에러적색은 컴프 위반).
          ...(isHighlighted ? { color: "#135bec", weight: 4, fillOpacity: 0.5 } : {}),
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

      if (showCapacity && hasGeometry) {
        const color = capacityColor(feature.effectiveFarPct, feature.currentFarPct);
        if (color) {
          capacityCount += 1;
          drawPolygon({ color, weight: 2.5, fillColor: color, fillOpacity: 0.5 });
        }
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
          bubblingMouseEvents: false, // 점 클릭 = 정보 팝업만(지도 클릭 팝오버로 미전파 — U6)
        }).bindPopup(popup, { maxWidth: 280 }).on("click", () => onFeatureClick?.(feature)).addTo(group);
        bounds.extend([feature.lat, feature.lon]);
      }
    });

    setOverlayNote(buildOverlayNotes({
      showCadastre,
      cadastreCount,
      showZoning,
      zoningCount,
      showPrice,
      priceCount,
      showAge,
      ageCount,
      showCapacity,
      capacityCount,
      markerCount,
      // 노후도 0건일 때 사유 세분("나대지 N·미준공 P·조회실패 M·대량생략 K") — 정직 무자료 고지(WP-M3).
      ageNoBuilding: ageStatusCounts.ageNoBuilding,
      ageNoApprovalDate: ageStatusCounts.ageNoApprovalDate,
      ageLookupFailed: ageStatusCounts.ageLookupFailed,
      ageSkippedBulk: ageStatusCounts.ageSkippedBulk,
    }));

    const fitKey = overlayFeatures.map(satongMapFeatureKey).join("||");
    if (fitKey && fitKey !== lastFitKeyRef.current && bounds.isValid()) {
      const isMapClick = isMapClickSelectionRef.current;
      lastFitKeyRef.current = fitKey;
      // ★지도 직접 클릭 선택 시에는 사용자 줌 레벨(Zoom 18~19 등)을 100% 보존 (줌아웃 축소 차단)
      if (!isMapClick) {
        try { map.fitBounds(bounds, { padding: [36, 36], maxZoom: 17 }); } catch { /* noop */ }
      }
      isMapClickSelectionRef.current = false;
    }

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (overlayLayerRef.current === group) overlayLayerRef.current = null;
	    };
	  }, [
    ageStatusCounts,
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

  // ── 선택 필지(연결 프로젝트·staged·pending) 식별 라벨 — 전역 라벨 버짓·줌 LOD 무관 항상 표시 ──
  //   ★PR#329 R1 리뷰(LOW1) 반영: 홈 초기 진입(줌 12)은 hover-only LOD라 시장/POI/개발계획
  //   상시 라벨이 0개인데, 사용자가 지도를 연 '목적'인 선택 필지 자체까지 사라지면 첫인상이
  //   빈 지도가 된다. 이 라벨은 labelPlan(전역 48/16/0 버짓) 대상이 아닌 별도 always-on
  //   트랙이다 — 상위 오버레이 색칠 이펙트(showCadastre 등 토글 게이트)와도 독립적이라,
  //   레이어 토글을 하나도 켜지 않은 상태(초기 연결 직후)에도 필지가 식별된다.
  //   시각 마커(폴리곤·staged 초록점)는 다른 이펙트가 이미 그리므로, 여기서는 투명 앵커
  //   포인트에 라벨만 부착한다(중복 마커 방지).
  const selectionLabelLayerRef = useRef<any>(null);
  // 롤업 여부만 dep로 — LOD 임계(z=15) 교차 시에만 라벨 재부착(줌마다 teardown 낭비 방지 — R1 L2).
  const selectionRollup = satongLabelLOD(mapZoom) === "hover-only";
  /* eslint-disable react-hooks/set-state-in-effect -- Selection labels are rendered into an imperative Leaflet layer group. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (selectionLabelLayerRef.current) {
      try { selectionLabelLayerRef.current.remove(); } catch { /* noop */ }
      selectionLabelLayerRef.current = null;
    }
    if (overlayFeatures.length === 0) return;

    const group = L.layerGroup().addTo(map);
    selectionLabelLayerRef.current = group;

    const points = overlayFeatures
      .map((feature) => ({
        feature,
        point:
          feature.lat != null && feature.lon != null
            ? { lat: feature.lat, lon: feature.lon }
            : geometryRepresentativePoint(feature.geometry),
      }))
      .filter((e): e is { feature: (typeof overlayFeatures)[number]; point: { lat: number; lon: number } } => !!e.point);
    if (points.length === 0) return;

    const makeAnchor = (lat: number, lon: number) =>
      L.circleMarker([lat, lon], { radius: 0, opacity: 0, fillOpacity: 0, interactive: false }).addTo(group);

    // ★줌 롤업(U-라벨 파일업): 줌아웃(hover-only LOD)에서 다필지 주소 라벨을 전부 상시
    //   표시하면 한 점에 겹겹이 쌓인다(12필지 주소 파일업). 줌아웃+다필지에서는 집계 칩
    //   1개("선택 N필지 · 합산㎡")로 롤업하고, 줌인(z≥15)에서만 필지별 '짧은 지번' 라벨을
    //   단다. 단일 필지는 어느 줌에서도 개별 라벨(초기 진입 식별 — PR#329 LOW1 의도 유지).
    if (selectionRollup && points.length > 1) {
      const centroid = {
        lat: points.reduce((s, e) => s + e.point.lat, 0) / points.length,
        lon: points.reduce((s, e) => s + e.point.lon, 0) / points.length,
      };
      // ★정직표기(R1 M1): 면적은 라벨이 세는 피처(points)와 같은 모집단으로 합산하고,
      //   결측이 하나라도 있으면 부분합을 전체합처럼 보이게 하지 않도록 면적 표기를 생략한다.
      const hasAllAreas = points.every((e) => (e.feature.areaSqm ?? 0) > 0);
      const totalArea = points.reduce((s, e) => s + (e.feature.areaSqm || 0), 0);
      const label = `선택 ${points.length}필지${hasAllAreas && totalArea > 0 ? ` · ${Math.round(totalArea).toLocaleString()}㎡` : ""}`;
      bindSatongLabel(makeAnchor(centroid.lat, centroid.lon), label, { permanent: true, offsetY: 2 });
    } else {
      points.forEach(({ feature, point }) => {
        bindSatongLabel(
          makeAnchor(point.lat, point.lon),
          shortJibunLabel(feature.address, feature.pnu || "필지"),
          { permanent: true, offsetY: 2 },
        );
      });
    }

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (selectionLabelLayerRef.current === group) selectionLabelLayerRef.current = null;
    };
  }, [mapReady, overlayFeatures, selectionRollup]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // ── 거리재기 — 측정 모드 동기화·측정점/폴리라인/누적거리 렌더·모드 UX·ESC ──
  useEffect(() => {
    measureOnRef.current = measureOn;
  }, [measureOn]);

  /* eslint-disable react-hooks/set-state-in-effect -- Measure shapes are rendered into an imperative Leaflet layer group. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;
    if (measureLayerRef.current) {
      try { measureLayerRef.current.remove(); } catch { /* noop */ }
      measureLayerRef.current = null;
    }
    if (measurePoints.length === 0) return;

    const group = L.layerGroup().addTo(map);
    measureLayerRef.current = group;
    const latlngs = measurePoints.map((p) => [p.lat, p.lon] as [number, number]);
    latlngs.forEach((ll) => {
      L.circleMarker(ll, {
        radius: 4, color: "#135bec", weight: 2, fillColor: "#ffffff", fillOpacity: 1,
        interactive: false, // 측정점이 다음 클릭(점 추가)을 가로채지 않게
      }).addTo(group);
    });
    if (measureMode === "area" && latlngs.length >= 3) {
      // 면적재기(I6): 채움 폴리곤 + 중심 면적 라벨(둘레는 칩에서 병기).
      L.polygon(latlngs, {
        color: "#135bec", weight: 3, dashArray: "6 6", fillColor: "#135bec", fillOpacity: 0.12,
        interactive: false,
      }).addTo(group);
      const centroid: [number, number] = [
        measurePoints.reduce((s, p) => s + p.lat, 0) / measurePoints.length,
        measurePoints.reduce((s, p) => s + p.lon, 0) / measurePoints.length,
      ];
      const anchor = L.circleMarker(centroid, {
        radius: 0, opacity: 0, fillOpacity: 0, interactive: false,
      }).addTo(group);
      bindSatongLabel(anchor, formatAreaSqm(polygonAreaSqm(measurePoints)), { permanent: true, offsetY: 0 });
    } else if (latlngs.length >= 2) {
      L.polyline(latlngs, { color: "#135bec", weight: 3, dashArray: "6 6", interactive: false }).addTo(group);
      // 누적 거리 라벨 — 마지막 점 위 상시 표시(순수계산 satong-measure).
      const anchor = L.circleMarker(latlngs[latlngs.length - 1], {
        radius: 0, opacity: 0, fillOpacity: 0, interactive: false,
      }).addTo(group);
      bindSatongLabel(anchor, `누적 ${formatDistance(totalDistanceMeters(measurePoints))}`, { permanent: true, offsetY: -10 });
    }
    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (measureLayerRef.current === group) measureLayerRef.current = null;
    };
  }, [mapReady, measurePoints, measureMode]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // 측정 모드 UX — 더블클릭줌 비활성(더블클릭=종료 제스처와 충돌)·크로스헤어 커서.
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    if (measureOn) {
      try { map.doubleClickZoom.disable(); } catch { /* noop */ }
      if (mapEl.current) mapEl.current.style.cursor = "crosshair";
    } else {
      try { map.doubleClickZoom.enable(); } catch { /* noop */ }
      if (mapEl.current) mapEl.current.style.cursor = "";
    }
  }, [mapReady, measureOn]);

  // ESC 단계적 해제 — ①팝오버 닫기 → ②측정 종료 → ③측정 결과 지우기.
  useEffect(() => {
    if (!clickMenu && !measureOn && measurePoints.length === 0) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key !== "Escape") return;
      if (clickMenu) { setClickMenu(null); return; }
      if (measureOn) { setMeasureOn(false); return; }
      setMeasurePoints([]);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [clickMenu, measureOn, measurePoints.length]);

  // 클릭 지점의 오버레이 피처(용도지역·공시지가·노후도 색면) — 팝오버 헤더 정보(레이캐스팅).
  const clickMenuFeature = useMemo(() => {
    if (!clickMenu) return null;
    return findFeatureAtPoint(clickMenu.lat, clickMenu.lon, overlayFeatures, (f) =>
      geoJsonToLeafletRings(f.geometry),
    );
  }, [clickMenu, overlayFeatures]);

  // marketLayer에서 마커 이펙트가 실제로 읽는 원시값·참조만 뽑아 구독을 협소화한다(리뷰 LOW) —
  //   marketLayer 객체 identity가 바뀌어도(다른 필드 갱신) 아래 값이 같으면 마커를 다시 그리지
  //   않아, 분양 items 도착이 실거래 마커 재생성·재fitBounds를 유발하던 낭비를 끊는다.
  const marketKind = marketLayer?.kind ?? "trade";
  // 실거래 라벨 총액/평당 토글(jootek 패리티) — transactions 레이어의 unit-price 컨트롤.
  const pricePerPyeongOn = hasSatongLayerControl(layerState, "transactions", "unit-price");
  const marketType = marketLayer?.type ?? "apt";
  const showPresale = !!marketLayer?.showPresale;
  const presaleItems = marketLayer?.presaleItems ?? null;
  const showAuction = !!marketLayer?.showAuction;
  const auctionItems = marketLayer?.auctionItems ?? null;

  // ── 라벨(상시 툴팁) 시스템 — 레이어별 후보 수 집계 → 전역 버짓 배분(줌 LOD) ──
  //   각 레이어는 자기 몫(permanentLimit)만큼만 선두 마커에 상시 라벨을 붙이고 나머지는 hover.
  //   ★후보 수는 '실제로 렌더될 라벨'만 센다(레이어 off → 0). 합산이 버짓(48/16/0)을 넘지 않는다.
  const marketMappableCount = useMemo(() => {
    if (!marketPayload?.center?.lat || !marketPayload?.center?.lon || marketPayload.fetch_failed) return 0;
    const cat = marketPayload.categories?.[`${marketType}_${marketKind}`];
    return (cat?.groups ?? []).filter((g) => !!g.lat && !!g.lon).length;
  }, [marketPayload, marketKind, marketType]);
  const presaleMappableCount = useMemo(
    () => (showPresale ? (presaleItems ?? []).filter((i) => !!i.lat && !!i.lon).length : 0),
    [showPresale, presaleItems],
  );
  const auctionMappableCount = useMemo(
    () => (showAuction ? (auctionItems ?? []).filter((i) => !!i.lat && !!i.lon).length : 0),
    [showAuction, auctionItems],
  );
  const poiMappableCount = useMemo(() => {
    if (!poiPayload || poiPayload.available === false) return 0;
    const cats = poiPayload.categories || {};
    let total = 0;
    for (const [control, codes] of Object.entries(POI_CONTROL_CODES)) {
      if (!hasSatongLayerControl(layerState, "poi", control)) continue;
      for (const code of codes) {
        total += (cats[code]?.items || []).filter(
          (item) => typeof item.lat === "number" && typeof item.lon === "number",
        ).length;
      }
    }
    return total;
  }, [poiPayload, layerState]);
  const devMappableCount = useMemo(
    () =>
      (developmentPayload?.facilities || []).filter(
        (f) => typeof f.lat === "number" && typeof f.lon === "number",
      ).length,
    [developmentPayload],
  );
  const labelPlan = useMemo(
    () =>
      planSatongLabels(mapZoom, [
        { id: "market", count: marketMappableCount },
        { id: "presale", count: presaleMappableCount },
        { id: "auction", count: auctionMappableCount },
        { id: "poi", count: poiMappableCount },
        { id: "development", count: devMappableCount },
      ]),
    [mapZoom, marketMappableCount, presaleMappableCount, auctionMappableCount, poiMappableCount, devMappableCount],
  );
  const marketLabelLimit = labelPlan.market ?? 0;
  const presaleLabelLimit = labelPlan.presale ?? 0;
  const auctionLabelLimit = labelPlan.auction ?? 0;
  const poiLabelLimit = labelPlan.poi ?? 0;
  const devLabelLimit = labelPlan.development ?? 0;

  /* eslint-disable react-hooks/set-state-in-effect -- Market markers are rendered into an imperative Leaflet layer group. */
  useEffect(() => {
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (marketLayerRef.current) {
      try { marketLayerRef.current.remove(); } catch { /* noop */ }
      marketLayerRef.current = null;
    }

    if (!marketPayload?.center?.lat || !marketPayload?.center?.lon || marketPayload.fetch_failed) {
      setMarketNote(marketPayload?.fetch_failed ? marketPayload.note || "실거래 공공데이터 조회 실패" : "");
      return;
    }

    const group = L.layerGroup().addTo(map);
    marketLayerRef.current = group;
    const bounds = L.latLngBounds([]);
    const kind = marketKind;
    const type = marketType;
    const category = marketPayload.categories?.[`${type}_${kind}`];
    const groups = category?.groups ?? [];
    const typeColor = MARKET_TYPE_COLORS[type] || "#2563eb";
    let marketCount = 0;

    bounds.extend([marketPayload.center.lat, marketPayload.center.lon]);
    L.circleMarker([marketPayload.center.lat, marketPayload.center.lon], {
      radius: 9,
      color: "#ef4444",
      weight: 3,
      fillColor: "#ffffff",
      fillOpacity: 0.95,
      bubblingMouseEvents: false, // 점 클릭 = 정보 팝업만(U6)
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
        interactive: false, // 반경 링이 지도 클릭(필지 팝오버)을 가로채지 않게
      }).addTo(group);
    }

    groups.forEach((item) => {
      if (!item.lat || !item.lon) return;
      const ordinal = marketCount;
      marketCount += 1;
      const radius = Math.min(18, 7 + Math.round(Math.sqrt(Math.max(1, item.count)) * 1.5));
      const marker = L.circleMarker([item.lat, item.lon], {
        radius,
        color: "#ffffff",
        weight: 2,
        fillColor: typeColor,
        fillOpacity: 0.9,
        // ★U6 근본수정: L.Path(circleMarker) 기본 bubblingMouseEvents=true 라 점 클릭이
        //   지도 click으로 번져 필지선택(현 팝오버)이 함께 발동했다. 점 클릭 = 정보 팝업만.
        bubblingMouseEvents: false,
      })
        .bindPopup(marketPopupHtml(item, kind), { maxWidth: 300 })
        .addTo(group);
      // 정보 상시화(2026-07-17): 라벨에 평균가를 병기 — hover 없이도 핵심값이 보이게(jootek 가격 pill).
      // ★R1 #2: 팝업과 동일 공용 포맷터 won() 재사용 — 억미만 "0.4억" 어색 표기·라벨/팝업 불일치 제거.
      // 총액/평당 토글(실거래 unit-price 컨트롤 — jootek '총액/평당' 패리티): 평당가는
      // avg_price_10k(만원)/평(avg_area_m2/3.305785). 면적 결측 시 총액 폴백(정직).
      const perPyeong =
        pricePerPyeongOn && item.avg_price_10k && item.avg_area_m2 && item.avg_area_m2 > 0
          ? Math.round(item.avg_price_10k / (item.avg_area_m2 / 3.305785))
          : null;
      const priceTag =
        kind === "trade" && item.avg_price_10k
          ? perPyeong
            ? ` ${perPyeong.toLocaleString()}만/평`
            : ` ${won(item.avg_price_10k)}${pricePerPyeongOn ? "·총액" : ""}` // 평당 불가(면적결측) 혼재 명시(R1 #4)
          : "";
      bindSatongLabel(marker, `${item.name || "실거래"}${priceTag}`, { permanent: ordinal < marketLabelLimit, offsetY: radius });
      bounds.extend([item.lat, item.lon]);
    });

    // 분양·경매 노트는 독립 이펙트(presaleAuctionNote)가 담당 — 실거래만 여기서.
    setMarketNote(marketCount ? `실거래 ${marketCount}곳` : "실거래 무자료");

    // ★선택필지가 있을 때만 fitBounds(선택 대상지로 이동). 선택 없이 지도중심으로 탐색(브라우즈
    //   모드)할 땐 fitBounds 금지 — 사용자가 보던 화면을 유지하고, moveend→재조회 루프를 끊는다.
    //   ★fit-key 1회성 가드: 라벨 재부착(줌 임계 교차)로 이 이펙트가 재실행돼도 같은 대상지엔
    //     다시 fit 하지 않아 사용자 줌을 덮지 않는다.
    const marketFitKey = `${marketPayload.center.lat},${marketPayload.center.lon}|${kind}|${type}|${selectedParcelKey}`;
    if (bounds.isValid() && selectedParcels.length > 0 && marketFitKey !== lastMarketFitKeyRef.current) {
      lastMarketFitKeyRef.current = marketFitKey;
      try { map.fitBounds(bounds, { padding: [44, 44], maxZoom: 15 }); } catch { /* noop */ }
    }

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (marketLayerRef.current === group) marketLayerRef.current = null;
    };
  }, [mapReady, marketKind, marketType, marketPayload, marketLabelLimit, selectedParcelKey, selectedParcels.length, pricePerPyeongOn]);
  /* eslint-enable react-hooks/set-state-in-effect */

  /* eslint-disable react-hooks/set-state-in-effect -- Presale/auction markers are rendered into an imperative Leaflet layer group. */
  useEffect(() => {
    // ★P0-1: 분양·경매 렌더를 실거래(marketPayload) 이펙트에서 독립 분리.
    //   종전엔 market 이펙트 내부에 있어 실거래 레이어 OFF(기본값)거나 nearby-map 실패 시
    //   분양·경매가 데이터를 받아놓고도 마커·노트 없이 침묵(활성 배지+빈 지도 = 정직원칙 역위반).
    const map = mapRef.current;
    const L = window.L;
    if (!mapReady || !map || !L) return;

    if (presaleAuctionLayerRef.current) {
      try { presaleAuctionLayerRef.current.remove(); } catch { /* noop */ }
      presaleAuctionLayerRef.current = null;
    }

    if (!showPresale && !showAuction) {
      return;
    }

    const group = L.layerGroup().addTo(map);
    presaleAuctionLayerRef.current = group;

    if (showPresale) {
      let presaleShown = 0;
      (presaleItems ?? []).forEach((item) => {
        if (!item.lat || !item.lon) return;
        const ordinal = presaleShown;
        presaleShown += 1;
        const status = item.status || "미정";
        const color = PRESALE_STATUS_COLORS[status] || PRESALE_STATUS_COLORS["미정"];
        const icon = L.divIcon({
          className: "",
          html: `<div style="width:18px;height:18px;border-radius:5px;background:${escapeHtml(color)};border:2px solid #fff;box-shadow:0 4px 12px rgba(15,23,42,.28);transform:rotate(45deg);"></div>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11],
        });
        const marker = L.marker([item.lat, item.lon], { icon })
          .bindPopup(presalePopupHtml(item), { maxWidth: 300 })
          .addTo(group);
        bindSatongLabel(marker, item.name || "분양", { permanent: ordinal < presaleLabelLimit, offsetY: 11 });
      });
    }

    if (showAuction) {
      let auctionShown = 0;
      (auctionItems ?? []).forEach((item) => {
        if (!item.lat || !item.lon) return;
        const ordinal = auctionShown;
        auctionShown += 1;
        const status = item.status || "진행";
        const color = AUCTION_STATUS_COLORS[status] || AUCTION_STATUS_COLORS["진행"];
        const icon = L.divIcon({
          className: "",
          html: `<div style="width:20px;height:20px;border-radius:10px;background:${escapeHtml(color)};border:2px solid #fff;box-shadow:0 4px 12px rgba(15,23,42,.28);display:flex;align-items:center;justify-content:center;"><span style="color:#fff;font-size:10px;font-weight:900;">경</span></div>`,
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        });
        const marker = L.marker([item.lat, item.lon], { icon })
          .bindPopup(auctionPopupHtml(item), { maxWidth: 300 })
          .addTo(group);
        bindSatongLabel(marker, "경매물건", { permanent: ordinal < auctionLabelLimit, offsetY: 12 });
      });
    }

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (presaleAuctionLayerRef.current === group) presaleAuctionLayerRef.current = null;
    };
  }, [mapReady, showPresale, presaleItems, showAuction, auctionItems, presaleLabelLimit, auctionLabelLimit]);
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

    // 컨트롤(역·학교·상권·공원·병원)별로 켜진 것만 렌더 — 컨트롤 상태는 layerState가 SSOT.
    //   상시 라벨은 선두 poiLabelLimit 개만(전역 버짓 배분·줌 LOD), 나머지는 hover 강등.
    for (const [control, codes] of Object.entries(POI_CONTROL_CODES)) {
      if (!hasSatongLayerControl(layerState, "poi", control)) continue;
      const color = POI_CONTROL_COLORS[control] || "#0ea5e9";
      for (const code of codes) {
        const items = cats[code]?.items || [];
        const label = cats[code]?.label || code;
        for (const item of items) {
          if (typeof item.lat !== "number" || typeof item.lon !== "number") continue;
          const ordinal = poiCount;
          poiCount += 1;
          // ★WP-M3: POI는 '흰 코어+색 링+흰 헤일로' 도넛(타겟) 형태로 그린다. POI_CONTROL_COLORS가
          //   AGE_RAMP(노후도 폴리곤)와 팔레트가 겹쳐 '색 점=노후도'로 오인되던 문제를, 색이 아닌
          //   형태(링)로 분리한다. 노후도는 채워진 폴리곤, POI는 속 빈 링 → 시각 구분이 명확.
          // ★리뷰(LOW): 렌더 실제 크기(content-box 14px + border 3px×2=6px = 20px)와
          //   iconSize/anchor를 일치시킨다(종전 17/8.5는 3px 과소평가 — 앵커가 1.5px 어긋났다).
          const icon = L.divIcon({
            className: "",
            html: `<div style="width:14px;height:14px;border-radius:50%;background:#ffffff;border:3px solid ${escapeHtml(color)};box-shadow:0 0 0 1.5px #ffffff,0 1px 3px rgba(15,23,42,.35);"></div>`,
            iconSize: [20, 20],
            iconAnchor: [10, 10],
          });
          const marker = L.marker([item.lat, item.lon], { icon })
            .bindPopup(
              `<div style="padding:6px 9px;font-size:12px;line-height:1.5;">` +
                `<b>${escapeHtml(item.name || label)}</b>` +
                `<br/>${escapeHtml(label)}${item.distance_m != null ? ` · ${Math.round(item.distance_m).toLocaleString()}m` : ""}` +
                `</div>`,
              { maxWidth: 260 },
            )
            .addTo(group);
          bindSatongLabel(marker, item.name || label, { permanent: ordinal < poiLabelLimit, offsetY: 10 });
        }
      }
    }
    setPoiNote(poiCount ? `POI ${poiCount}곳` : "POI 무자료");

    return () => {
      try { group.remove(); } catch { /* noop */ }
      if (poiLayerRef.current === group) poiLayerRef.current = null;
    };
  }, [mapReady, poiPayload, layerState, poiLabelLimit]);
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
    // 상시 라벨은 선두 devLabelLimit 개만(전역 버짓 배분·줌 LOD), 나머지는 hover 강등(예: 67건 밀집).
    for (const fac of facilities) {
      if (typeof fac.lat !== "number" || typeof fac.lon !== "number") continue;
      const ordinal = devCount;
      devCount += 1;
      const marker = L.circleMarker([fac.lat, fac.lon], {
        radius: 6,
        color: "#7c3aed",       // 보라 — 개발계획(도시계획시설)
        weight: 2,
        fillColor: "#ede9fe",
        fillOpacity: 0.9,
        bubblingMouseEvents: false, // 점 클릭 = 정보 팝업만(U6)
      })
        .bindPopup(
          `<div style="padding:6px 9px;font-size:12px;line-height:1.5;">` +
            `<b>${escapeHtml(fac.name || "(명칭 미상)")}</b>` +
            `<br/>${escapeHtml(fac.type || "도시계획시설")} · ${escapeHtml(fac.status || "확인필요")}` +
            `${fac.distance_m != null ? `<br/>거리 ${Math.round(fac.distance_m).toLocaleString()}m` : ""}` +
            `</div>`,
          { maxWidth: 260 },
        )
        .addTo(group);
      bindSatongLabel(marker, fac.name || "개발계획", { permanent: ordinal < devLabelLimit, offsetY: 6 });
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
  }, [mapReady, developmentPayload, devLabelLimit]);
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

  // ★WP-M2 CTA 이중표기: 신규(=staged∖selectedParcels)와 총(=selectedParcels+신규)을 분리 집계.
  //   "지적 12건(칩)"↔"완료 1필지(CTA)" 혼란의 원천을 CTA에서 "신규 N · 총 M"으로 못박는다.
  const newStaged = useMemo(
    () => staged.filter((s) => !selectedMembershipKeys.has(parcelMembershipKey(s))),
    [staged, selectedMembershipKeys],
  );
  const newCount = newStaged.length;
  const totalCount = selectedMembershipKeys.size + newCount;
  // 합산 면적은 신규 staged 기준(총 면적은 프로젝트 목록/분석에서 별도 집계).
  const totalAreaSqm = newStaged.reduce((acc, p) => acc + (p.area_sqm ?? 0), 0);

  // pending이 이미 staged에 있는지 / 프로젝트에 이미 등록됐는지(확인 카드 표시용)
  const pendingAlreadyStaged = pending?.pnu
    ? staged.some((s) => s.pnu === pending.pnu)
    : false;
  const pendingAlreadyRegistered = pending
    ? selectedMembershipKeys.has(parcelMembershipKey(pending))
    : false;

  // [MAP-007] 기반 타일 실패 오버레이(순수 판정) — error일 때만 메시지+재시도 노출
  const tileFailureNotice = buildTileFailureNotice(tileStatus);

  // 분양·경매 노트(렌더 파생) — 상태 노트 prop(좌표 대기·로그인 필요·조회 실패)이 오면 건수
  // 라벨보다 우선해 '무자료'와 '아직 조회 못함/권한 없음'을 구분한다(정직원칙). 건수는 items에서
  // 직접 계산(마커 렌더와 동일 좌표 필터) — 상태 경유로 1커밋 늦게 따라오던 깜빡임 제거.
  // 노트만 바뀔 땐 마커 이펙트가 돌지 않는다(리뷰 LOW 해소).
  const countMappable = (items: Array<{ lat?: number | null; lon?: number | null }> | null) =>
    (items ?? []).filter((item) => !!item.lat && !!item.lon).length;
  const presaleCount = showPresale ? countMappable(presaleItems) : 0;
  const auctionCount = showAuction ? countMappable(auctionItems) : 0;
  const presaleAuctionNote = [
    showPresale ? presaleNote || (presaleCount ? `분양 ${presaleCount}곳` : "분양 무자료") : "",
    showAuction ? auctionNote || (auctionCount ? `경매 ${auctionCount}곳` : "경매 무자료") : "",
  ].filter(Boolean).join(" · ");

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
          지도를 클릭하면 선택·정보·거리재기 메뉴가 열립니다. [필지 선택·정보] → [＋추가]로 담고 [완료]로 등록하세요.
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
        {/* 줌 컨트롤은 좌하단(디자인컴프) — 상단 칩바 겹침 CSS 불필요. ping은 마커 애니메이션용. */}
        <style jsx global>{`
          @keyframes ping {
            75%, 100% {
              transform: scale(2);
              opacity: 0;
            }
          }
        `}</style>
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
          className="absolute right-2 top-2 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)]/90 p-1.5 text-[var(--text-secondary)] shadow hover:bg-[var(--surface-muted)] transition-colors"
          style={{ zIndex: SATONG_UI_Z.fullscreenButton }}
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

        {/* ── V2 측정 rail(VWorld 공식 프로토타입 패턴) — 팝오버 진입과 병행하는 상시 도구 ── */}
        {!readOnly && (
          <div
            // ★위치 이력(재발 방지): 우상단→셸 레이어 레일(right-4 top-20)과 겹침(R1 M1) →
            //   좌하단 bottom-28로 이동 → ★다시 줌 컨트롤과 중첩(2026-07-17 라이브 신고).
            //   근본원인: 이 absolute의 기준은 지도가 아니라 '래퍼'(하단 완료바 포함 — :2536
            //   배너 주석과 동일 함정)라, bottom-28(112px)이 지도 기준으로는 완료바 높이만큼
            //   내려앉아(≈50px) 지도 기준 10~78px의 줌 '+' 버튼을 정확히 덮었다.
            //   → 좌중앙(top-1/2) 앵커로 이동: 줌(좌하단)·레이어 레일(우측)·저줌 배너(하단)·
            //   완료바(하단) 어느 것과도 세로 대역이 겹치지 않는 유일한 좌측 슬롯.
            //   ★정직 고지(R1): 앵커 공식은 완료바 유무에 불변이지만 **충돌무결성은 높이
            //   의존**이다 — 지도 높이 H<약 282px면 rail 하단이 줌 '+'와 재중첩한다(rail은
            //   래퍼 중앙 비례·줌은 지도 바닥 고정 오프셋이라). 현행 비-readOnly 콜러 최소
            //   높이 500 → 안전 마진 ≥69px. 새 콜러는 500px 미만 높이 배치 금지.
            //   left-4=16px — DESIGN.md B3.1:218
            //   "플로팅 컨트롤 가장자리 16~24px 이격" 충족(종전 left-3=12px는 미달).
            className="pointer-events-auto absolute left-4 top-1/2 flex -translate-y-1/2 flex-col gap-1 rounded-xl border border-[var(--border-muted)] bg-[var(--glass-bg)] p-1 shadow-lg backdrop-blur"
            style={{ zIndex: SATONG_UI_Z.fullscreenButton }}
          >
            <button
              type="button"
              aria-label="거리재기 도구"
              aria-pressed={measureOn && measureMode === "distance"}
              title="거리재기 — 지도 클릭으로 점 추가, 더블클릭/ESC 종료"
              onClick={() => {
                if (measureOn && measureMode === "distance") { setMeasureOn(false); return; } // 재클릭=종료(R1 L4)
                setMeasureMode("distance");
                setMeasurePoints([]);
                setMeasureOn(true);
              }}
              className={`grid size-9 place-items-center rounded-lg border transition ${
                measureOn && measureMode === "distance"
                  ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15 text-[var(--accent-strong)]"
                  : "border-transparent text-[var(--text-secondary)] hover:border-[var(--line-strong)]"
              }`}
            >
              <Ruler className="size-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="면적재기 도구"
              aria-pressed={measureOn && measureMode === "area"}
              title="면적재기 — 점 3개 이상, 더블클릭/ESC 종료"
              onClick={() => {
                if (measureOn && measureMode === "area") { setMeasureOn(false); return; } // 재클릭=종료(R1 L4)
                setMeasureMode("area");
                setMeasurePoints([]);
                setMeasureOn(true);
              }}
              className={`grid size-9 place-items-center rounded-lg border transition ${
                measureOn && measureMode === "area"
                  ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15 text-[var(--accent-strong)]"
                  : "border-transparent text-[var(--text-secondary)] hover:border-[var(--line-strong)]"
              }`}
            >
              <LandPlot className="size-4" aria-hidden />
            </button>
          </div>
        )}

        {/* ── 지도 클릭 팝오버(단일 팝오버 — 디자인컴프) : 필지 선택·정보 / 거리재기 / 닫기 + 출처 푸터 ── */}
        {clickMenu && !readOnly && (() => {
          const pos = clampClickMenuPosition(
            { x: clickMenu.x, y: clickMenu.y },
            { width: clickMenu.w, height: clickMenu.h },
            // ★w-64(256px)·좌표행 추가 반영 — 컨테이너 실측과 동기 유지(어긋나면 화면 밖 클램프 오차).
            { width: 256, height: 232 },
          );
          const subInfo = [
            clickMenuFeature?.zoneType || null,
            clickMenuFeature?.officialPricePerSqm
              ? `공시 ${Math.round(clickMenuFeature.officialPricePerSqm).toLocaleString()}원/㎡`
              : null,
            clickMenuFeature?.buildingAgeYears != null ? `노후 ${clickMenuFeature.buildingAgeYears}년` : null,
          ].filter(Boolean);
          const coordText = `${clickMenu.lat.toFixed(6)}, ${clickMenu.lon.toFixed(6)}`;
          return (
            <div
              // ★DESIGN.md 정합(2026-07-17): L3 팝오버=blur 24px(B4:239 — 종전 기본
              //   backdrop-blur 8px는 위반) · 라운드 12px(:290) · w-64 — 좌표 잘림 원천 해소.
              className="pointer-events-auto absolute w-64 -translate-x-1/2 overflow-hidden rounded-xl border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] shadow-xl backdrop-blur-xl"
              style={{ left: pos.left, top: pos.top, zIndex: SATONG_UI_Z.clickMenu }}
              role="menu"
              aria-label="지도 지점 메뉴"
            >
              <div className="border-b border-[var(--border-muted)] px-3 py-2">
                {/* label-caps 시그니처(B2 — 패널 최상단) — 팝업 성격을 한눈에.
                    ★라벨은 피처 '존재'로 판정(R1 m2) — address 유무로 가르면 피처는 매치됐는데
                    주소 보강만 늦은 경우 "지도 지점" 라벨 아래 용도지역·공시가가 떠 모순된다. */}
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--on-surface-muted)]">
                  {clickMenuFeature ? "필지" : "지도 지점"}
                </p>
                {clickMenuFeature?.address && (
                  <p className="mt-0.5 truncate text-[13px] font-semibold text-[var(--text-primary)]">
                    {shortJibunLabel(clickMenuFeature.address)}
                  </p>
                )}
                {subInfo.length > 0 && (
                  <p className="mt-0.5 truncate text-[11px] text-[var(--text-secondary)]">
                    {subInfo.join(" · ")}
                  </p>
                )}
                {/* 좌표행 — 수치는 data-mono(B2). 복사 라벨은 고정("복사")·좌표는 이 행이 정본
                    → 종전 "좌표 복사 (37.30...)" 버튼 내 좌표 중복이 w-56에서 잘리던 결함 해소. */}
                <div className="mt-1 flex items-center gap-1.5">
                  <span className="truncate font-mono text-[11px] text-[var(--text-secondary)]" title={coordText}>
                    {coordText}
                  </span>
                  <button
                    type="button"
                    aria-label={`좌표 복사 (${coordText})`}
                    className="shrink-0 rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-secondary)] transition hover:text-[var(--text-primary)]"
                    onClick={() => {
                      // ★R1: clipboard 미지원이면 옵셔널 체이닝이 조용히 단락되므로 성공 표기를
                      //   해선 안 되고, writeText Promise 거부(권한/포커스)도 삼키면 거짓 성공이
                      //   된다 — 실제 resolve 후에만 '복사됨' 표기(정직).
                      const writing = navigator.clipboard?.writeText?.(coordText);
                      if (!writing) return;
                      writing.then(() => setCopiedCoord(coordText)).catch(() => { /* 거부 — 무표기 */ });
                    }}
                  >
                    {copiedCoord === coordText ? "복사됨 ✓" : "복사"}
                  </button>
                </div>
              </div>
              <button
                type="button"
                role="menuitem"
                className="block w-full px-3 py-2 text-left text-[13px] font-medium text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)]"
                onClick={() => {
                  isMapClickSelectionRef.current = true;
                  void queryParcel(clickMenu.lat, clickMenu.lon);
                  setClickMenu(null);
                }}
              >
                <span className="inline-flex items-center gap-1.5"><MapPin className="size-3.5 text-[var(--text-secondary)]" aria-hidden />이 필지 선택·정보</span>
              </button>
              <button
                type="button"
                role="menuitem"
                className="block w-full px-3 py-2 text-left text-[13px] font-medium text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)]"
                onClick={() => {
                  setMeasureMode("distance");
                  setMeasurePoints([{ lat: clickMenu.lat, lon: clickMenu.lon }]);
                  setMeasureOn(true);
                  setClickMenu(null);
                }}
              >
                <span className="inline-flex items-center gap-1.5"><Ruler className="size-3.5 text-[var(--text-secondary)]" aria-hidden />거리재기 시작</span>
              </button>
              <button
                type="button"
                role="menuitem"
                className="block w-full px-3 py-2 text-left text-[13px] font-medium text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)]"
                onClick={() => {
                  setMeasureMode("area");
                  setMeasurePoints([{ lat: clickMenu.lat, lon: clickMenu.lon }]);
                  setMeasureOn(true);
                  setClickMenu(null);
                }}
              >
                <span className="inline-flex items-center gap-1.5"><LandPlot className="size-3.5 text-[var(--text-secondary)]" aria-hidden />면적재기 시작</span>
              </button>
              <button
                type="button"
                role="menuitem"
                className="block w-full px-3 py-2 text-left text-xs font-semibold text-[var(--text-hint)] transition hover:bg-[var(--surface-muted)]"
                onClick={() => setClickMenu(null)}
              >
                닫기 <span className="font-mono text-[10px]">(ESC)</span>
              </button>
              {/* 출처 푸터 — 디자인컴프 '팝업 출처 푸터' 계약 */}
              <p className="border-t border-[var(--border-muted)] px-3 py-1.5 font-mono text-[9px] text-[var(--text-hint)]">
                출처 VWorld · 국토교통부 공간정보
              </p>
            </div>
          );
        })()}

        {/* 거리재기 상태 칩 — 측정 중 안내/누적거리, 종료 후 결과 유지+지우기 */}
        {(measureOn || measurePoints.length > 0) && (
          <div
            className="pointer-events-auto absolute left-1/2 top-14 flex -translate-x-1/2 items-center gap-2 rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] px-3 py-1.5 shadow-lg backdrop-blur"
            style={{ zIndex: SATONG_UI_Z.clickMenu }}
          >
            {/* #359 아이콘 규약(lucide) + 측정 모드(I6) 병합 */}
            <span className="inline-flex items-center gap-1 text-[11px] font-black text-[var(--text-primary)]">
              {measureMode === "area" ? (
                <LandPlot className="size-3.5 shrink-0" aria-hidden />
              ) : (
                <Ruler className="size-3.5 shrink-0" aria-hidden />
              )}
              {measureOn
                ? `${measureMode === "area" ? "면적재기" : "거리재기"} — 클릭: 점 추가 · 더블클릭/ESC: 종료`
                : "측정 결과"}
              {measureMode === "area"
                ? measurePoints.length >= 3
                  ? ` · ${formatAreaSqm(polygonAreaSqm(measurePoints))} · 둘레 ${formatDistance(
                      totalDistanceMeters([...measurePoints, measurePoints[0]]),
                    )}`
                  : " · 점 3개 이상 필요" // R1: 면적 라벨 아래 거리값 표기 혼동 방지
                : measurePoints.length >= 2
                  ? ` · ${formatDistance(totalDistanceMeters(measurePoints))}`
                  : ""}
            </span>
            {measureOn ? (
              <button
                type="button"
                onClick={() => setMeasureOn(false)}
                className="rounded-full bg-[var(--accent-strong)]/10 px-2 py-0.5 text-[11px] font-black text-[var(--accent-strong)]"
              >
                종료
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setMeasurePoints([])}
                className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[11px] font-black text-[var(--text-secondary)]"
              >
                지우기
              </button>
            )}
          </div>
        )}

        {/* ── 좌하단 코너 도크 — 노후도 범례 + 상태 칩을 세로로 자동 스택(좌표 충돌·겹침 제거 · S5).
             종전엔 칩(bottom-3)과 범례(bottom-16)가 별개 absolute라 풀스크린(둘 다 bottom-16)에서
             정면 충돌했다. 한 도크에 담아 flex-col 로 흘려 물리적 겹침을 구조적으로 없앤다. ── */}
        {(bottomDockSlot != null || hasSatongLayer(layerState, "age") || tileStatus === "error" || boundaryStatus === "loading" || boundaryStatus === "error" || overlayNote || marketNote || presaleAuctionNote || poiNote || developmentNote || cadastreTileNote || zoningWideNote || regulationNote || (overlayFeatures.length > 0 && mapZoom < 15 && !zoomHintDismissed)) && (
          <div
            // left-14: 줌 컨트롤이 좌하단으로 이동(디자인컴프)해 도크를 오른쪽으로 비켜 세운다.
            // ★겹침 해소(2026-07-17): 세로 스택이 지도·팝업을 여러 줄 가리던 것을 가로 1줄
            //   (wrap 최소화)로 재배치 — 하단 배경정보 가림 면적을 구조적으로 축소.
            // ★겹침 근본해소(2026-07-17 라이브 신고): 하단 완료바는 비풀스크린에서도 래퍼
            //   '내부' flow 요소(지도 아래)라 bottom-3(래퍼 바닥) 앵커는 완료바 밴드와 정면
            //   충돌했다 — 두 모드 모두 bottom-16으로 완료바 위에 분리.
            // ★도크 단일화(2026-07-17 구조 진단): 종전 max-w-[calc(100%-152px)]는 우측
            //   스위처 섬(bottom-20 right-4)을 위한 암묵 예약이었는데 스위처 실폭(≈192px — 3×w-14+간격+패딩)이
            //   152px를 초과해 칩이 스위처 밑으로 파고들었다 — 스위처를 bottomDockSlot으로
            //   같은 flex 행에 흘려(right-3까지 전폭) 예약값 자체를 제거. flow 안에서는
            //   겹침이 문법적으로 불가능하다.
            data-testid="satong-bottom-dock"
            className={"pointer-events-none absolute bottom-16 left-14 right-3 flex flex-row flex-wrap items-end gap-1.5 transition-all duration-300"}
            style={{ zIndex: SATONG_UI_Z.cornerDock }}
          >
            {/* I4 저줌 안내(jootek 패턴) — 라벨 줌 롤업 구간에서 정보가 '숨은 게 아니라 접힘'임을
                알리고 원클릭 확대 제공. 닫으면 세션 내 재표시 안 함. */}
            {overlayFeatures.length > 0 && mapZoom < 15 && !zoomHintDismissed && (
              <span className="pointer-events-auto inline-flex w-fit items-center gap-1.5 rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] px-3 py-1.5 text-[11px] font-black text-[var(--text-primary)] shadow backdrop-blur">
                확대하면 필지·마커 상세 라벨이 표시됩니다
                <button
                  type="button"
                  onClick={() => { try { mapRef.current?.setZoom(16); } catch { /* noop */ } }}
                  className="rounded-full bg-[var(--accent-strong)]/10 px-2 py-0.5 text-[var(--accent-strong)]"
                >
                  확대
                </button>
                <button type="button" onClick={() => setZoomHintDismissed(true)} aria-label="확대 안내 닫기" className="text-[var(--text-hint)]">
                  <X className="size-3" aria-hidden />
                </button>
              </span>
            )}
            {/* WS-D 개발여력 범례 — capacity 레이어 on + 산정 가능 필지가 있을 때만 노출
                (무자료는 overlayNote "개발여력 무자료(실효·현황 용적률 필요)"가 정직 고지 —
                램프만 띄우면 '색=여력' 오인 조장·노후도 범례와 동일 원칙). */}
            {hasSatongLayer(layerState, "capacity") && hasSatongLayerControl(layerState, "capacity", "far-headroom") &&
              overlayFeatures.some((f) => capacityColor(f.effectiveFarPct, f.currentFarPct) != null) && (
              <div className="pointer-events-auto w-fit rounded-xl border border-slate-200 bg-white/95 p-2 shadow-lg backdrop-blur">
                <p className="mb-1 text-[10px] font-extrabold text-slate-700">개발여력 = (실효−현황)/실효 용적률</p>
                <div className="flex flex-col gap-0.5">
                  {CAPACITY_LEGEND_ITEMS.map((item) => (
                    <span key={item.label} className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-slate-600">
                      <span className="inline-block size-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
                      {item.label}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 노후도 범례 (age 레이어 on일 때) — ★WP-M3: 노후도 자료(avgAge)가 있을 때만 5색
                램프를 노출한다. 자료 0건이면 5색 램프가 '색=노후도' 오인을 조장하므로, "건물 정보
                없음"과 무자료 사유(나대지/조회실패/대량생략)만 정직 표기한다. */}
            {/* ★U1(범례 과점): 기본은 1줄 칩으로 접고, 클릭 시에만 5색 램프 카드를 펼친다.
                무자료(avgAge=null)면 카드 대신 정직 칩 1줄만 — 하단 도크 과점을 구조적으로 제거. */}
            {hasSatongLayer(layerState, "age") && (
              avgAge === null ? (
                <span className="pointer-events-auto inline-flex w-fit items-center gap-1 rounded-full bg-white/92 px-3 py-1.5 text-[11px] font-bold text-slate-500 shadow">
                  <Building2 className="size-3" aria-hidden />
                  노후도 — 건물 정보 없음
                  {buildAgeGapDetail(ageStatusCounts) ? ` · ${buildAgeGapDetail(ageStatusCounts)}` : ""}
                </span>
              ) : legendOpen ? (
                <div className="pointer-events-auto w-fit min-w-[155px] max-w-[240px] rounded-xl border border-slate-200 bg-white/95 p-2.5 shadow-lg backdrop-blur">
                  <button
                    type="button"
                    onClick={() => setLegendOpen(false)}
                    className="mb-1.5 flex w-full items-center justify-between gap-2 text-[11px] font-extrabold text-slate-800"
                    aria-expanded
                  >
                    <span className="inline-flex items-center gap-1"><Building2 className="size-3" aria-hidden />건물 노후도 구분</span>
                    <span aria-hidden>▾</span>
                  </button>
                  <div className="flex flex-col gap-1 text-[10.5px] border-b border-slate-100 pb-2 mb-2">
                    {AGE_LEGEND_ITEMS.map((item) => (
                      <div key={item.label} className="flex items-center gap-1.5 font-semibold text-slate-700">
                        <span className="h-3 w-3 rounded-sm border border-black/10 shadow-xs" style={{ backgroundColor: item.color }} />
                        <span>{item.label}</span>
                      </div>
                    ))}
                  </div>
                  <div className="text-[10px] font-bold text-slate-500 flex flex-col gap-0.5">
                    <span>선택 필지 평균 노후도</span>
                    <span className="text-xs font-black text-rose-600">{avgAge}년</span>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setLegendOpen(true)}
                  aria-expanded={false}
                  className="pointer-events-auto inline-flex w-fit items-center gap-1 rounded-full bg-white/95 px-3 py-1.5 text-[11px] font-black text-slate-700 shadow"
                >
                  <Building2 className="size-3" aria-hidden />노후도 범례 · 평균 <span className="text-rose-600">{avgAge}년</span>
                  <span aria-hidden>▸</span>
                </button>
              )
            )}
            {/* 상태 칩 — 가로 1줄(겹침 해소) */}
            {(tileStatus === "error" || boundaryStatus === "loading" || boundaryStatus === "error" || overlayNote || marketNote || presaleAuctionNote || poiNote || developmentNote || cadastreTileNote || zoningWideNote || regulationNote) && (
              <div className="flex flex-row flex-wrap items-end gap-1.5">
                {cadastreTileNote && (
                  // I9: 배지 = 자가진단 버튼 — 클릭 시 프록시 프로브로 실제 오류 code 표면화.
                  <button
                    type="button"
                    onClick={() => void diagnoseCadastreTiles()}
                    title={`${cadastreTileNote} — 클릭: 재진단`}
                    className="pointer-events-auto inline-flex w-fit max-w-[380px] rounded-full bg-amber-50/95 px-3 py-1.5 text-left text-[11px] font-black text-amber-800 shadow transition hover:bg-amber-100"
                  >
                    <span className="inline-flex items-center gap-1">
                      {cadastreTileNote} <Search className="size-3 shrink-0" aria-hidden />
                    </span>
                  </button>
                )}
                {zoningWideNote && (
                  <span className="inline-flex rounded-full bg-amber-50/95 px-3 py-1.5 text-[11px] font-black text-amber-800 shadow">
                    {zoningWideNote}
                  </span>
                )}
                {regulationNote && (
                  <span className="inline-flex rounded-full bg-amber-50/95 px-3 py-1.5 text-[11px] font-black text-amber-800 shadow">
                    {regulationNote}
                  </span>
                )}
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
                {presaleAuctionNote && (
                  <span className="inline-flex rounded-full bg-white/92 px-3 py-1.5 text-[11px] font-black text-slate-700 shadow">
                    {presaleAuctionNote}
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
              </div>
            )}
            {/* 우측 슬롯(베이스맵 스위처 등 부모 소유) — ml-auto로 같은 행 우측 정렬, 공간이
                부족하면 flex-wrap이 자기 행으로 내린다(칩과의 겹침이 문법적으로 불가능). */}
            {bottomDockSlot != null && (
              <div className="pointer-events-auto ml-auto shrink-0 self-end">{bottomDockSlot}</div>
            )}
          </div>
        )}

        {/* [MAP-007] 기반 타일 실패 — 중앙 반투명 오버레이 + 재시도(로딩/실패 구분 명시).
            pointer-events는 카드에만 허용해 지도 조작·기존 오버레이 확인은 계속 가능하다. */}
        {tileFailureNotice && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg bg-slate-900/40" style={{ zIndex: SATONG_UI_Z.tileFailure }}>
            <div className="pointer-events-auto flex max-w-[calc(100%-48px)] flex-col items-center gap-2 rounded-xl border border-rose-300/70 bg-white/95 px-4 py-3 text-center shadow-lg">
              <span className="text-[12px] font-bold leading-snug text-rose-700">
                {tileFailureNotice.message}
              </span>
              <button
                type="button"
                onClick={() => setTileRetryNonce((n) => n + 1)}
                className="rounded-lg bg-rose-600 px-3 py-1.5 text-[11px] font-bold text-white transition-colors hover:bg-rose-700"
              >
                {tileFailureNotice.retryLabel}
              </button>
            </div>
          </div>
        )}

        {/* 초기 안내 오버레이(아직 클릭 전) */}
        {!readOnly && !tileFailureNotice && status === "idle" && staged.length === 0 && overlayFeatures.length === 0 && !marketPayload && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg">
            <span className="rounded-lg bg-[var(--surface)]/80 px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] shadow">
              지도를 클릭해 필지 선택
            </span>
          </div>
        )}

        {/* ── 확인 카드 오버레이 — 조회 완료 후 사용자가 추가/취소를 결정하는 카드 ── */}
        {!readOnly && status === "found" && pending && (
          <div className="absolute bottom-16 left-1/2 -translate-x-1/2 w-[calc(100%-32px)] max-w-sm" style={{ zIndex: SATONG_UI_Z.confirmCard }}>
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
              {pendingAlreadyRegistered && !pendingAlreadyStaged ? (
                // ★WP-M2: 프로젝트에 이미 등록된 필지 → "이미 등록됨" 배지·닫기만(재등록 불가).
                //   staged에 담지 않으므로 "1필지 추가" 오카운트가 생기지 않는다.
                <div className="flex items-center gap-2">
                  <span className="flex-1 text-[11px] font-bold text-emerald-500">이미 등록됨(선택 필지)</span>
                  <button
                    type="button"
                    onClick={handleCancelPending}
                    className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:bg-[var(--surface)] transition-colors"
                  >
                    닫기
                  </button>
                </div>
              ) : pendingAlreadyStaged ? (
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
      {/* ── 하단 바 — 선택 필지 수·합산 면적·완료/전체취소.
          ★P1(감사): 풀스크린 래퍼 '내부'로 이동 — 종전엔 래퍼 밖이라 풀스크린(z-9990) 중
          완료/전체취소가 가려져 필지 등록이 불가했다. 풀스크린일 땐 하단 오버레이로 표시. ── */}
      {!readOnly && (
      <div
        className={isMapFullscreen
          ? "absolute inset-x-3 bottom-3 flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-secondary)]/95 px-3 py-2 shadow-xl backdrop-blur"
          : "mt-2 flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/60 px-3 py-2"}
        style={isMapFullscreen ? { zIndex: SATONG_UI_Z.bottomBar } : undefined}
      >
        {/* 선택 현황 — ★WP-M2 이중표기: 신규(이번에 담은 것)와 총(프로젝트 포함) 분리 표기.
            프로젝트 연결 직후엔 신규 0·총 12로 보여 "지적 12 vs 완료 1" 혼란을 없앤다. */}
        <div className="flex-1 text-[11px]">
          {totalCount > 0 ? (
            <span className="font-bold text-[var(--text-primary)]">
              신규 <span className="text-[var(--accent-strong)]">{newCount}</span> · 총 <span className="text-[var(--accent-strong)]">{totalCount}필지</span>
              {totalAreaSqm > 0 && (
                <span className="ml-1.5 font-normal text-[var(--text-secondary)]">
                  · 신규 {Math.round(totalAreaSqm).toLocaleString()}㎡ ({toP(totalAreaSqm)}평)
                </span>
              )}
            </span>
          ) : (
            <span className="text-[var(--text-hint)]">아직 선택된 필지 없음</span>
          )}
        </div>

        {/* 전체취소 버튼 — 신규 staged가 있을 때만 활성 */}
        {newCount > 0 && (
          <button
            type="button"
            onClick={handleClearAll}
            className="rounded-lg border border-[var(--line-strong)] px-2.5 py-1.5 text-[10px] font-bold text-[var(--text-secondary)] hover:border-red-400/50 hover:text-red-500 hover:bg-red-500/10 transition-colors"
          >
            전체취소
          </button>
        )}

        {/* 완료 버튼 — 신규가 있을 때만 활성. 라벨에 신규·총을 함께 표기(이중 카운트 봉합). */}
        <button
          type="button"
          disabled={newCount === 0}
          onClick={handleComplete}
          className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 transition-opacity"
        >
          {totalCount > 0 ? `완료(신규 ${newCount} · 총 ${totalCount}필지)` : "지도에서 필지 선택"}
        </button>
      </div>
      )}
      </div>
    </div>
  );
}

export default SatongMultiMap;
