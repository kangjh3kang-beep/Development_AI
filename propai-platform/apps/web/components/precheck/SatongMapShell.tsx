"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bot,
  Building2,
  CheckCircle2,
  ChevronRight,
  Download,
  FileSpreadsheet,
  Gavel,
  Home,
  Landmark,
  Layers,
  Image as ImageIcon,
  LineChart,
  Loader2,
  MapIcon,
  MapPin,
  Mountain,
  Route,
  Search,
  Sparkles,
  Trash2,
  TrainFront,
  X,
  TrendingUp,
} from "lucide-react";
import {
  type ChangeEvent,
  type ComponentType,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiClientError, apiClient, apiV1BaseUrl, hasAccessToken } from "@/lib/api-client";
import { UseLlmToggle } from "@/components/common/UseLlmToggle";
import { DataSourceNotice } from "@/components/ui/DataSourceNotice";
import type {
  ParcelAtPointResult,
  SatongAuctionItem,
  SatongDevelopmentPayload,
  SatongMarketPayload,
  SatongMultiMapProps,
  SatongPoiPayload,
  SatongPresaleItem,
} from "@/components/map/SatongMultiMap";
import {
  isRenderableSatongMapLayer,
  resolveSelectionAnchor,
  type SatongMapFeature,
  type SatongMapLayerId,
  type SatongMapLayerState,
  capacityRatio,
  resolveVWorldBaseLayer,
} from "@/lib/satong-map-layers";
import { buildSelectionGeoJson, buildSelectionKml, kakaoRoadviewUrl } from "@/lib/satong-export";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { useProjectStore } from "@/store/useProjectStore";
import { restoreSnapshot } from "@/lib/projectSync";
import { createProjectFromParcels } from "@/lib/satong-project-create";
import {
  readSatongMapSelection,
  selectionToSiteAnalysisPatch,
  siteAnalysisToSelection,
  writeSatongMapSelection,
  type SatongSelectionParcel,
} from "./satong-map-selection";
import {
  deriveProjectNameFromParcels,
  selectionMismatchesProject,
} from "./satong-project-connect";

const SatongMultiMap = dynamic<SatongMultiMapProps>(
  () =>
    import("@/components/map/SatongMultiMap").then(
      (mod) => mod.SatongMultiMap as ComponentType<SatongMultiMapProps>,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="grid h-[720px] place-items-center rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] text-sm font-bold text-[var(--text-secondary)]">
        <span className="inline-flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          통합지도를 불러오는 중
        </span>
      </div>
    ),
  },
);

type SearchCandidate = {
  address?: string | null;
  road_address?: string | null;
  jibun?: string | null;
  pnu?: string | null;
  kind?: string | null;
  lat?: number | null;
  lon?: number | null;
};

type SearchResponse = {
  candidates?: SearchCandidate[];
};

type GeocodeResponse = {
  found?: boolean;
  address?: string | null;
  road_address?: string | null;
  jibun_address?: string | null;
  pnu?: string | null;
  bcode?: string | null;
  lat?: number | null;
  lon?: number | null;
  reason?: string | null;
};

type ParsedParcel = {
  address?: string | null;
  jibun?: string | null;
  pnu?: string | null;
  area_sqm?: number | null;
  zone_type?: string | null;
  jimok?: string | null;
  official_price_per_sqm?: number | null;
  // ★검증 리포트(additive) — 행별 최종분류. 구버전 응답(필드 부재)과 호환되도록 옵셔널.
  verification_status?: "verified" | "corrected" | "needs_review" | null;
  verification_reasons?: string[] | null;
  injectable?: boolean | null;
};

type VerificationCorrection = {
  field?: string | null;
  before?: string | number | null;
  after?: string | number | null;
  reason?: string | null;
};

type VerificationReport = {
  counts?: { verified?: number; corrected?: number; needs_review?: number; excluded?: number } | null;
  corrections?: VerificationCorrection[] | null;
  warnings?: string[] | null;
  llm_used?: boolean | null;
  passes?: number | null;
};

type ParseParcelsResponse = {
  parcels?: ParsedParcel[];
  note?: string | null;
  error?: string | null;
  verification_report?: VerificationReport | null;
};

type SatongParcel = SatongSelectionParcel;

type LayerStatus = "active" | "ready" | "needs-source";

type SatongLayer = {
  id: SatongMapLayerId;
  label: string;
  shortLabel: string;
  description: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  status: LayerStatus;
  tone: string;
  source: string;
  controls: SatongLayerControl[];
};

type SatongLayerControl = {
  id: string;
  label: string;
  mapEffect: boolean;
  description?: string;
};

type OutputAction = {
  id: string;
  label: string;
  description: string;
  href: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  tone: string;
};

/**
 * 통합지도 레이어 정의 레지스트리.
 * 정직 라벨 원칙: 지도에 실데이터가 렌더링되는(mapEffect) 레이어의 source 는
 * '연동 필요'가 아니라 실제 연동된 원천을 기술해야 한다.
 * (테스트 검증용으로 export — components/precheck/__tests__/SatongMapShell.layers.test.ts)
 */
const LAYERS: SatongLayer[] = [
  {
    id: "cadastre",
    label: "지적도",
    shortLabel: "지적",
    description: "필지 경계, 지목, 면적, PNU를 선택 기준으로 사용합니다.",
    // ★WP-M4: 레일 앵커(지도 레이어 관리)의 MapIcon과 중복 인지되던 것을 Layers로 교체(아이콘-기능 1:1).
    icon: Layers,
    status: "active",
    tone: "bg-lime-100 text-lime-950 border-lime-200",
    source: "필지 클릭 API + 지적 경계",
    controls: [
      { id: "boundary", label: "필지 경계", mapEffect: true },
      { id: "selected", label: "선택 필지", mapEffect: true },
      { id: "neighbors", label: "주변 필지", mapEffect: false, description: "주변 필지 벡터 API 연결 후 활성화" },
    ],
  },
  {
    id: "zoning",
    label: "용도지역",
    shortLabel: "용도",
    description: "선택 필지의 용도지역을 색상으로 구분해 지도에 반영합니다.",
    icon: Landmark,
    status: "active",
    tone: "bg-sky-100 text-sky-950 border-sky-200",
    source: "공간정보(토지특성정보) API 연동",
    controls: [
      { id: "land-use", label: "용도지역", mapEffect: true },
      { id: "land-use-wide", label: "전국 지적편집도", mapEffect: true, description: "화면 전체를 용도지역 색상으로 표시(VWorld)" },
      // ★규제 오버레이(2026-07-17 잠금 해제): 아래 2개는 "원천 연결 후 활성화" 플레이스홀더로
      //   설계돼 있었고, VWorld WMS 원천(GetCapabilities+GetMap 매트릭스 채증)이 확보되어
      //   설계 의도대로 활성화한다. 매핑은 satong-map-layers.REGULATION_WMS_BY_CONTROL 단일 SSOT.
      { id: "district-unit", label: "지구단위", mapEffect: true, description: "지구단위계획 구역을 지도에 표시(VWorld)" },
      { id: "development-limit", label: "개발행위 제한", mapEffect: true, description: "개발행위허가 제한구역을 지도에 표시(VWorld)" },
      { id: "water-protect", label: "상수원보호", mapEffect: true, description: "상수원보호구역 — 개발행위 제한 요인(VWorld)" },
      { id: "edu-protect", label: "교육환경보호", mapEffect: true, description: "교육환경보호구역 — 숙박·위락 업종 인허가 직결(VWorld)" },
      { id: "height-district", label: "고도지구", mapEffect: true, description: "고도지구 — 건축물 높이 제한(VWorld)" },
    ],
  },
  {
    id: "official-price",
    label: "공시지가",
    shortLabel: "공시",
    description: "선택 필지의 개별공시지가(㎡당 단가)를 지도에 색상으로 반영합니다.",
    icon: LineChart,
    status: "active",
    tone: "bg-emerald-100 text-emerald-950 border-emerald-200",
    source: "공간정보(VWorld NED) 토지특성 API 연동",
    controls: [
      { id: "unit-price", label: "㎡당 단가", mapEffect: true },
      { id: "year", label: "연도", mapEffect: false, description: "연도별 공시지가 이력 연결 후 활성화" },
      { id: "change-rate", label: "변동률", mapEffect: false, description: "연도별 공시지가 이력 연결 후 활성화" },
    ],
  },
  {
    // WS-D① 개발여력 히트맵(선택필지 MVP) — (실효FAR−현황FAR)/실효FAR 코로플레스.
    // 실효=calc_effective_far 7계층 min(서버)·현황=건축물대장 전동 연면적합/대지면적(서버).
    // 미상 필지는 무색+무자료 고지(무날조). 뷰포트 전역 배치 산출은 후속(배치 엔드포인트).
    id: "capacity",
    label: "개발여력",
    shortLabel: "여력",
    description: "실효 용적률 대비 남은 개발 여력을 색상으로 표시합니다(지을 수 있는 만큼 못 지은 땅 발굴).",
    icon: TrendingUp,
    status: "active",
    tone: "bg-green-100 text-green-950 border-green-200",
    source: "실효한도(7계층)+건축물대장 연면적 서버 산정",
    controls: [
      { id: "far-headroom", label: "용적 여력", mapEffect: true },
    ],
  },
  {
    id: "age",
    label: "노후도",
    shortLabel: "노후",
    description: "건축물대장 기반 준공연도(연식)를 색상으로 구분합니다. 나대지·미준공은 표시하지 않습니다.",
    icon: Building2,
    status: "active",
    tone: "bg-rose-100 text-rose-950 border-rose-200",
    source: "건축물대장 표제부(건축HUB, 사용승인일)",
    controls: [
      { id: "building-age", label: "건축연도", mapEffect: true },
      { id: "structure", label: "구조", mapEffect: false, description: "건축물대장 구조 필드 연결 후 활성화" },
      { id: "floors", label: "층수", mapEffect: false, description: "건축물대장 층수 필드 연결 후 활성화" },
      { id: "purpose", label: "주용도", mapEffect: false, description: "건축물대장 주용도 필드 연결 후 활성화" },
    ],
  },
  {
    id: "transactions",
    label: "실거래·시세",
    shortLabel: "시세",
    description: "선택 필지 주변(1km·최근 3개월) 실거래를 마커로 지도에 반영합니다. 필지를 먼저 선택하세요.",
    icon: Home,
    status: "active",
    tone: "bg-blue-100 text-blue-950 border-blue-200",
    source: "국토교통부 실거래가(주변 1km·최근 3개월)",
    controls: [
      { id: "deal-year", label: "거래연도", mapEffect: false, description: "거래연도 필터 — 향후 제공" },
      { id: "deal-type", label: "거래유형", mapEffect: false, description: "거래유형 필터 — 향후 제공" },
      { id: "total-price", label: "총액", mapEffect: false, description: "총액 필터 — 향후 제공" },
      { id: "unit-price", label: "평당가 라벨", mapEffect: true, description: "실거래 라벨을 총액 대신 평당가로 표시" },
    ],
  },
  {
    id: "presale",
    label: "분양정보",
    shortLabel: "분양",
    description: "선택 필지(또는 지도 중심) 주변 3km의 분양단지를 마커로 표시합니다.",
    icon: Sparkles,
    status: "active",
    tone: "bg-violet-100 text-violet-950 border-violet-200",
    source: "청약홈 분양정보(주변 3km)",
    controls: [
      { id: "supply-type", label: "공급유형", mapEffect: false, description: "공급유형 필터 — 향후 제공" },
      { id: "presale-price", label: "분양가", mapEffect: false, description: "분양가 필터 — 향후 제공" },
      { id: "move-in", label: "입주시기", mapEffect: false, description: "입주시기 필터 — 향후 제공" },
    ],
  },
  {
    id: "auction",
    label: "공·경매",
    shortLabel: "경매",
    description: "선택 필지 주변(10km)의 온비드 공매 물건을 마커로 표시합니다. 로그인이 필요할 수 있습니다.",
    icon: Gavel,
    status: "active",
    tone: "bg-amber-100 text-amber-950 border-amber-200",
    source: "온비드 공매(주변 10km·감정가/최저가)",
    controls: [
      { id: "appraisal", label: "감정가", mapEffect: false, description: "감정가 필터 — 향후 제공" },
      { id: "minimum-bid", label: "최저가", mapEffect: false, description: "최저가 필터 — 향후 제공" },
      { id: "bid-date", label: "입찰일", mapEffect: false, description: "입찰일 필터 — 향후 제공" },
      { id: "bid-rate", label: "낙찰률", mapEffect: false, description: "낙찰률 필터 — 향후 제공" },
    ],
  },
  {
    id: "poi",
    label: "교통·편의 POI",
    shortLabel: "POI",
    description: "선택 필지 주변(800m)의 역·학교·상권·공원·병원을 마커로 표시합니다. 필지를 먼저 선택하세요.",
    icon: TrainFront,
    status: "active",
    tone: "bg-cyan-100 text-cyan-950 border-cyan-200",
    source: "Kakao Local 반경검색(카카오 로컬)",
    controls: [
      { id: "station", label: "역", mapEffect: true },
      { id: "school", label: "학교", mapEffect: true },
      { id: "commerce", label: "상권", mapEffect: true },
      { id: "park", label: "공원", mapEffect: true },
      { id: "hospital", label: "병원", mapEffect: true },
    ],
  },
  {
    id: "development",
    label: "개발계획",
    shortLabel: "개발",
    description: "선택 필지 주변(1km)의 도시계획시설(철도·역사 등 계획·결정)을 마커로 표시합니다. 필지를 먼저 선택하세요.",
    icon: Route,
    status: "active",
    tone: "bg-violet-100 text-violet-950 border-violet-200",
    source: "VWorld 도시계획시설(UPIS 계열)",
    controls: [
      { id: "facilities", label: "도시계획시설", mapEffect: true },
    ],
  },
  {
    id: "terrain",
    label: "지형도·항공뷰",
    shortLabel: "지형",
    description: "경사, 고저차, 항공사진을 사업 리스크와 설계 제약에 반영합니다.",
    icon: Mountain,
    status: "ready",
    tone: "bg-stone-100 text-stone-950 border-stone-200",
    source: "VWorld WMTS 프록시 연동(기본·위성·항공뷰)",
    controls: [
      { id: "base", label: "기본지도", mapEffect: true },
      { id: "satellite", label: "위성", mapEffect: true },
      { id: "hybrid", label: "항공뷰", mapEffect: true },
      { id: "elevation", label: "표고", mapEffect: false, description: "표고/경사도 격자 원천 연결 후 활성화" },
      { id: "gray", label: "회색지도", mapEffect: true, description: "저채도 배경 — 데이터 대비 강조" },
    ],
  },
  {
    id: "roadview",
    label: "로드뷰",
    shortLabel: "로드",
    description: "접도, 가로환경, 출입구 후보를 현장감 있게 확인합니다.",
    icon: Route,
    status: "needs-source",
    tone: "bg-slate-100 text-slate-950 border-slate-200",
    source: "카카오 로드뷰 SDK 연동 필요",
    controls: [
      { id: "roadview", label: "로드뷰", mapEffect: false },
      { id: "frontage", label: "접도", mapEffect: false },
      { id: "vehicle-access", label: "차량 진입", mapEffect: false },
      { id: "pedestrian-access", label: "보행 접근", mapEffect: false },
    ],
  },
];

export { LAYERS as SATONG_MAP_SHELL_LAYERS };

// 항공뷰 썸네일 베이스맵 스위처(jootek 패리티) — terrain 컨트롤 재사용.
// ★스와치=실물 타일 미리보기(2026-07-17 직관력 보강): 스와치의 본질은 "이 버튼을 누르면
//   실제로 보이는 지도"의 미리보기라, 같은 프록시(/tiles/vworld/wmts)의 실제 타일을 쓴다
//   — 실서비스(카카오·네이버·jootek) 관행. 생성/장식 이미지는 실렌더와 어긋나는 약속이라
//   무목업 원칙에 반한다. 자기 오리진 프록시 경유 = CSP 안전(외부 host 아님 — 종전
//   "외부 이미지 금지" 의도 유지). 그라디언트 클래스는 타일 로드 실패 시 폴백으로 잔존.
//   대표 타일 z12/1583/3492 = 서울 도심(한강·시가지·산 대비로 4스타일 차이가 명확 —
//   2026-07-17 라이브 4종 200 실측). Hybrid는 실렌더와 동일하게 위성 위 라벨 합성.
const SWATCH_TILE_BASE = "/tiles/vworld/wmts";
const SWATCH_TILE_ZYX = "12/1583/3492";
const BASEMAP_SWITCHES = [
  { id: "base", label: "일반", base: "Base", swatch: "bg-gradient-to-br from-slate-100 via-emerald-50 to-emerald-100",
    tiles: [`${SWATCH_TILE_BASE}/Base/${SWATCH_TILE_ZYX}.png`] },
  { id: "satellite", label: "위성", base: "Satellite", swatch: "bg-gradient-to-br from-slate-800 via-emerald-950 to-slate-900",
    tiles: [`${SWATCH_TILE_BASE}/Satellite/${SWATCH_TILE_ZYX}.jpeg`] },
  { id: "hybrid", label: "하이브리드", base: "Hybrid", swatch: "bg-gradient-to-br from-slate-700 via-sky-950 to-slate-800",
    // CSS 다중 배경은 먼저 쓴 것이 위 — 라벨(Hybrid)을 위성 위에 얹는 실렌더 합성과 동일.
    tiles: [`${SWATCH_TILE_BASE}/Hybrid/${SWATCH_TILE_ZYX}.png`, `${SWATCH_TILE_BASE}/Satellite/${SWATCH_TILE_ZYX}.jpeg`] },
  // ★id("gray")=UI 컨트롤 식별자(:1353 상호배타 해제셋 키·LAYERS 정의와 일치) /
  //   base("white")=VWorld tiletype 정본 — 별개 네임스페이스라 분리 유지한다.
  //   종전 base:"gray"는 상류 미존재값이라 회색 선택 시 배경지도가 통째로 사라졌다.
  { id: "gray", label: "회색", base: "white", swatch: "bg-gradient-to-br from-slate-200 to-slate-400",
    tiles: [`${SWATCH_TILE_BASE}/white/${SWATCH_TILE_ZYX}.png`] },
] as const;

const sourceLabel: Record<SatongParcel["source"], string> = {
  search: "검색",
  excel: "엑셀",
  map: "지도",
};

function getCandidateLabel(candidate: SearchCandidate): string {
  return (
    candidate.address ||
    candidate.road_address ||
    candidate.jibun ||
    candidate.pnu ||
    "주소 미확인"
  );
}

function normalizeKey(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function parcelKey(parcel: Pick<SatongParcel, "address" | "pnu">): string {
  return parcel.pnu || normalizeKey(parcel.address);
}

/**
 * ★리뷰(HIGH) 근치 — pnu/주소 키 이중성 승격.
 *
 * 시드 필지(엑셀·지오코딩)는 pnu 미확보 상태로 selectedParcels 에 들어온다(pnu=null, 키=주소).
 * 이후 지도 boundary 보강(/zoning/parcel-boundaries)이 real 19자리 pnu 를 채워 돌려주는데,
 * 종전 handleBoundaryEnriched 병합은 기존 p.pnu 를 그대로 유지해 이 real pnu 를 버렸다 —
 * autoStage(parcelMembershipKey, real pnu 기준)는 이후 계속 이 필지를 "미등록"으로 오판했고,
 * mergeSatongMapFeatures("지적 N건" 등 칩 집계)도 같은 물리 필지를 pnu-키/주소-키 2건으로 쪼갰다.
 *
 * 이 함수는 existingPnu 가 있으면 그대로 보존(real→real 덮어쓰기 금지 — 무날조), 없을 때만
 * boundaryPnu 로 승격한다. handleBoundaryEnriched 한 곳에서 이 값을 채택하면 이후 파생되는
 * selectedMapFeatures·mergeSatongMapFeatures·parcelMembershipKey 가 모두 같은 real pnu 로
 * 수렴해 칩·CTA·merge 카운트가 한 번에 정합해진다(공용화 치유).
 */
export function healParcelPnu(
  existingPnu: string | null | undefined,
  boundaryPnu: string | null | undefined,
): string | null {
  return existingPnu || boundaryPnu || null;
}

function formatArea(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "-";
  // ㎡·평 병행 표기(1평 = 3.305785㎡).
  const pyeong = (value / 3.305785).toFixed(1);
  return `${Math.round(value).toLocaleString()}㎡ (${pyeong}평)`;
}

function statusText(status: LayerStatus): string {
  if (status === "active") return "활성";
  if (status === "ready") return "준비";
  return "연동 필요";
}

function statusClass(status: LayerStatus): string {
  if (status === "active") return "bg-[var(--status-success)]/15 text-[var(--status-success)]";
  if (status === "ready") return "bg-[var(--accent-strong)]/15 text-[var(--accent-strong)]";
  return "bg-[var(--status-warning)]/15 text-[var(--status-warning)]";
}

function defaultControlsByLayer(): SatongMapLayerState["controlsByLayer"] {
  return {
    cadastre: ["boundary", "selected"],
    zoning: ["land-use"],
    "official-price": ["unit-price"],
    age: ["building-age"],
    poi: ["station", "school", "commerce", "park", "hospital"],
    development: ["facilities"],
    terrain: ["base"],
  };
}

function parseGeocodeToParcel(
  query: string,
  response: GeocodeResponse,
  source: SatongParcel["source"],
): SatongParcel {
  const address =
    response.address ||
    response.road_address ||
    response.jibun_address ||
    query;
  return {
    id: response.pnu || normalizeKey(address),
    address,
    pnu: response.pnu ?? null,
    lat: response.lat ?? null,
    lon: response.lon ?? null,
    source,
  };
}

function parsedParcelToSelection(parcel: ParsedParcel): SatongParcel {
  const address = parcel.address || parcel.jibun || parcel.pnu || "엑셀 등록 필지";
  return {
    id: parcel.pnu || normalizeKey(address),
    address,
    pnu: parcel.pnu ?? null,
    areaSqm: parcel.area_sqm ?? null,
    zoneType: parcel.zone_type ?? null,
    jimok: parcel.jimok ?? null,
    officialPricePerSqm: parcel.official_price_per_sqm ?? null,
    source: "excel",
  };
}

function mapParcelToSelection(parcel: ParcelAtPointResult): SatongParcel {
  const address = parcel.address || parcel.jibun || parcel.pnu || "지도 선택 필지";
  return {
    id: parcel.pnu || normalizeKey(address),
    address,
    pnu: parcel.pnu ?? null,
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

function saveSelectionForOutputs(parcels: SatongParcel[]): void {
  writeSatongMapSelection(parcels);
}

export function SatongMapShell({ locale }: { locale: string }) {
  const router = useRouter();
  const updateSiteAnalysis = useProjectContextStore((state) => state.updateSiteAnalysis);
  const projectId = useProjectContextStore((state) => state.projectId);
  const setProject = useProjectContextStore((state) => state.setProject);
  const clearProject = useProjectContextStore((state) => state.clearProject);
  const projects = useProjectStore((state) => state.projects);
  const syncFromBackend = useProjectStore((state) => state.syncFromBackend);

  useEffect(() => {
    if (!projects.length) void syncFromBackend();
  }, [projects.length, syncFromBackend]);

  // 읽기 셀렉터 — 활성 프로젝트 siteAnalysis 전체를 구독(SSOT). parcels[]뿐 아니라 레거시
  //   단일필지(top-level 주소·좌표만) 프로젝트도 비동기 스냅샷 복원 도착을 감지해야 하므로
  //   객체 단위로 읽는다. sessionStorage(자기세션 선택)가 우선, 이건 폴백/전환 시드용.
  const storeSiteAnalysis = useProjectContextStore((state) => state.siteAnalysis);
  // 연결 대상: "new"=새 프로젝트로 등록(기본) · "none"=연결 안 함(약식) · 그 외=기존 프로젝트 id.
  //   기본을 '새 프로젝트'로 두는 이유: 마지막 활성 프로젝트가 영속 기본값이면 다른 지역 필지
  //   선택이 그 프로젝트 siteAnalysis를 조용히 덮어쓴다(교차오염). 이어하기(컨텍스트에 진행 중
  //   프로젝트+데이터가 있는 경우)만 예외로 그 프로젝트를 유지한다.
  const [connectTarget, setConnectTarget] = useState<"new" | "none" | string>(() => "new");
  const [connectNotice, setConnectNotice] = useState("");
  const connectInitRef = useRef(false);
  useEffect(() => {
    if (connectInitRef.current) return;
    if (!projectId) {
      connectInitRef.current = true; // 연결된 프로젝트 없음 — 기본 'new' 확정
      return;
    }
    if (storeSiteAnalysis?.address || storeSiteAnalysis?.parcels?.length) {
      connectInitRef.current = true;
      setConnectTarget(projectId); // 이어하기 예외
      return;
    }
    // projectId는 있지만 데이터(주소·필지)가 아직 도착 전(스냅샷 복원 비동기 대기) — 여기서
    // 래치하지 않는다. 다음 storeSiteAnalysis 갱신 때 이 이펙트가 다시 실행돼 재평가한다
    // (늦은 복원 허용 — F5, 조기 래치로 '이어하기' 판정을 놓치지 않는다).
  }, [projectId, storeSiteAnalysis]);
  const [query, setQuery] = useState("");
  const [searchCandidates, setSearchCandidates] = useState<SearchCandidate[]>([]);
  const [searchStatus, setSearchStatus] = useState<"idle" | "loading" | "error">("idle");
  const [searchError, setSearchError] = useState("");
  const [selectedParcels, setSelectedParcels] = useState<SatongParcel[]>([]);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "loading" | "error">("idle");
  const [uploadNote, setUploadNote] = useState("");
  // ★검증 리포트(T5) — 업로드 직후 4분류 카운트·보정내역·확인필요 사유를 패널로 노출.
  const [verificationReport, setVerificationReport] = useState<VerificationReport | null>(null);
  const [uploadParcels, setUploadParcels] = useState<ParsedParcel[]>([]);
  // ★use_llm 옵트인(T1) — 기존 동작 보존을 위해 기본 true(비표준 양식 자동 LLM 보조 유지).
  const [useLlm, setUseLlm] = useState(true);
  const [focusTarget, setFocusTarget] = useState<{ lat: number; lon: number; label?: string } | null>(null);
  const [enabledLayers, setEnabledLayers] = useState<Set<SatongMapLayerId>>(() => new Set(["cadastre"]));
  const [layerControls, setLayerControls] = useState<SatongMapLayerState["controlsByLayer"]>(() => defaultControlsByLayer());
  const [activeLayerId, setActiveLayerId] = useState<SatongMapLayerId | null>(null);
  const [isOutputDockOpen, setIsOutputDockOpen] = useState(true);
  // ── WS-C 필지 상세 패널 — 지도 폴리곤/카드 클릭 → 통합 정보(개요·공시지가·노후도)와
  //    산출물 원클릭 퍼널. 단일 팝오버 원칙: 레이어 설정 패널과 동시 표출 금지(상호 배타).
  const [detailFeature, setDetailFeature] = useState<SatongMapFeature | null>(null);
  const openFeatureDetail = useCallback((feature: SatongMapFeature) => {
    // ★단일 팝오버 불변식 — right-20 top-20 z-430 좌표를 공유하는 3패널(필지상세·레이어·
    //   베이스맵)은 동시에 뜰 수 없다. 봉합은 '생산 근원'인 이 함수에서 한다 — 호출부
    //   (좌측 필지 카드·지도 피처 클릭)마다 닫기를 흩뿌리면 새 호출부가 생길 때 또 샌다.
    setBasemapOpen(false);
    setDetailFeature(feature);
    setActiveLayerId(null);
  }, []);
  // I5: 선택 필지 GeoJSON 내보내기 결과 고지(제외 건수 정직 표기).
  const [exportNote, setExportNote] = useState("");
  // ★R1(stale 고지): 선택이 바뀌면(추가·삭제·초기화·프로젝트 전환) 지난 내보내기 고지를
  //   비운다 — "3필지 내보냄"이 4필지 상태에 잔존하는 정직-고지 역위반 방지.
  useEffect(() => {
    setExportNote("");
  }, [selectedParcels]);
  // ★WP-M2: "초기화"(clearParcels)가 지도 내부 staged·녹색 폴리곤도 청소하도록 보내는 신호(nonce).
  //   증가할 때마다 SatongMultiMap이 handleClearAll을 실행한다(종전엔 목록만 비고 지도엔 잔존).
  const [clearNonce, setClearNonce] = useState(0);
  // ★WP-M4: 레일(레이어 아이콘 세로바) 클릭 고정 토글 — hover 없이 터치로도 전개 가능하게.
  const [railPinned, setRailPinned] = useState(false);
  // 베이스맵 팝오버 열림 — 레이어 팝오버(activeLayerId)와 상호배타(같은 좌표를 쓰므로).
  const [basemapOpen, setBasemapOpen] = useState(false);
  // 새 프로젝트 생성 인플라이트 표시(버튼 disabled용) — 실제 중복차단은 creatingProjectRef(F4).
  const [creatingProject, setCreatingProject] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const basemapPopoverRef = useRef<HTMLDivElement | null>(null);
  const creatingProjectRef = useRef(false);

  // ── PR#221 프로젝트 전환/하이드레이션 상태 refs(컴포넌트 상단으로 이동 — F1: 아래 콜백들이
  //   detachProjectCarryingSelection 등에서 참조할 수 있도록 다른 ref 선언 옆에 둔다. 로직은
  //   기존과 동일 — 하이드레이션 이펙트 본문은 원래 위치에 그대로 있다) ──
  const hydratedRef = useRef(false);
  // 직전 projectId(undefined=첫 실행 센티널)와, 전환 후 스토어 시드 허용 여부.
  const prevProjectIdRef = useRef<string | null | undefined>(undefined);
  const projectSeedArmedRef = useRef(false);
  // 마지막으로 시드한 내용의 지문 — siteAnalysis 객체 참조만 바뀌고 내용이 같은 갱신
  //   (updatedAt 등 무관 필드 변경)에 재시드·지도 이동이 반복되지 않게 한다. ""=전환 직후.
  const lastSeedKeyRef = useRef("");
  // 전환 후 지도 이동(포커스)을 아직 못 했는지 — 좌표가 보강으로 늦게 와도 딱 1회만 이동.
  const projectFocusPendingRef = useRef(false);

  // 의도적 프로젝트 해제(선택 유지): 전환 이펙트가 P→null을 '프로젝트 전환'으로 오인해
  //   방금 담은 선택·sessionStorage를 지우지 않도록, 이펙트가 볼 직전값을 미리 null로 맞춘다.
  //   (자동시드도 함께 disarm — 해제 후 스토어 갱신이 선택을 덮지 않게.)
  const detachProjectCarryingSelection = useCallback(() => {
    prevProjectIdRef.current = null;
    hydratedRef.current = true;
    projectSeedArmedRef.current = false;
    clearProject();
  }, [clearProject]);

  const selectedTotalArea = useMemo(
    () => selectedParcels.reduce((sum, parcel) => sum + (parcel.areaSqm ?? 0), 0),
    [selectedParcels],
  );

  const activeLayer = useMemo(
    () => LAYERS.find((layer) => layer.id === activeLayerId) ?? null,
    [activeLayerId],
  );

  const activeLayers = useMemo(
    () => LAYERS.filter((layer) => enabledLayers.has(layer.id)),
    [enabledLayers],
  );


  const handleSelectProject = useCallback((id: string) => {
    if (!id) return;
    const p = projects.find((x) => x.id === id);
    if (!p) return;
    setProject(p.id, p.name, p.status, p.address || undefined);
    void restoreSnapshot(p.id);
  }, [projects, setProject]);

  const handleConnectTargetChange = useCallback((value: string) => {
    setConnectNotice("");
    if (value === "new" || value === "none") {
      setConnectTarget(value);
      // 활성 프로젝트가 있으면 해제(스냅샷 보존, 선택 유지) — 이후 선택·커밋이 그 프로젝트를
      //   덮지 않게. clearProject 직접 호출 대신 detachProjectCarryingSelection을 써서 전환
      //   이펙트가 이 해제를 '프로젝트 전환'으로 오인해 방금 담긴 선택을 지우지 않게 한다(F1).
      if (projectId) detachProjectCarryingSelection();
      return;
    }
    setConnectTarget(value);
    handleSelectProject(value); // 기존 경로(setProject+restoreSnapshot) 재사용 — PR#221 시드가 이어짐
  }, [projectId, detachProjectCarryingSelection, handleSelectProject]);

  const selectedMapFeatures = useMemo<SatongMapFeature[]>(
    () =>
      selectedParcels.map((parcel) => ({
        id: parcel.id,
        address: parcel.address,
        pnu: parcel.pnu,
        lat: parcel.lat,
        lon: parcel.lon,
        areaSqm: parcel.areaSqm,
        zoneType: parcel.zoneType,
        jimok: parcel.jimok,
        officialPricePerSqm: parcel.officialPricePerSqm,
        builtYear: parcel.builtYear,
        buildingAgeYears: parcel.buildingAgeYears,
        ageStatus: parcel.ageStatus,
        effectiveFarPct: parcel.effectiveFarPct,
        effectiveBcrPct: parcel.effectiveBcrPct,
        currentFarPct: parcel.currentFarPct,
        geometry: parcel.geometry,
        source: parcel.source,
      })),
    [selectedParcels],
  );

  const mapLayerState = useMemo<SatongMapLayerState>(
    () => ({
      enabledLayerIds: Array.from(enabledLayers),
      controlsByLayer: layerControls,
    }),
    [enabledLayers, layerControls],
  );

  // I5+V3: 선택 필지 → GeoJSON/KML 파일 다운로드(순수 직렬화는 satong-export — 테스트 고정).
  //   포맷별 중복을 공용 실행기로 일원화(버그수정 정책 — 공용화).
  const exportSelection = useCallback(
    (format: "geojson" | "kml") => {
      const built =
        format === "kml" ? buildSelectionKml(selectedMapFeatures) : buildSelectionGeoJson(selectedMapFeatures);
      if (built.included === 0) {
        setExportNote(
          "내보낼 경계(geometry) 보유 필지가 없습니다 — 지도에서 필지를 선택(경계 조회)한 뒤 다시 시도하세요.",
        );
        return;
      }
      const mime = format === "kml" ? "application/vnd.google-earth.kml+xml" : "application/geo+json";
      const blob = new Blob([built.json], { type: mime });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `satong-parcels-${built.included}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      // R1: click() 직후 동기 revoke는 일부 환경에서 다운로드를 끊을 수 있어 다음 틱으로 지연.
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setExportNote(
        `${format === "kml" ? "KML" : "GeoJSON"} ${built.included}필지 내보냄${built.skipped ? ` · 경계 없음 ${built.skipped}필지 제외(정직 고지)` : ""}`,
      );
    },
    [selectedMapFeatures],
  );

  // ── 실거래·시세 레이어 배선: 레이어 ON + 선택필지 있으면 주변 실거래(nearby-map) 조회 ──
  //   렌더(마커·반경·팝업)는 SatongMultiMap에 완비 — 여기서는 데이터만 주입한다.
  //   실패는 fetch_failed로 정직 전달(지도에 "조회 실패" 노트), 무선택·레이어 OFF는 null(마커 제거).
  const [marketPayload, setMarketPayload] = useState<SatongMarketPayload | null>(null);
  const marketEnabled = enabledLayers.has("transactions");
  //   ★의존성은 원시값(pnu·address)으로 — 선택목록 참조가 바뀌어도 anchor가 같으면 재조회 안 함
  //     (#178 교훈: 참조 churn이 이펙트 무한/중복 실행을 유발).
  //   anchor = 첫 선택 필지(생성자들이 address를 항상 채우므로 사실상 selectedParcels[0]).
  const marketAnchor = useMemo(
    () => selectedParcels.find((p) => p.pnu || p.address) ?? null,
    [selectedParcels],
  );
  const marketAnchorPnu = marketAnchor?.pnu || "";
  const marketAnchorAddress = marketAnchor?.address || "";
  // ★지도 현재중심(P1) — 선택필지 없을 때 지역레이어(POI·개발계획)의 폴백 앵커. 원시값(lat/lon)만
  //   의존성에 쓴다(#178). SatongMultiMap의 moveend가 반올림·디바운스해 통지하므로 재조회 폭주 없음.
  const [mapCenter, setMapCenter] = useState<{ lat: number; lon: number } | null>(null);
  useEffect(() => {
    if (!marketEnabled || (!marketAnchorPnu && !marketAnchorAddress)) {
      setMarketPayload(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongMarketPayload>("/zoning/nearby-map", {
          body: {
            address: marketAnchorAddress || undefined,
            pnu: marketAnchorPnu || undefined,
            radius_m: 1000,
            months: 3,
          },
          useMock: false,
          timeoutMs: 90000,
        });
        if (!cancelled) {
          // 백엔드 소프트 실패(HTTP 200 + {error, center:null})도 fetch_failed로 승격해
          // 지도에 "조회 불가" 노트를 정직 표기(침묵 빈지도 방지 — 리뷰 LOW 반영).
          const soft = res as SatongMarketPayload & { error?: string };
          if (soft.error || !soft.center?.lat) {
            setMarketPayload({
              center: null,
              fetch_failed: true,
              note: soft.error || "주변 실거래 조회 불가(지역코드 미확인)",
            });
          } else {
            setMarketPayload(res);
          }
        }
      } catch {
        if (!cancelled) {
          setMarketPayload({ center: null, fetch_failed: true, note: "주변 실거래 조회 실패" });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [marketEnabled, marketAnchorPnu, marketAnchorAddress]);

  // ── 교통·편의 POI 레이어 배선: 레이어 ON + 선택필지 있으면 주변 POI(/site-score/poi-infra) 조회 ──
  //   렌더(카테고리 색상 마커·팝업)는 SatongMultiMap에 구현 — 여기서는 데이터만 주입.
  //   실패/키미설정은 available:false로 정직 전달(지도 노트), OFF/무선택은 null(마커 제거).
  //   의존성은 원시값(lat·lon·address) — 참조 churn 재조회 방지(#178 교훈, 실거래와 동일 패턴).
  const [poiPayload, setPoiPayload] = useState<SatongPoiPayload | null>(null);
  const poiEnabled = enabledLayers.has("poi");
  // ★좌표 앵커 공용화(resolveSelectionAnchor — satong-map-layers): 종전 '첫 필지의 lat/lon'만
  //   보던 단선을 ①좌표 보유 첫 필지 ②경계(geometry) 대표점 ③(무선택시) 지도중심 순으로 해소.
  //   좌표 없는 선택(엑셀 PNU행·프로젝트 시드)도 경계보강 도착 즉시 앵커가 살아나 분양·경매·
  //   개발계획 조회가 자동 재개된다. 선택이 있는데 좌표·경계가 전무하면 null 유지(엉뚱한
  //   지도중심 조회 역전 차단 — 기존 계약 보존, 리뷰 LOW). 이펙트 의존성은 원시값만(#178).
  const selectionAnchor = useMemo(
    () => resolveSelectionAnchor(selectedParcels, mapCenter),
    [selectedParcels, mapCenter],
  );
  const anchorLat = selectionAnchor?.lat ?? null;
  const anchorLon = selectionAnchor?.lon ?? null;
  // 앵커 필지의 주소 — 좌표와 같은 필지 기준. 다필지에서 첫 필지(주소)와 앵커(좌표)가 서로
  //   다른 필지를 가리키던 조합 불일치 해소(리뷰 LOW): POI 보조주소·경매 region이 앵커 필지를 따른다.
  const anchorAddress = selectionAnchor?.address ?? "";
  // 선택은 있는데 좌표·경계가 아직 없음(경계보강 대기) — 좌표 레이어의 정직 노트용.
  const anchorPending = selectedParcels.length > 0 && selectionAnchor == null;
  // 경계보강 진행상태(SatongMultiMap→onBoundaryStatusChange) — 영구 실패면 "확인 중" 노트를
  //   "확인 실패"로 정직 강등한다(진행 중인 척 위장 금지, 리뷰 LOW).
  const [boundaryFailed, setBoundaryFailed] = useState(false);
  const handleBoundaryStatusChange = useCallback(
    (status: "idle" | "loading" | "ready" | "error") => setBoundaryFailed(status === "error"),
    [],
  );
  // 좌표 레이어(개발계획·분양·경매) 공용 대기 노트 — 상태 3분류를 한 곳에서 만든다.
  const anchorWaitNote = useCallback(
    (label: string) =>
      anchorPending
        ? boundaryFailed
          ? `${label}: 필지 좌표 확인 실패(경계 조회 불가)`
          : `${label}: 선택 필지 좌표 확인 중(경계 보강 후 자동 조회)`
        : `${label}: 지도를 이동하면 지도 중심 기준으로 조회합니다`,
    [anchorPending, boundaryFailed],
  );
  useEffect(() => {
    if (!poiEnabled || (anchorLat == null && !marketAnchorAddress)) {
      setPoiPayload(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongPoiPayload>("/site-score/poi-infra", {
          body: {
            lat: anchorLat ?? undefined,
            lon: anchorLon ?? undefined,
            // 좌표가 있으면 앵커 필지의 주소(좌표·주소 동일 출처), 좌표 전무 시에만 첫 필지 주소 폴백.
            address: (anchorLat != null ? anchorAddress : marketAnchorAddress) || undefined,
            radius_m: 800,
          },
          useMock: false,
          timeoutMs: 60000,
        });
        if (!cancelled) setPoiPayload(res);
      } catch {
        if (!cancelled) setPoiPayload({ available: false, reason: "POI 조회 실패" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [poiEnabled, anchorLat, anchorLon, anchorAddress, marketAnchorAddress]);

  // ── 개발계획 레이어 배선: 레이어 ON + 앵커 좌표 있으면 주변 도시계획시설 조회 ──
  //   /zoning/development-facilities 는 lat/lon 필수(주소 지오코딩 없음).
  //   ★앵커 미해소 시에도 침묵하지 않는다 — 빈 facilities + 대기/안내 note 정직 전달(무날조).
  const [developmentPayload, setDevelopmentPayload] = useState<SatongDevelopmentPayload | null>(null);
  const developmentEnabled = enabledLayers.has("development");
  useEffect(() => {
    if (!developmentEnabled) {
      setDevelopmentPayload(null);
      return;
    }
    if (anchorLat == null || anchorLon == null) {
      // 레이어는 켜졌는데 조회 기준 좌표가 아직 없음 — 종전엔 payload null(노트조차 없는
      // 침묵 빈지도, 정직원칙 역위반)이었다. 상태를 구분해 지도에 노트로 알린다.
      setDevelopmentPayload({ facilities: [], note: anchorWaitNote("개발계획") });
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongDevelopmentPayload>("/zoning/development-facilities", {
          // kinds:"all" — 지도 레이어는 전체 도시계획시설(도로·광장·학교·유통 등) 표시.
          //   (기본 "rail"은 입지 신호용 철도 전용 — 기존 소비처 동작 보존)
          body: { lat: anchorLat, lon: anchorLon, radius_m: 1000, kinds: "all" },
          useMock: false,
          timeoutMs: 60000,
        });
        if (!cancelled) setDevelopmentPayload(res);
      } catch {
        if (!cancelled) {
          setDevelopmentPayload({ facilities: [], note: "개발계획(도시계획시설) 조회 실패" });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [developmentEnabled, anchorLat, anchorLon, anchorWaitNote]);

  // ── 분양정보 레이어 배선(실데이터): 레이어 ON + 앵커좌표(또는 주소) → 청약홈(/presale/nearby) ──
  //   렌더(마커·팝업)는 SatongMultiMap의 presaleItems에 완비. 실패/무자료는 [](정직 "분양 무자료").
  //   ★무목업: 종전 가상단지(Math.random) 목업을 실데이터로 대체. 패턴은 실거래·POI와 동일.
  //   ★주소 폴백: 서버(presale.nearby)가 좌표 없이 address만 와도 지오코딩으로 해소하므로,
  //     좌표 미확보 선택(엑셀 PNU행 등)도 주소로 즉시 조회한다(앵커 단선 해소).
  const [presaleItems, setPresaleItems] = useState<SatongPresaleItem[] | null>(null);
  const [presaleNote, setPresaleNote] = useState("");
  const presaleEnabled = enabledLayers.has("presale");
  useEffect(() => {
    if (!presaleEnabled) {
      setPresaleItems(null);
      setPresaleNote("");
      return;
    }
    if (anchorLat == null && !marketAnchorAddress) {
      // 좌표도 주소도 없음 — 침묵 대신 상태를 노트로 알린다(정직원칙).
      setPresaleItems(null);
      setPresaleNote(anchorWaitNote("분양"));
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<{ available?: boolean; items?: SatongPresaleItem[] }>(
          "/presale/nearby",
          {
            body: {
              lat: anchorLat ?? undefined,
              lon: anchorLon ?? undefined,
              // 좌표가 없을 때만 주소 전달 — 서버 지오코딩 1회로 해소(좌표 있으면 좌표 우선).
              address: anchorLat == null ? marketAnchorAddress || undefined : undefined,
              radius_m: 3000,
            },
            useMock: false,
            timeoutMs: 30000,
          },
        );
        if (!cancelled) {
          setPresaleItems(
            (res.items ?? []).filter(
              (item) => typeof item.lat === "number" && typeof item.lon === "number",
            ),
          );
          setPresaleNote("");
        }
      } catch {
        if (!cancelled) {
          setPresaleItems([]); // 가짜 생성 금지
          setPresaleNote("분양: 조회 실패"); // 무자료와 실패를 구분(정직원칙)
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [presaleEnabled, anchorLat, anchorLon, anchorWaitNote, marketAnchorAddress]);

  // ── 공·경매 레이어 배선(실데이터): 온비드 검색(/auction/search) → 주소 지오코딩(/auction/geocode)
  //   → 앵커 반경(10km) 필터. 지역(시/도) 우선 검색, 0건이면 전국 폴백. 좌표 미확인 물건은
  //   스킵(가짜 좌표 금지).
  //   ★인증 정직화: /auction/search만 RBAC 게이트(RequirePermission) — 종전엔 비로그인 401이
  //     catch로 삼켜져 "경매 무자료"로 오표기됐고, 전역 세션만료 처리(로그인 리다이렉트)가
  //     발동해 지도에서 튕겨나갔다. ①토큰 없으면 호출 전 게이트(무의미한 401 왕복 차단)
  //     ②호출은 skipSessionExpiry로 리다이렉트 옵트아웃 ③401/403은 무자료가 아니라
  //     "로그인/권한 필요" 노트로 구분 표기.
  const [auctionItems, setAuctionItems] = useState<SatongAuctionItem[] | null>(null);
  const [auctionNote, setAuctionNote] = useState("");
  const auctionEnabled = enabledLayers.has("auction");
  useEffect(() => {
    if (!auctionEnabled) {
      setAuctionItems(null);
      setAuctionNote("");
      return;
    }
    if (anchorLat == null || anchorLon == null) {
      setAuctionItems(null);
      setAuctionNote(anchorWaitNote("경매"));
      return;
    }
    // 토큰 존재는 반응형 신호가 아니다(localStorage 직독) — 이 화면엔 인라인 로그인이 없어
    // 로그인은 항상 /login 라우트 이동→복귀 리마운트로 해소되므로 stale 위험은 이론적(리뷰 MEDIUM 수용).
    // 인라인 로그인 UI가 생기면 인증 스토어 구독으로 교체할 것.
    if (!hasAccessToken()) {
      setAuctionItems(null);
      setAuctionNote("경매: 로그인 후 조회 가능합니다");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        type AuctionSearchItem = {
          id?: number | string;
          address?: string | null;
          status?: string | null;
          appraisal_price?: number | null;
          min_bid_price?: number | null;
          bid_end?: string | null;
        };
        // 앵커 필지 주소의 시/도 토큰을 **원형 그대로** 전달(예: "충청북도") — 저장 축약형("충북")
        // 정규화는 서버 공용 _sido_from_address가 담당(진실원천 1곳, 프론트 재구현 금지 — QA MEDIUM).
        // ★좌표(하버사인 필터)와 같은 앵커 필지의 주소를 쓴다 — 다필지에서 region과 거리필터가
        //   서로 다른 필지 기준이 되던 조합 불일치 해소(리뷰 LOW). 앵커 주소 부재 시 첫 필지 폴백.
        const region = (anchorAddress || marketAnchorAddress).split(" ")[0] || "";
        const fetchPage = (r?: string) =>
          apiClient.get<{ items?: AuctionSearchItem[] }>(
            `/auction/search?page_size=60${r ? `&region=${encodeURIComponent(r)}` : ""}`,
            // skipSessionExpiry: 선택형 지도 레이어가 만료 세션에서 전역 로그인 리다이렉트를
            // 발동하지 않게 옵트아웃 — 401/403은 아래 catch가 정직 노트로 처리한다.
            { useMock: false, timeoutMs: 30000, skipSessionExpiry: true },
          );
        let res = region ? await fetchPage(region) : await fetchPage();
        if (region && !(res.items ?? []).length) res = await fetchPage(); // 지역 0건 → 전국 폴백
        const items = (res.items ?? []).filter((item) => (item.address ?? "").trim());
        if (!items.length) {
          if (!cancelled) setAuctionItems([]);
          return;
        }
        const geo = await apiClient.post<{ located?: { key: string; lat: number; lon: number }[] }>(
          "/auction/geocode",
          {
            body: {
              items: items.slice(0, 60).map((item, index) => ({
                key: String(item.id ?? index),
                address: item.address,
              })),
            },
            useMock: false,
            timeoutMs: 60000,
          },
        );
        const located = new Map((geo.located ?? []).map((l) => [l.key, l]));
        const toRad = (d: number) => (d * Math.PI) / 180;
        const near = items
          .map((item, index): SatongAuctionItem | null => {
            const loc = located.get(String(item.id ?? index));
            if (!loc) return null;
            // 하버사인 거리(m) — 앵커 반경 10km만 채택.
            const dLat = toRad(loc.lat - anchorLat);
            const dLon = toRad(loc.lon - anchorLon);
            const h =
              Math.sin(dLat / 2) ** 2 +
              Math.cos(toRad(anchorLat)) * Math.cos(toRad(loc.lat)) * Math.sin(dLon / 2) ** 2;
            const distanceM = Math.round(2 * 6371000 * Math.asin(Math.sqrt(h)));
            if (distanceM > 10000) return null;
            return {
              address: item.address ?? undefined,
              status: item.status ?? undefined,
              appraisal_price: item.appraisal_price ?? undefined,
              minimum_bid_price: item.min_bid_price ?? undefined,
              bid_date: item.bid_end ?? undefined,
              lat: loc.lat,
              lon: loc.lon,
              distance_m: distanceM,
            };
          })
          .filter((item): item is SatongAuctionItem => item != null)
          .sort((a, b) => (a.distance_m ?? 0) - (b.distance_m ?? 0))
          .slice(0, 30);
        if (!cancelled) {
          setAuctionItems(near);
          setAuctionNote("");
        }
      } catch (err) {
        if (cancelled) return;
        // 인증/권한 실패는 '무자료'가 아니다 — 상태를 구분해 정직 표기.
        if (err instanceof ApiClientError && (err.status === 401 || err.status === 403)) {
          setAuctionItems(null);
          setAuctionNote(
            err.status === 403
              ? "경매: 조회 권한이 없는 계정입니다"
              : "경매: 로그인 후 조회 가능합니다",
          );
        } else {
          setAuctionItems([]); // 가짜 생성 금지
          setAuctionNote("경매: 조회 실패"); // 무자료와 실패를 구분(정직원칙)
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auctionEnabled, anchorLat, anchorLon, anchorAddress, anchorWaitNote, marketAnchorAddress]);

  const outputActions: OutputAction[] = useMemo(
    () => [
      {
        id: "analysis",
        label: "종합 부지분석",
        description: "다필지·규제·입지",
        href: `/${locale}/analysis`,
        icon: MapPin,
        // 산출물 dock: primary 1개(부지분석) + 글래스 3개 — DESIGN.md B5 Output Actions.
        tone: "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)]",
      },
      {
        id: "permits",
        label: "인허가 체크리스트",
        description: "허가 가능성·보완 항목",
        href: `/${locale}/permits`,
        icon: CheckCircle2,
        tone: "border-[var(--border-muted)] bg-[var(--surface-strong)] text-[var(--text-primary)]",
      },
      {
        id: "market",
        label: "시장·분양 리포트",
        description: "시세·수요·공급",
        href: `/${locale}/market-insights`,
        icon: LineChart,
        tone: "border-[var(--border-muted)] bg-[var(--surface-strong)] text-[var(--text-primary)]",
      },
      {
        id: "design",
        label: "건축개요·CAD 계획도면",
        description: "법규 맞춤 계획안",
        href: `/${locale}/design-studio`,
        icon: Building2,
        tone: "border-[var(--border-muted)] bg-[var(--surface-strong)] text-[var(--text-primary)]",
      },
    ],
    [locale],
  );

  const commitParcelsToContext = useCallback(
    (parcels: SatongParcel[]) => {
      const patch = selectionToSiteAnalysisPatch(parcels);
      if (!patch) return;
      updateSiteAnalysis(patch, { source: "user" });
    },
    [updateSiteAnalysis],
  );

  // 선택목록 → SSOT(store)·sessionStorage 동기화 공용통로. commitParcelsToContext는 빈 배열에
  //   no-op이므로, 빈 목록이면 store 필지를 명시 정리한다 — 안 지우면 ①재마운트 시 스토어 폴백
  //   하이드레이션이 삭제한 필지를 부활시키고 ②/analysis가 옛 주소를 계속 분석한다(P1 감사).
  //   삭제·전체취소 등 모든 경로가 이 통로를 쓰게 해 경로 간 비대칭 재발을 막는다.
  const syncParcelsToStores = useCallback(
    (parcels: SatongParcel[]) => {
      if (parcels.length > 0) {
        commitParcelsToContext(parcels);
      } else {
        updateSiteAnalysis({ parcels: [], parcelCount: 0 }, { source: "user" });
      }
      saveSelectionForOutputs(parcels);
    },
    [commitParcelsToContext, updateSiteAnalysis],
  );

  const addParcels = useCallback(
    (incoming: SatongParcel[]) => {
      if (incoming.length === 0) return;
      // ★교차오염 가드: 기존 프로젝트 연결 상태에서 그 프로젝트 주소와 지역이 다른 필지가
      //   들어오면, 프로젝트를 덮지 않도록 '새 프로젝트로 등록' 모드로 자동 전환한다.
      //   clearProject 직접 호출 대신 detachProjectCarryingSelection을 쓴다 — 전환 이펙트가
      //   이 해제를 '프로젝트 전환'으로 오인해 방금 추가한 필지·sessionStorage를 지우는 것을
      //   막는다(F1: prevProjectIdRef를 미리 null로 맞춰 이펙트가 전환으로 보지 않게 한다).
      if (projectId && connectTarget === projectId) {
        const projAddr = projects.find((p) => p.id === projectId)?.address || storeSiteAnalysis?.address;
        if (selectionMismatchesProject(projAddr, incoming[0]?.address)) {
          detachProjectCarryingSelection();
          setConnectTarget("new");
          setConnectNotice("선택 필지가 연결 프로젝트 주소와 달라 '새 프로젝트로 등록'으로 전환했습니다.");
        }
      }
      projectSeedArmedRef.current = false; // 사용자 직접 편집 — 자동시드 중지(선택 소유권 이전)
      setSelectedParcels((prev) => {
        const byKey = new Map(prev.map((parcel) => [parcelKey(parcel), parcel]));
        incoming.forEach((parcel) => {
          const key = parcelKey(parcel);
          const current = byKey.get(key);
          byKey.set(key, {
            ...current,
            ...parcel,
            areaSqm: parcel.areaSqm ?? current?.areaSqm ?? null,
            zoneType: parcel.zoneType ?? current?.zoneType ?? null,
            jimok: parcel.jimok ?? current?.jimok ?? null,
          });
        });
        const next = Array.from(byKey.values());
        syncParcelsToStores(next);
        return next;
      });
    },
    [syncParcelsToStores, projectId, connectTarget, projects, storeSiteAnalysis, detachProjectCarryingSelection],
  );

  const removeParcel = useCallback(
    (id: string) => {
      projectSeedArmedRef.current = false; // 사용자 직접 편집 — 자동시드 중지(선택 소유권 이전)
      setSelectedParcels((prev) => {
        const removed = prev.find((parcel) => parcel.id === id);
        const next = prev.filter((parcel) => parcel.id !== id);
        syncParcelsToStores(next); // 빈 배열이면 store·sessionStorage 모두 정리(부활 방지)
        // ★R1 HIGH(유령 패널): 삭제한 필지가 상세 패널에 떠 있으면 함께 닫는다 —
        //   화면엔 삭제된 필지, 퍼널은 남은 선택으로 실행되는 오도 조합 차단.
        if (removed) {
          setDetailFeature((current) =>
            current &&
            ((removed.pnu && current.pnu === removed.pnu) || current.address === removed.address)
              ? null
              : current,
          );
        }
        return next;
      });
    },
    [syncParcelsToStores],
  );

  const clearParcels = useCallback(() => {
    projectSeedArmedRef.current = false; // 사용자 직접 편집 — 자동시드 중지(선택 소유권 이전)
    setSelectedParcels([]);
    setFocusTarget(null);
    setDetailFeature(null); // ★R1 HIGH: 전체초기화 시 상세 패널 잔존 방지
    syncParcelsToStores([]);
    setClearNonce((n) => n + 1); // ★WP-M2: 지도 staged·녹색 폴리곤도 함께 청소(잔존 방지)
  }, [syncParcelsToStores]);

  const runDirectGeocode = useCallback(
    async (rawQuery: string) => {
      const trimmed = rawQuery.trim();
      if (!trimmed) return;
      setSearchStatus("loading");
      setSearchError("");
      try {
        const geocoded = await apiClient.post<GeocodeResponse>("/zoning/geocode", {
          body: { query: trimmed },
          useMock: false,
          timeoutMs: 20000,
        });
        if (!geocoded.found) {
          setSearchStatus("error");
          setSearchError(geocoded.reason || "검색 결과를 찾지 못했습니다.");
          return;
        }
        const parcel = parseGeocodeToParcel(trimmed, geocoded, "search");
        addParcels([parcel]);
        if (parcel.lat != null && parcel.lon != null) {
          setFocusTarget({ lat: parcel.lat, lon: parcel.lon, label: parcel.address });
        }
        setSearchCandidates([]);
        setSearchStatus("idle");
      } catch {
        setSearchStatus("error");
        setSearchError("주소 검색 중 오류가 발생했습니다.");
      }
    },
    [addParcels],
  );

  const handleCandidatePick = useCallback(
    async (candidate: SearchCandidate) => {
      const label = getCandidateLabel(candidate);
      setQuery(label);
      setSearchCandidates([]);
      if (candidate.pnu || (candidate.lat != null && candidate.lon != null)) {
        const parcel: SatongParcel = {
          id: candidate.pnu || normalizeKey(label),
          address: label,
          pnu: candidate.pnu ?? null,
          lat: candidate.lat ?? null,
          lon: candidate.lon ?? null,
          source: "search",
        };
        addParcels([parcel]);
        if (parcel.lat != null && parcel.lon != null) {
          setFocusTarget({ lat: parcel.lat, lon: parcel.lon, label: parcel.address });
        }
        return;
      }
      await runDirectGeocode(label);
    },
    [addParcels, runDirectGeocode],
  );

  const handleSearchSubmit = useCallback(() => {
    if (searchCandidates[0]) {
      void handleCandidatePick(searchCandidates[0]);
      return;
    }
    void runDirectGeocode(query);
  }, [handleCandidatePick, query, runDirectGeocode, searchCandidates]);

  const handleExcelUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      setUploadStatus("loading");
      setUploadNote("");
      setVerificationReport(null);
      setUploadParcels([]);
      const form = new FormData();
      form.append("file", file);
      form.append("use_llm", String(useLlm));
      try {
        const data = await apiClient.post<ParseParcelsResponse>("/zoning/parse-parcels", {
          body: form,
          useMock: false,
          // ★H4-③: LLM 보조 구조인식·반복검증(S1/S3)까지 걸리면 60s로는 대량 엑셀에서 타임아웃이
          //   잦았다 — GlobalAddressSearch(120s)보다 여유 있게 180s로 상향.
          timeoutMs: 180000,
        });
        if (data.error) {
          setUploadStatus("error");
          setUploadNote(data.error);
          return;
        }
        const allParcels = data.parcels ?? [];
        // ★H3: injectable=False는 백엔드에서 표에서 완전히 제외된 행(합계/집계)에만 쓴다 —
        //   verified/corrected/needs_review는 모두 주입해 주입 후 2차 enrich(/zoning/parcels-info)
        //   의 재지오코딩·재검증으로 자기치유되게 한다(injectable 필드 부재 시 구버전 응답
        //   호환을 위해 기본 포함 — 무회귀). 필터 로직은 그대로 두되(향후 방어), 실제로는
        //   백엔드 계약상 아래 filter가 걸러내는 행은 사실상 없다.
        const injectable = allParcels.filter((p) => p.injectable !== false);
        const parcels = injectable.map(parsedParcelToSelection);
        addParcels(parcels);
        setUploadStatus("idle");
        setUploadParcels(allParcels);
        setVerificationReport(data.verification_report ?? null);
        const skipped = allParcels.length - injectable.length;
        setUploadNote(
          (data.note ||
            (parcels.length > 0
              ? `${parcels.length}개 필지를 지도 선택 목록에 반영했습니다.`
              : "엑셀에서 등록 가능한 필지를 찾지 못했습니다.")) +
            (skipped > 0 ? ` (확인필요 ${skipped}건은 아래 리포트에서 확인)` : ""),
        );
      } catch {
        setUploadStatus("error");
        setUploadNote("엑셀 파일 처리 중 오류가 발생했습니다.");
      } finally {
        event.target.value = "";
      }
    },
    [addParcels, useLlm],
  );

  const handleTemplateDownload = useCallback(() => {
    if (typeof window === "undefined") return;
    window.location.href = `${apiV1BaseUrl()}/zoning/land-schedule-template`;
  }, []);

  const handleLayerClick = useCallback((layerId: SatongMapLayerId) => {
    setDetailFeature(null); // 단일 팝오버 — 레이어 패널을 열면 필지 상세는 닫는다
    setBasemapOpen(false);  // 〃 베이스맵도(레일 버튼·좌상단 칩 행 두 호출부가 함께 따라온다)
    if (!isRenderableSatongMapLayer(layerId)) {
      setActiveLayerId((current) => (current === layerId ? null : layerId));
      return;
    }
    setEnabledLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layerId)) {
        if (layerId !== "cadastre") next.delete(layerId);
      } else {
        next.add(layerId);
      }
      return next;
    });
    setActiveLayerId((current) => (current === layerId ? null : layerId));
  }, []);

  const handleLayerControlClick = useCallback((layerId: SatongMapLayerId, control: SatongLayerControl) => {
    if (!control.mapEffect) return;
    setEnabledLayers((prev) => {
      const next = new Set(prev);
      next.add(layerId);
      return next;
    });
    setLayerControls((prev) => {
      const current = new Set(prev[layerId] ?? []);
      if (layerId === "terrain") {
        ["base", "satellite", "hybrid", "aerial", "gray"].forEach((id) => current.delete(id));
        current.add(control.id);
      } else if (current.has(control.id)) {
        current.delete(control.id);
      } else {
        current.add(control.id);
      }
      return {
        ...prev,
        [layerId]: Array.from(current),
      };
    });
  }, []);

  const handleMapPickMany = useCallback(
    (parcels: ParcelAtPointResult[]) => {
      addParcels(parcels.map(mapParcelToSelection));
    },
    [addParcels],
  );

  // ★P1(감사): 지도 경계 API가 보강한 필지 속성(면적·용도·좌표·경계)을 선택목록+SSOT에 병합.
  //   종전엔 지도 내부 dead-end → 검색 등록 필지가 면적 0으로 통합분석에서 침묵 탈락했다.
  //   빈 필드만 채우고(사용자·원천값 우선), 변화가 없으면 setState를 건너뛰어 재조회 루프를 끊는다.
  const handleBoundaryEnriched = useCallback(
    (features: Array<{ pnu?: string | null; address?: string; areaSqm?: number | null;
      zoneType?: string | null; jimok?: string | null; lat?: number | null; lon?: number | null;
      officialPricePerSqm?: number | null; builtYear?: number | null;
      buildingAgeYears?: number | null; ageStatus?: string | null;
      effectiveFarPct?: number | null; effectiveBcrPct?: number | null;
      currentFarPct?: number | null; geometry?: unknown }>,
    ) => {
      setSelectedParcels((prev) => {
        if (!prev.length || !features.length) return prev;
        let changed = false;
        const byKey = new Map<string, (typeof features)[number]>();
        for (const f of features) {
          if (f.pnu) byKey.set(String(f.pnu), f);
          if (f.address) byKey.set(f.address.trim(), f);
        }
        const next = prev.map((p) => {
          const f = (p.pnu && byKey.get(String(p.pnu))) || byKey.get(p.address.trim());
          if (!f) return p;
          const merged = {
            ...p,
            // ★리뷰(HIGH) 근치: 시드 필지(pnu 미확보)의 합성/주소 키를 boundary가 돌려준 real
            //   pnu로 승격한다(기존 real pnu는 보존 — healParcelPnu 참조). 이 한 줄이 칩·CTA·
            //   merge 카운트 이중성의 근원(pnu/주소 키 불일치)을 한 곳에서 치유한다.
            pnu: healParcelPnu(p.pnu, f.pnu),
            areaSqm: p.areaSqm ?? f.areaSqm ?? null,
            zoneType: p.zoneType ?? f.zoneType ?? null,
            jimok: p.jimok ?? f.jimok ?? null,
            lat: p.lat ?? f.lat ?? null,
            lon: p.lon ?? f.lon ?? null,
            officialPricePerSqm: p.officialPricePerSqm ?? f.officialPricePerSqm ?? null,
            builtYear: p.builtYear ?? f.builtYear ?? null,
            buildingAgeYears: p.buildingAgeYears ?? f.buildingAgeYears ?? null,
            // ★WP-M3: 노후도 조회 사유(age_status)를 역전파해 "조회 시도됨"을 SSOT에 남긴다 —
            //   나대지(연식 null)여도 ageStatus가 채워져 경계 재조회 루프가 끊긴다.
            ageStatus: p.ageStatus ?? f.ageStatus ?? null,
            // I7/WS-D — 서버 산정치 역전파(선택 SSOT까지 — orphan handoff 방지).
            effectiveFarPct: p.effectiveFarPct ?? f.effectiveFarPct ?? null,
            effectiveBcrPct: p.effectiveBcrPct ?? f.effectiveBcrPct ?? null,
            currentFarPct: p.currentFarPct ?? f.currentFarPct ?? null,
            geometry: p.geometry ?? f.geometry ?? null,
          };
          if (
            merged.pnu !== p.pnu ||
            merged.areaSqm !== p.areaSqm || merged.zoneType !== p.zoneType ||
            merged.jimok !== p.jimok || merged.lat !== p.lat || merged.lon !== p.lon ||
            merged.officialPricePerSqm !== p.officialPricePerSqm ||
            merged.builtYear !== p.builtYear || merged.buildingAgeYears !== p.buildingAgeYears ||
            merged.ageStatus !== p.ageStatus ||
            merged.effectiveFarPct !== p.effectiveFarPct ||
            merged.effectiveBcrPct !== p.effectiveBcrPct ||
            merged.currentFarPct !== p.currentFarPct ||
            merged.geometry !== p.geometry
          ) {
            changed = true;
            return merged;
          }
          return p;
        });
        if (!changed) return prev; // 무변화 — 참조 유지로 하류 이펙트 재실행 차단
        commitParcelsToContext(next); // SSOT 동기화 → /analysis가 보강 면적을 읽는다
        saveSelectionForOutputs(next);
        return next;
      });
    },
    [commitParcelsToContext],
  );

  // 선택 필지로 새 프로젝트 생성·연결(공용) — 셀렉터 아래 버튼과 산출물 실행(연결모드 "new")이 공유.
  // ★인플라이트 가드(F4): 버튼 연타·산출물 클릭 중복이 프로젝트를 여러 개 만들지 않게 한다.
  //   ref=동기 즉시차단, state=버튼 disabled 표시용(둘 다 시작/종료 시 함께 토글).
  const connectAsNewProject = useCallback(async (): Promise<string | null> => {
    if (selectedParcels.length === 0) return null;
    if (creatingProjectRef.current) return null;
    creatingProjectRef.current = true;
    setCreatingProject(true);
    try {
      const created = await createProjectFromParcels(selectedParcels);
      if (!created) {
        setConnectNotice("필지 주소가 없어 프로젝트를 생성할 수 없습니다.");
        return null;
      }
      // setProject 직후 같은 틱에 선택 패치를 커밋 — 전환 이펙트가 실행될 땐 storeSiteAnalysis에
      // 필지가 이미 있어 선택이 그대로 재시드된다(선택 소실 없음, PR#221 상호작용).
      setProject(created.id, created.name, "draft", created.address);
      const patch = selectionToSiteAnalysisPatch(selectedParcels);
      if (patch) updateSiteAnalysis(patch, { source: "user" });
      setConnectTarget(created.id);
      setConnectNotice(`'${created.name}' 프로젝트가 생성·연결되었습니다.`);
      return created.id;
    } finally {
      creatingProjectRef.current = false;
      setCreatingProject(false);
    }
  }, [selectedParcels, setProject, updateSiteAnalysis]);

  const handleCreateProjectNow = useCallback(() => {
    void connectAsNewProject();
  }, [connectAsNewProject]);

  const handleOutputClick = useCallback(
    async (action: OutputAction) => {
      if (connectTarget === "new" && selectedParcels.length > 0) {
        try {
          await connectAsNewProject();
        } catch {
          // best-effort — 생성 실패해도 산출물 이동은 계속(기준선 정신)
        }
      }
      saveSelectionForOutputs(selectedParcels);
      commitParcelsToContext(selectedParcels);
      router.push(action.href);
    },
    [connectAsNewProject, connectTarget, commitParcelsToContext, router, selectedParcels],
  );

  // 최초 1회만 하이드레이션(이후 사용자 선택을 덮지 않도록 ref 가드). 우선순위:
  //   1) sessionStorage(자기세션 선택 — 좌표·경계까지 리치) → 복원(단, 미연결이면 이번 SPA
  //      세션에 기록된 선택만).
  //   2) 비었으면 활성 프로젝트 스토어 필지 폴백 → 연결 프로젝트의 필지를 지도/산출물에 복원.
  //   ★스토어 seed 시 commitParcelsToContext 재호출 금지(이미 스토어에 있는 값 되쓰면 되먹임 루프·#178).
  //   (refs 선언은 컴포넌트 상단으로 이동 — F1 참고)
  //
  //   ★T1(미연결 잔존 차단): 두 복원 경로 모두 브라우저(localStorage store)·탭(sessionStorage)에
  //     영속돼, 프로젝트를 연결하지 않고 검색도 안 한 '신규 진입'에서 이전 세션 선택이 되살아났다.
  //     - projectId가 있으면(이어하기/연결) 기존대로 복원한다(PR#221 스냅샷 하이드레이션 계약 불변).
  //     - 미연결(projectId 없음)이면: sessionStorage는 '이번 SPA 세션에 기록된 것'(sameSpaSession)
  //       일 때만 복원해 SPA 내 라우트 이동 후 복귀는 유지하되, 하드 리로드/새 탭 잔존은 차단한다.
  //       스토어 폴백(경로 2)은 localStorage라 하드 리로드도 넘어 되살아나므로 미연결이면 아예
  //       건너뛴다(SPA 내 복귀는 sessionStorage 경로가 담당).
  const hasConnectedProject = !!projectId;
  useEffect(() => {
    if (hydratedRef.current) return;
    const stored = readSatongMapSelection();
    if (stored?.parcels.length) {
      const restorable = hasConnectedProject || stored.sameSpaSession;
      if (restorable) {
        hydratedRef.current = true;
        setSelectedParcels(stored.parcels);
        commitParcelsToContext(stored.parcels); // sessionStorage 경로는 기존대로 SSOT 동기화
        const focused = stored.parcels.find((parcel) => parcel.lat != null && parcel.lon != null);
        if (focused?.lat != null && focused.lon != null) {
          setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
        }
        return;
      }
      // 미연결 + SPA 세션 불연속(하드 리로드/새 탭) → 이전 세션 선택 복원 금지. sessionStorage
      //   캐시를 정리해 다른 소비처(PreCheckWorkspace·/analysis 산출물)도 잔존을 읽지 않게 한다.
      hydratedRef.current = true;
      setSelectedParcels([]);
      saveSelectionForOutputs([]);
      return;
    }
    // 폴백: 연결 프로젝트 필지로 seed(재커밋 금지 — 이미 스토어 값). 미연결이면 스킵(위 주석).
    if (!hasConnectedProject) return;
    const seeded = siteAnalysisToSelection(storeSiteAnalysis);
    // ★유효 seed(주소 있는 필지)가 하나라도 나왔을 때만 latch. 전부 주소없어 []면 미확정으로 두어
    //   다음 siteAnalysis 변경(늦은 rehydrate) 때 재시도 허용(리뷰 LOW).
    if (seeded.length) {
      hydratedRef.current = true;
      setSelectedParcels(seeded);
      const focused = seeded.find((parcel) => parcel.lat != null && parcel.lon != null);
      if (focused?.lat != null && focused.lon != null) {
        setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
      }
    }
  }, [commitParcelsToContext, storeSiteAnalysis, hasConnectedProject]);

  // 프로젝트 전환 감지 → 프로젝트 등록 필지로 선택 복원.
  // ★restoreSnapshot(백엔드 스냅샷 GET)은 비동기라 전환 직후엔 storeSiteAnalysis가 비어있을 수
  //   있다. siteAnalysis를 의존성에 포함해 늦게 도착한 필지도 시드한다(읽기단선 방지).
  //   armed 플래그는 전환 시 켜지고 사용자가 직접 편집(추가·삭제·전체취소)하면 꺼져,
  //   자동시드가 사용자 선택을 덮지 않는다. 첫 마운트는 위 하이드레이션(sessionStorage 우선)이
  //   담당하므로 개입하지 않는다(약식 모드 선택 전멸 회귀 방지).
  useEffect(() => {
    const prev = prevProjectIdRef.current;
    const isFirstRun = prev === undefined;
    const isTransition = !isFirstRun && prev !== (projectId ?? null);
    prevProjectIdRef.current = projectId ?? null;
    if (isFirstRun) return;

    if (isTransition) {
      // 이전 프로젝트 선택이 새 프로젝트로 새지 않도록 선택·sessionStorage 즉시 무효화(교차오염 차단)
      hydratedRef.current = true; // 전환 이후 선택 소유권은 이 이펙트 — 초기 하이드레이션 비활성
      projectSeedArmedRef.current = !!projectId;
      lastSeedKeyRef.current = "";
      projectFocusPendingRef.current = !!projectId;
      setSelectedParcels([]);
      setFocusTarget(null);
      setDetailFeature(null); // ★R1 HIGH: 이전 프로젝트 필지 정보가 새 프로젝트 화면에 잔존 금지
      saveSelectionForOutputs([]);
    }

    if (!projectId || !projectSeedArmedRef.current) return;

    const seeded = siteAnalysisToSelection(storeSiteAnalysis);
    if (seeded.length) {
      // 내용 지문이 같으면 스킵 — siteAnalysis 참조만 바뀐 무관 갱신에 재시드·지도 튐 방지.
      //   지문에 면적·용도지역·좌표·경계 유무를 포함해 보강(enrich) 도착은 반영한다.
      const seedKey = seeded
        .map(
          (p) =>
            `${p.id}:${p.areaSqm ?? ""}:${p.zoneType ?? ""}:${p.lat ?? ""}:${p.lon ?? ""}:${p.geometry ? 1 : 0}`,
        )
        .join("|");
      if (seedKey === lastSeedKeyRef.current) return;
      lastSeedKeyRef.current = seedKey;
      // 시드 출처가 스토어이므로 재커밋 금지(#178 되먹임 방지). sessionStorage만 동기화.
      setSelectedParcels(seeded);
      saveSelectionForOutputs(seeded);
      // 지도 이동은 전환 후 1회만(좌표가 보강으로 늦게 오면 그때 1회) — 이후 갱신 때
      //   사용자가 보던 화면을 낚아채지 않는다.
      if (projectFocusPendingRef.current) {
        const focused = seeded.find((parcel) => parcel.lat != null && parcel.lon != null);
        if (focused?.lat != null && focused.lon != null) {
          projectFocusPendingRef.current = false;
          setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
        }
      }
    }
  }, [projectId, storeSiteAnalysis]);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSearchCandidates([]);
      setSearchStatus("idle");
      setSearchError("");
      return;
    }
    let alive = true;
    const timer = window.setTimeout(async () => {
      setSearchStatus("loading");
      setSearchError("");
      try {
        const data = await apiClient.post<SearchResponse>("/zoning/search", {
          body: { query: trimmed },
          useMock: false,
          timeoutMs: 15000,
        });
        if (!alive) return;
        setSearchCandidates(data.candidates ?? []);
        setSearchStatus("idle");
      } catch {
        if (!alive) return;
        setSearchCandidates([]);
        setSearchStatus("error");
        setSearchError("검색 후보를 불러오지 못했습니다.");
      }
    }, 350);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    if (!activeLayerId) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setActiveLayerId(null);
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (popoverRef.current?.contains(target) || railRef.current?.contains(target)) return;
      setActiveLayerId(null);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, [activeLayerId]);

  // 베이스맵 팝오버도 레이어 팝오버와 동일한 닫힘 계약(Esc·외부 포인터다운) — 같은 좌표에
  // 뜨는 형제 UI라 닫힘 규칙이 다르면 사용자가 두 규칙을 학습해야 한다(일관성).
  useEffect(() => {
    if (!basemapOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setBasemapOpen(false);
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (basemapPopoverRef.current?.contains(target) || railRef.current?.contains(target)) return;
      setBasemapOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("pointerdown", onPointerDown);
    };
  }, [basemapOpen]);

  // 베이스맵 스위처 — 우상단 레이어 레일의 '베이스맵' 항목이 여는 팝오버 본문(2026-07-23
  // 사용자 UX 요청: 지도 제어 일원화). 이력: 독립 absolute 섬(bottom-20 right-4) → 하단
  // 도크 bottomDockSlot(2026-07-17 겹침 구조 단일화) → 레일 팝오버(현재).
  // ★07-17 겹침 수정은 유지된다 — 도크 슬롯에서 빠져도 칩 행은 자기 flex flow 그대로이고,
  //   폐기됐던 암묵 예약값(152px)을 되살리지 않는다(레일 팝오버는 칩 행과 다른 코너·레이어).
  // ★레일 hover 전개와의 경합도 없다 — 팝오버는 레일 좌측(right-20)에 별도로 뜬다(레이어
  //   팝오버와 동일 좌표 계약). 상호배타: 하나가 열리면 다른 하나는 닫힌다.
  const basemapSwitcherPanel = (
    <div className="grid grid-cols-4 gap-1.5">
      {BASEMAP_SWITCHES.map((opt) => {
        const active = resolveVWorldBaseLayer(mapLayerState) === opt.base;
        return (
          <button
            key={opt.id}
            type="button"
            aria-pressed={active}
            aria-label={`베이스맵: ${opt.label}`}
            title={`베이스맵: ${opt.label}`}
            onClick={() =>
              handleLayerControlClick("terrain", { id: opt.id, label: opt.label, mapEffect: true })
            }
            className={`rounded-xl border p-1 text-center transition ${
              active
                ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15"
                : "border-transparent hover:border-[var(--line-strong)]"
            }`}
          >
            <span
              aria-hidden
              // 실물 타일을 background-image로 — <img>와 달리 로드 실패 시 깨진 아이콘
              // 없이 뒤의 그라디언트(opt.swatch)가 그대로 폴백된다(무음 열화·정직 유지).
              className={`block h-7 w-full rounded-lg border border-black/10 bg-cover bg-center ${opt.swatch}`}
              style={{ backgroundImage: opt.tiles.map((t) => `url(${t})`).join(", ") }}
            />
            <span className="mt-0.5 block text-[10px] font-black text-[var(--text-primary)]">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );

  return (
    <section className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface)] p-4 shadow-[var(--shadow-lg)] md:p-5">
      <div className="mb-4 flex flex-col gap-3 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-panel)] p-4 shadow-[var(--shadow-sm)] lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="font-[family-name:var(--font-display)] label-caps text-[var(--text-tertiary)]">
            Satong Map OS
          </p>
          <h1 className="mt-2 text-2xl font-black tracking-normal text-[var(--text-primary)] md:text-3xl">
            지도 위에서 입력부터 산출물 생성까지 이어갑니다.
          </h1>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-[var(--text-secondary)]">
            지번·주소 검색, 엑셀 다필지 등록, 지도 선택, 레이어 검토를 한 화면에 통합했습니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-[var(--r-pill)] bg-[var(--accent-soft)] px-3 py-2 text-xs font-black text-[var(--accent-strong)]">
            필지 선택 {selectedParcels.length}건
          </span>
          <span className="rounded-[var(--r-pill)] border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-black text-[var(--text-secondary)]">
            합산 면적 <span className="font-mono">{formatArea(selectedTotalArea || null)}</span>
          </span>
        </div>
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-panel)] p-4 shadow-[var(--shadow-sm)]">
          <div className="rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-secondary)] p-4 text-[var(--text-primary)] shadow-[var(--shadow-md)]">
            <p className="font-[family-name:var(--font-display)] label-caps text-[var(--accent-strong)]">
              Parcel Intake
            </p>
            <h2 className="mt-2 text-xl font-black tracking-normal">통합 필지 입력</h2>
            <p className="mt-2 text-xs font-semibold leading-5 text-[var(--text-secondary)]">
              검색하면 지도 중심이 이동하고, 엑셀을 올리면 다필지 목록이 같은 선택 목록으로 합쳐집니다.
            </p>
          </div>

          {/* 프로젝트 연결 */}
          <div className="mt-4 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3.5">
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-black text-[var(--text-primary)]">
              <Building2 className="size-4 text-[var(--accent-strong)]" aria-hidden />
              연결 프로젝트
            </label>
            <select
              value={connectTarget}
              onChange={(e) => handleConnectTargetChange(e.target.value)}
              className="w-full rounded-[var(--r-input)] border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2.5 text-xs font-bold text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
            >
              <option value="new">새 프로젝트로 등록 (기본)</option>
              <option value="none">프로젝트 연결 안 함 (약식 분석)</option>
              <optgroup label="기존 프로젝트에 연결">
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}{p.address ? ` — ${p.address}` : ""}
                  </option>
                ))}
              </optgroup>
            </select>
            {connectTarget === "none" && (
              <p className="mt-2 text-[11px] font-bold leading-4 text-[var(--text-hint)]">
                산출물은 프로젝트에 저장되지 않습니다.
              </p>
            )}
            {connectNotice && (
              <p className="mt-2 rounded-lg bg-[var(--status-success)]/10 px-2.5 py-1.5 text-[11px] font-bold leading-4 text-[var(--status-success)]">
                {connectNotice}
              </p>
            )}
          </div>

          <div className="mt-4 space-y-3">
            <div className="relative">
              <label className="mb-2 flex items-center gap-2 text-xs font-black text-[var(--text-primary)]">
                <Search className="size-4 text-[var(--accent-strong)]" aria-hidden />
                지번·주소 검색
              </label>
              <div className="flex gap-2">
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") handleSearchSubmit();
                  }}
                  placeholder="예: 의정부동 224, 판교역로 166"
                  className="min-w-0 flex-1 rounded-full border border-[var(--border-muted)] bg-[var(--surface-strong)] px-4 py-3 text-sm font-bold text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-hint)] focus:border-[var(--accent-strong)] focus:bg-[var(--surface-panel)] focus:ring-4 focus:ring-[var(--accent-soft)]"
                />
                <button
                  type="button"
                  onClick={handleSearchSubmit}
                  disabled={!query.trim() || searchStatus === "loading"}
                  className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-[var(--accent-strong)] text-[var(--on-primary)] shadow-[var(--shadow-glow)] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
                  aria-label="검색 추가"
                >
                  {searchStatus === "loading" ? (
                    <Loader2 className="size-5 animate-spin" aria-hidden />
                  ) : (
                    <ChevronRight className="size-5" aria-hidden />
                  )}
                </button>
              </div>
              {searchCandidates.length > 0 && (
                <div className="absolute left-0 right-14 top-[78px] z-30 overflow-hidden rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] shadow-[var(--shadow-xl)]">
                  {searchCandidates.slice(0, 6).map((candidate, index) => {
                    const label = getCandidateLabel(candidate);
                    return (
                      <button
                        key={`${label}-${index}`}
                        type="button"
                        onClick={() => void handleCandidatePick(candidate)}
                        className="flex w-full items-start gap-3 border-b border-[var(--line)] px-4 py-3 text-left last:border-0 hover:bg-[var(--surface-strong)]"
                      >
                        <MapPin className="mt-0.5 size-4 shrink-0 text-[var(--accent-strong)]" aria-hidden />
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-black text-[var(--text-primary)]">
                            {label}
                          </span>
                          <span className="mt-0.5 block text-xs font-semibold text-[var(--text-hint)]">
                            {candidate.kind || candidate.pnu || "주소 후보"}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
              {searchError && (
                <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-[var(--status-error)]">
                  <AlertTriangle className="size-3.5" aria-hidden />
                  {searchError}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center justify-center gap-2 rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-3 text-xs font-black text-[var(--text-primary)] transition hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10"
              >
                {uploadStatus === "loading" ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <FileSpreadsheet className="size-4 text-[var(--accent-strong)]" aria-hidden />
                )}
                엑셀 파일 선택
              </button>
              <button
                type="button"
                onClick={handleTemplateDownload}
                className="inline-flex items-center justify-center gap-2 rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-3 text-xs font-black text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)]"
              >
                <Download className="size-4" aria-hidden />
                양식 다운로드
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                className="hidden"
                onChange={handleExcelUpload}
              />
            </div>
            <UseLlmToggle
              checked={useLlm}
              onChange={setUseLlm}
              label="AI 보조 인식"
              hint="비표준 양식(다중시트·전치·복합셀) 자동 구조분석"
              disabled={uploadStatus === "loading"}
              className="px-1"
            />
            {uploadNote && (
              <p
                className={`rounded-2xl px-3 py-2 text-xs font-bold ${
                  uploadStatus === "error"
                    ? "bg-[var(--status-error)]/10 text-[var(--status-error)]"
                    : "bg-[var(--status-success)]/10 text-[var(--status-success)]"
                }`}
              >
                {uploadNote}
              </p>
            )}
            {verificationReport && (
              <div className="space-y-2 rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] p-3">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="text-xs font-black text-[var(--text-primary)]">업로드 검증 리포트</h4>
                  {verificationReport.llm_used && (
                    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-[var(--ai-accent)]/15 px-2 py-0.5 text-[10px] font-black text-[var(--ai-accent)]">
                      <Bot className="size-3" aria-hidden /> LLM 보조 사용
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className="rounded-full bg-[var(--status-success)]/15 px-2 py-1 text-[11px] font-black text-[var(--status-success)]">
                    확인됨 {verificationReport.counts?.verified ?? 0}
                  </span>
                  <span className="rounded-full bg-[var(--status-info)]/15 px-2 py-1 text-[11px] font-black text-[var(--status-info)]">
                    보정됨 {verificationReport.counts?.corrected ?? 0}
                  </span>
                  <span className="rounded-full bg-[var(--status-warning)]/15 px-2 py-1 text-[11px] font-black text-[var(--status-warning)]">
                    확인필요 {verificationReport.counts?.needs_review ?? 0}
                  </span>
                  <span className="rounded-full bg-[var(--surface-muted)] px-2 py-1 text-[11px] font-black text-[var(--text-secondary)]">
                    제외 {verificationReport.counts?.excluded ?? 0}
                  </span>
                </div>
                {/* ★H3: 확인필요 행도 일단 주입되며, 주입 후 2차 조회에서 자동보정을 시도한다는
                    것을 명확히 안내(과거엔 이 자기치유 경로가 자동반영 제외로 조용히 끊겼었음). */}
                {(verificationReport.counts?.needs_review ?? 0) > 0 && (
                  <p className="text-[11px] font-semibold text-[var(--status-warning)]">
                    확인필요 행은 주입 후 자동보정 시도됩니다 — 아래 사유를 확인해 주세요.
                  </p>
                )}
                {(verificationReport.corrections?.length ?? 0) > 0 && (
                  <p className="text-[11px] font-semibold text-[var(--status-info)]">
                    보정 {verificationReport.corrections?.length}건 —{" "}
                    {(verificationReport.corrections ?? [])
                      .slice(0, 3)
                      .map((c) => `${c.field ?? "필드"}: ${c.before ?? "-"}→${c.after ?? "-"}`)
                      .join(" · ")}
                    {(verificationReport.corrections?.length ?? 0) > 3
                      ? ` 외 ${(verificationReport.corrections?.length ?? 0) - 3}건`
                      : ""}
                  </p>
                )}
                {uploadParcels.filter((p) => p.verification_status === "needs_review").length > 0 && (
                  <ul className="space-y-1">
                    {uploadParcels
                      .filter((p) => p.verification_status === "needs_review")
                      .slice(0, 8)
                      .map((p, i) => (
                        <li
                          key={`${p.address ?? p.jibun ?? p.pnu ?? "row"}-${i}`}
                          className="rounded-lg bg-[var(--status-warning)]/10 px-2 py-1.5 text-[11px] font-semibold text-[var(--status-warning)]"
                        >
                          {p.address || p.jibun || p.pnu || `행 ${i + 1}`} —{" "}
                          {(p.verification_reasons ?? []).join(" · ") || "확인 필요"}
                        </li>
                      ))}
                  </ul>
                )}
                {(verificationReport.warnings?.length ?? 0) > 0 && (
                  <ul className="space-y-1">
                    {(verificationReport.warnings ?? []).map((w, i) => (
                      <li key={i} className="text-[11px] font-semibold text-[var(--status-error)]">
                        {w}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          {/* 선택 필지로 새 프로젝트 생성 — 작업 순서(검색→필지 선택→생성)상 지번·주소/엑셀
              입력 아래, 선택 필지 목록 직전에 둔다. 핸들러·조건은 무변경(JSX 재배치만). */}
          {connectTarget === "new" && selectedParcels.length > 0 && (
            <div className="mt-4">
              <p className="text-[11px] font-bold leading-4 text-[var(--text-hint)]">
                완료(등록)·산출물 실행 시 &apos;{deriveProjectNameFromParcels(selectedParcels) ?? "새 프로젝트"}&apos; 프로젝트가 자동 생성됩니다.
              </p>
              <button
                type="button"
                onClick={handleCreateProjectNow}
                disabled={creatingProject}
                className="mt-2 w-full rounded-[var(--r-input)] border border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 px-3 py-2 text-xs font-black text-[var(--accent-strong)] transition hover:bg-[var(--accent-strong)]/15 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {creatingProject ? "생성 중…" : "선택 필지로 새 프로젝트 생성"}
              </button>
            </div>
          )}

          <div className="mt-5 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-black text-[var(--text-primary)]">선택 필지</h3>
                <p className="mt-1 text-xs font-semibold text-[var(--text-hint)]">
                  검색·엑셀·지도 선택이 같은 목록으로 통합됩니다.
                </p>
              </div>
              {selectedParcels.length > 0 && (
                <div className="flex items-center gap-1.5">
                  {/* I5: 선택 필지 GeoJSON 내보내기 — 측량·타 GIS 연계(기하 없는 필지는 제외 정직 고지) */}
                  <button
                    type="button"
                    onClick={() => exportSelection("geojson")}
                    title="선택 필지를 GeoJSON(FeatureCollection)으로 내려받기"
                    className="rounded-full border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-1.5 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--accent-strong)]"
                  >
                    GeoJSON
                  </button>
                  <button
                    type="button"
                    onClick={() => exportSelection("kml")}
                    title="선택 필지를 KML(구글어스·측량 호환)로 내려받기 — V3"
                    className="rounded-full border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-1.5 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--accent-strong)]"
                  >
                    KML
                  </button>
                  <button
                    type="button"
                    onClick={clearParcels}
                    className="rounded-full border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-1.5 text-xs font-black text-[var(--text-secondary)] hover:text-[var(--status-error)]"
                  >
                    초기화
                  </button>
                </div>
              )}
            </div>
            {exportNote && (
              <p className="mt-2 text-[11px] font-bold text-[var(--text-hint)]">{exportNote}</p>
            )}

            <div className="mt-3 max-h-[360px] space-y-2 overflow-auto pr-1">
              {selectedParcels.length === 0 ? (
                <div className="rounded-[var(--r-panel)] border border-dashed border-[var(--line-strong)] bg-[var(--surface-panel)] px-4 py-10 text-center">
                  <MapPin className="mx-auto size-8 text-[var(--text-hint)]" aria-hidden />
                  <p className="mt-3 text-sm font-black text-[var(--text-primary)]">
                    아직 선택된 필지가 없습니다.
                  </p>
                  <p className="mt-1 text-xs font-semibold text-[var(--text-hint)]">
                    검색하거나 지도에서 필지를 선택하세요.
                  </p>
                </div>
              ) : (
                // ★U4(카드 과점): 지번 전문·PNU 행이 차지하던 공간 압축 — 1줄 헤더(짧은
                //   지번+면적)+칩 1줄. 전체 주소·PNU는 hover title로 보존(정보 손실 없음).
                selectedParcels.map((parcel, index) => (
                  // 카드 클릭 = 상세 패널 + 지도 포커스(좌표 보유 시) — 카드-지도 연동(WS-C).
                  <div
                    key={`${parcel.id}-${index}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => {
                      const feature =
                        selectedMapFeatures.find(
                          (f) => (parcel.pnu && f.pnu === parcel.pnu) || f.address === parcel.address,
                        ) ??
                        ({
                          id: parcel.id,
                          address: parcel.address,
                          pnu: parcel.pnu ?? null,
                          areaSqm: parcel.areaSqm ?? null,
                          zoneType: parcel.zoneType ?? null,
                          jimok: parcel.jimok ?? null,
                          source: parcel.source,
                        } satisfies SatongMapFeature);
                      openFeatureDetail(feature);
                      if (feature.lat != null && feature.lon != null) {
                        setFocusTarget({ lat: feature.lat, lon: feature.lon, label: parcel.address });
                      }
                    }}
                    onKeyDown={(e) => {
                      // ★R1: 중첩 삭제버튼에서의 keydown 버블링이 카드 활성(상세 열기)으로
                      //   번지지 않게 target 가드, Space 스크롤은 preventDefault.
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        e.currentTarget.click();
                      }
                    }}
                    className="cursor-pointer rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2 shadow-[var(--shadow-sm)] transition hover:border-[var(--accent-strong)]/40"
                    title={`${parcel.address}${parcel.pnu ? ` · PNU ${parcel.pnu}` : ""} — 클릭: 상세 정보`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="min-w-0 truncate text-[13px] font-black text-[var(--text-primary)]">
                        {parcel.address?.split(/\s+/).slice(-2).join(" ") || parcel.address}
                      </p>
                      <span className="shrink-0 font-mono text-[11px] font-bold text-[var(--text-secondary)]">
                        {formatArea(parcel.areaSqm)}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation(); // 삭제가 카드 클릭(상세 열기)으로 번지지 않게
                          removeParcel(parcel.id);
                        }}
                        className="shrink-0 rounded-full p-1.5 text-[var(--text-hint)] transition hover:bg-[var(--status-error)]/10 hover:text-[var(--status-error)]"
                        aria-label="필지 제거"
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </button>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1 text-[10px] font-bold">
                      <span className="rounded-full bg-[var(--accent-strong)]/10 px-2 py-0.5 text-[var(--accent-strong)]">
                        {sourceLabel[parcel.source]}
                      </span>
                      {parcel.zoneType && (
                        <span className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--text-secondary)]">
                          {parcel.zoneType}
                        </span>
                      )}
                      {parcel.jimok && (
                        <span className="rounded-full bg-[var(--surface-muted)] px-2 py-0.5 text-[var(--text-secondary)]">
                          지목 {parcel.jimok}
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </aside>

        <section className="min-w-0 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-panel)] p-3 shadow-[var(--shadow-sm)] md:p-4">
          <div className="relative min-h-[720px] overflow-hidden rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--background-deep)]">
            <div className="pointer-events-auto absolute left-4 top-4 z-[380] flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={(event) => event.stopPropagation()}
                className="rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] px-3 py-2 text-xs font-black text-[var(--text-primary)] shadow-[var(--shadow-lg)] backdrop-blur-[var(--glass-blur)]"
                aria-label="사통팔땅 멀티지도"
              >
                사통팔땅 멀티지도
              </button>
              {activeLayers.slice(0, 4).map((layer) => (
                <button
                  key={layer.id}
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    handleLayerClick(layer.id);
                  }}
                  className="rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg)] px-3 py-2 text-xs font-black text-[var(--text-primary)] shadow-[var(--shadow-md)] backdrop-blur-[var(--glass-blur)] transition hover:bg-[var(--glass-bg-strong)]"
                  aria-label={`${layer.label} 레이어 전환`}
                >
                  {layer.label}
                </button>
              ))}
              {activeLayers.length > 4 && (
                <span className="rounded-full border border-[var(--border-muted)] bg-[var(--glass-bg)] px-3 py-2 text-xs font-black text-[var(--text-primary)] shadow-[var(--shadow-md)] backdrop-blur-[var(--glass-blur)]">
                  +{activeLayers.length - 4}
                </span>
              )}
            </div>

            <div className="p-2">
              <SatongMultiMap
                onPickMany={handleMapPickMany}
                onFeatureClick={openFeatureDetail}
                focusTarget={focusTarget}
                autoPreviewFocus
                height={720}
                chrome="immersive"
                selectedParcels={selectedMapFeatures}
                layerState={mapLayerState}
                marketPayload={marketEnabled ? marketPayload : null}
                // ★무목업: 종전 가상 분양단지/경매물건(Math.random) 목업을 실데이터 state로 대체.
                // 분양=/presale/nearby(청약홈)·경매=/auction/search+geocode(온비드) — 위 이펙트에서 조회.
                marketLayer={useMemo(
                  () => ({
                    kind: "trade" as const,
                    type: "apt",
                    showPresale: presaleEnabled,
                    presaleItems: presaleEnabled ? presaleItems : null,
                    showAuction: auctionEnabled,
                    auctionItems: auctionEnabled ? auctionItems : null,
                  }),
                  [presaleEnabled, presaleItems, auctionEnabled, auctionItems],
                )}
                // 상태 노트는 marketLayer 밖 별도 prop — 노트만 바뀔 때 마커 이펙트가 재실행되지
                // 않게 한다(리뷰 LOW). 건수 라벨보다 우선 표기(정직원칙).
                presaleNote={presaleEnabled ? presaleNote || null : null}
                auctionNote={auctionEnabled ? auctionNote || null : null}
                poiPayload={poiEnabled ? poiPayload : null}
                developmentPayload={developmentEnabled ? developmentPayload : null}
                onCenterChange={setMapCenter}
                onBoundaryEnriched={handleBoundaryEnriched}
                onBoundaryStatusChange={handleBoundaryStatusChange}
                clearSignal={clearNonce}
              />
            </div>

            <div
              ref={railRef}
              // ★P1(감사): 고정고는 전 버튼 필요고보다 작아 하단(로드뷰 등)이 클리핑돼 도달
              //   불가였음 — 가용고 내 auto + 세로 스크롤로 전 버튼 접근 보장.
              // ★WP-M4: hover 전개에 더해 앵커 클릭 고정(railPinned)으로도 전개 — 터치 기기 대응.
              // ★U3(비반응형 레일): 상한을 컨테이너뿐 아니라 브라우저 뷰포트(dvh)로도 걸어,
              //   지도가 화면보다 클 때 레일이 폴드 밑으로 늘어나 하단 버튼 도달 불가·페이지
              //   스크롤 시 hover 전개가 풀리던 문제를 해소. 고정(핀) 시 2열 그리드로 접어
              //   버튼 높이를 절반으로 — 어떤 뷰포트에서도 전 버튼 가시(현 14개=7행·400px).
              //   dvh 상한은 supports- 가드로 부가(R1 L5: min() 인자에 미지원 단위가 섞이면
              //   선언 전체가 drop돼 상한이 사라짐) · 핀 폭 128px(48px 버튼×2+gap+p — R1 L4).
              // ★2026-07-23(R1 M): 접힌 높이 h-16(=버튼 1개)은 두 번째 자식인 베이스맵 버튼을
              //   숨겨, 터치 기기에서 배경지도 전환이 3탭(앵커→베이스맵→스와치)이 되고 기능
              //   존재 자체가 비가시였다(종전 하단 도크는 항상 가시·1탭). h-28로 앵커+베이스맵
              //   2개를 상시 노출해 1탭 경로를 복원한다(전개 어포던스인 앵커는 그대로 유지).
              className={`group absolute right-4 top-20 z-[420] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg)] p-2 shadow-[var(--shadow-lg)] backdrop-blur-[var(--glass-blur)] transition-all duration-300 ease-in-out ${
                railPinned
                  ? "grid w-32 auto-rows-min grid-cols-2 gap-2 h-auto max-h-[calc(100%-120px)] supports-[height:100dvh]:max-h-[min(calc(100%-120px),calc(100dvh-176px))] overflow-y-auto"
                  : "flex w-16 flex-col gap-2 h-28 overflow-hidden hover:h-auto hover:max-h-[calc(100%-120px)] supports-[height:100dvh]:hover:max-h-[min(calc(100%-120px),calc(100dvh-176px))] hover:overflow-y-auto"
              }`}
            >
              {/* 앵커(레이어 관리) 버튼 — ★WP-M4: 죽은 버튼을 클릭 고정 토글로 실기능화(터치 전개).
                  아이콘은 MapIcon(지도), 지적도 레이어는 Layers로 분리해 아이콘-기능 1:1. */}
              <button
                type="button"
                onClick={() => setRailPinned((v) => !v)}
                aria-pressed={railPinned}
                aria-label={railPinned ? "레이어 목록 접기" : "레이어 목록 펼치기(고정)"}
                className={`grid size-12 shrink-0 place-items-center rounded-2xl border transition ${
                  railPinned
                    ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/15 text-[var(--accent-strong)]"
                    : "border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--accent-strong)] hover:bg-[var(--surface-strong)] group-hover:border-[var(--line-strong)] group-hover:bg-[var(--surface-muted)] group-hover:text-[var(--text-secondary)]"
                }`}
                title={railPinned ? "레이어 목록 고정 해제" : "지도 레이어 관리 (클릭 고정 · hover 전개)"}
              >
                <MapIcon className={`size-5 ${railPinned ? "" : "animate-pulse group-hover:animate-none"}`} aria-hidden />
              </button>

              {/* 베이스맵 — 지도 표시 제어를 우상단 한 코너로 모으는 항목(2026-07-23 사용자
                  UX 요청). 종전엔 레일=우상단·베이스맵=우하단으로 제어가 분산돼 있었다. */}
              <button
                type="button"
                onClick={() => {
                  setActiveLayerId(null); // 상호배타 — 같은 좌표에 두 팝오버가 겹치지 않게
                  setBasemapOpen((v) => !v);
                }}
                aria-expanded={basemapOpen}
                aria-controls="satong-basemap-popover"
                aria-label="베이스맵 선택"
                title="베이스맵 (일반·위성·하이브리드·회색)"
                className={`grid size-12 shrink-0 place-items-center rounded-2xl border transition ${
                  basemapOpen
                    ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)] shadow-[var(--shadow-glow)]"
                    : "border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--text-secondary)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-strong)]"
                }`}
              >
                <ImageIcon className="size-5" aria-hidden />
              </button>

              {/* 내부 레이어 버튼 리스트 (세로 전개) */}
              {LAYERS.map((layer) => {
                const Icon = layer.icon;
                const enabled = enabledLayers.has(layer.id);
                const isActive = activeLayerId === layer.id;
                return (
                  <button
                    key={layer.id}
                    type="button"
                    onClick={() => handleLayerClick(layer.id)}
                    title={layer.label}
                    className={`grid size-12 shrink-0 place-items-center rounded-2xl border text-[var(--text-secondary)] transition ${
                      isActive
                        ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)] shadow-[var(--shadow-glow)]"
                        : enabled
                          ? "border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/15 text-[var(--primary-dim)]"
                          : "border-[var(--border-muted)] bg-[var(--surface-panel)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-strong)]"
                    }`}
                    aria-label={layer.label}
                  >
                    <Icon className="size-5" aria-hidden />
                  </button>
                );
              })}
            </div>

            {/* 베이스맵 팝오버 — 레일 '베이스맵' 버튼이 여는 패널. 레이어 팝오버와 같은
                좌표 계약(right-20 top-20)이라 상호배타로 열린다.
                이력: 독립 absolute 섬(~07-16) → 하단 도크(07-17 겹침 단일화) → 레일 팝오버(07-23).
                칩 행의 암묵 예약값(152px)은 07-17에 제거됐고 되살리지 않는다(겹침 수정 유지). */}
            {basemapOpen && (
              <div
                ref={basemapPopoverRef}
                id="satong-basemap-popover"
                className="absolute right-20 top-20 z-[430] w-[min(360px,calc(100%-112px))] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] p-4 shadow-[var(--shadow-xl)] backdrop-blur-xl"
              >
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-black text-[var(--text-primary)]">베이스맵</h3>
                  <button
                    type="button"
                    onClick={() => setBasemapOpen(false)}
                    aria-label="베이스맵 닫기"
                    className="grid size-8 place-items-center rounded-xl border border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--text-secondary)] transition hover:bg-[var(--surface-strong)]"
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>
                {basemapSwitcherPanel}
                <p className="mt-3 text-xs font-bold text-[var(--text-tertiary)]">
                  배경 지도를 바꿔도 선택 필지·레이어는 유지됩니다.
                </p>
              </div>
            )}

            {activeLayer && (
              <div
                ref={popoverRef}
                className="absolute right-20 top-20 z-[430] w-[min(360px,calc(100%-112px))] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] p-4 shadow-[var(--shadow-xl)] backdrop-blur-xl"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2.5 py-1 text-[11px] font-black ${statusClass(activeLayer.status)}`}>
                        {statusText(activeLayer.status)}
                      </span>
                      <span className="text-[11px] font-black uppercase tracking-[0.16em] text-[var(--on-surface-muted)]">
                        Layer
                      </span>
                    </div>
                    <h3 className="mt-2 text-lg font-black text-[var(--text-primary)]">{activeLayer.label}</h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveLayerId(null)}
                    className="rounded-full p-2 text-[var(--text-hint)] transition hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
                    aria-label="레이어 설정 닫기"
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>
                <p className="mt-2 text-sm font-semibold leading-6 text-[var(--text-secondary)]">
                  {activeLayer.description}
                </p>
                <div className="mt-4 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3">
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-[var(--on-surface-muted)]">
                    Source
                  </p>
                  <p className="mt-1 text-sm font-bold text-[var(--text-secondary)]">{activeLayer.source}</p>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {activeLayer.controls.map((control) => (
                    <button
                      key={control.id}
                      type="button"
                      disabled={!control.mapEffect}
                      onClick={() => handleLayerControlClick(activeLayer.id, control)}
                      title={control.mapEffect ? `${control.label} 지도 반영` : control.description || "공식 데이터 소스 연결 후 활성화"}
                      className={`rounded-2xl border px-3 py-2 text-xs font-black transition ${
                        layerControls[activeLayer.id]?.includes(control.id)
                          ? "border-[var(--accent-strong)] bg-[var(--accent-strong)] text-[var(--on-primary)]"
                          : control.mapEffect
                            ? "border-[var(--border-muted)] bg-[var(--surface-panel)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10 hover:text-[var(--accent-strong)]"
                            : "cursor-not-allowed border-[var(--border-muted)] bg-[var(--surface-muted)] text-[var(--text-hint)]"
                      }`}
                    >
                      {control.label}
                    </button>
                  ))}
                </div>
                {!isRenderableSatongMapLayer(activeLayer.id) ? (
                  <div className="mt-4 rounded-2xl bg-[var(--status-warning)]/10 px-3 py-2 text-xs font-bold leading-5 text-[var(--status-warning)]">
                    이 레이어는 아직 공식 데이터 소스와 지도 렌더러가 연결되지 않아 지도에 표시하지 않습니다.
                  </div>
                ) : activeLayer.status !== "active" && (
                  <div className="mt-4 rounded-2xl bg-[var(--status-warning)]/10 px-3 py-2 text-xs font-bold leading-5 text-[var(--status-warning)]">
                    선택 필지의 실제 속성 데이터가 확보된 범위에서만 지도에 반영됩니다. 무자료 필지는 추정 표시하지 않습니다.
                  </div>
                )}
              </div>
            )}

            {/* ── WS-C 필지 상세 패널 — 개요·보유 속성(무자료 '-' 정직표기)·산출물 원클릭 퍼널.
                 레이어 패널과 같은 슬롯(상호 배타 — 단일 팝오버 원칙). ── */}
            {/* ★렌더 가드도 3패널 전부를 배타 — 상태 봉합(근원 함수)과 이중 방어. 좌표가
                같은 형제가 늘 때 가드가 따라오지 않으면 겹침이 다시 샌다(07-17 교훈). */}
            {detailFeature && !activeLayer && !basemapOpen && (
              <div
                data-testid="parcel-detail-panel"
                className="absolute right-20 top-20 z-[430] w-[min(360px,calc(100%-112px))] rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--glass-bg-strong)] p-4 shadow-[var(--shadow-xl)] backdrop-blur-xl"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <span className="text-[11px] font-black uppercase tracking-[0.16em] text-[var(--on-surface-muted)]">
                      Parcel
                    </span>
                    <h3 className="mt-1 truncate text-lg font-black text-[var(--text-primary)]">
                      {detailFeature.address?.split(/\s+/).slice(-2).join(" ") || detailFeature.address || "필지"}
                    </h3>
                    <p className="truncate text-xs font-semibold text-[var(--text-hint)]">{detailFeature.address}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDetailFeature(null)}
                    className="rounded-full p-2 text-[var(--text-hint)] transition hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]"
                    aria-label="필지 상세 닫기"
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>

                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-strong)] p-3 text-xs">
                  <div>
                    <dt className="font-black text-[var(--text-hint)]">면적</dt>
                    <dd className="mt-0.5 font-mono font-bold text-[var(--text-primary)]">{formatArea(detailFeature.areaSqm)}</dd>
                  </div>
                  <div>
                    <dt className="font-black text-[var(--text-hint)]">용도지역</dt>
                    <dd className="mt-0.5 font-bold text-[var(--text-primary)]">
                      {detailFeature.zoneType || "-"}
                      {detailFeature.zoneType2 ? ` · ${detailFeature.zoneType2}` : ""}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-[var(--text-hint)]">지목</dt>
                    <dd className="mt-0.5 font-bold text-[var(--text-primary)]">{detailFeature.jimok || "-"}</dd>
                  </div>
                  <div>
                    <dt className="font-black text-[var(--text-hint)]">개별공시지가</dt>
                    <dd className="mt-0.5 font-mono font-bold text-[var(--text-primary)]">
                      {detailFeature.officialPricePerSqm
                        ? `${Math.round(detailFeature.officialPricePerSqm).toLocaleString()}원/㎡`
                        : "-"}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-[var(--text-hint)]">건물 노후도</dt>
                    <dd className="mt-0.5 font-bold text-[var(--text-primary)]">
                      {detailFeature.buildingAgeYears != null
                        ? `${detailFeature.buildingAgeYears}년${detailFeature.builtYear ? ` (준공 ${detailFeature.builtYear})` : ""}`
                        : detailFeature.ageStatus === "no_building"
                          ? "나대지·건물 없음"
                          : detailFeature.ageStatus === "no_approval_date"
                            ? "사용승인일 미기재(연식 미상)" // ★R1: 백엔드 4번째 상태 — 나대지와 구분(정직)
                            : detailFeature.ageStatus === "lookup_failed"
                              ? "조회 실패"
                              : detailFeature.ageStatus === "skipped_bulk"
                                ? "대량 선택 생략"
                                : "-"}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-black text-[var(--text-hint)]">PNU</dt>
                    <dd className="mt-0.5 truncate font-mono font-bold text-[var(--text-secondary)]" title={detailFeature.pnu || undefined}>
                      {detailFeature.pnu || "-"}
                    </dd>
                  </div>
                  {/* ── I7 규제 요약 — 실효 한도·현황·개발여력 인라인(경계 응답 서버 산정치 —
                       분석캐시 불요·#387). 미산정 '-' 정직 표기, 전항 미상이면 안내 1줄.
                       상세 산출·근거는 아래 퍼널의 '종합 부지분석'이 담당(중복 CTA 배제). ── */}
                  <div className="col-span-2 border-t border-[var(--border-muted)] pt-2">
                    <dt className="font-black text-[var(--text-hint)]">규제 요약(실효 한도 — 7계층 min)</dt>
                    <dd className="mt-1 grid grid-cols-3 gap-x-2 text-center">
                      <div>
                        <p className="text-[10px] font-bold text-[var(--text-hint)]">실효 용적률</p>
                        <p className="font-mono font-bold text-[var(--text-primary)]">
                          {detailFeature.effectiveFarPct != null ? `${Math.round(detailFeature.effectiveFarPct)}%` : "-"}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold text-[var(--text-hint)]">실효 건폐율</p>
                        <p className="font-mono font-bold text-[var(--text-primary)]">
                          {detailFeature.effectiveBcrPct != null ? `${Math.round(detailFeature.effectiveBcrPct)}%` : "-"}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold text-[var(--text-hint)]">현황 용적률</p>
                        <p className="font-mono font-bold text-[var(--text-primary)]">
                          {detailFeature.currentFarPct != null ? `${Math.round(detailFeature.currentFarPct)}%` : "-"}
                        </p>
                      </div>
                    </dd>
                    {(() => {
                      const ratio = capacityRatio(detailFeature.effectiveFarPct, detailFeature.currentFarPct);
                      if (ratio == null) {
                        return detailFeature.effectiveFarPct == null && detailFeature.effectiveBcrPct == null && detailFeature.currentFarPct == null ? (
                          <p className="mt-1 text-[10px] font-semibold text-[var(--text-hint)]">
                            산정 자료 미확보 — 용도지역·건축물대장 확보 시 자동 표시(상세는 아래 종합 부지분석)
                          </p>
                        ) : null;
                      }
                      return (
                        <p className={`mt-1 font-mono text-[11px] font-black ${ratio < 0 ? "text-[#a855f7]" : "text-[var(--status-success)]"}`}>
                          {ratio < 0
                            // ★R1 MAJOR: -ratio*100은 '실효 대비 상대%'라 %p 라벨이 오독(초과 절반
                            //   과소 표기 — 200/260에서 "30%p"로 읽힘). 용적률 초과는 점차이가 관행:
                            //   현황−실효 = 진짜 %p(260−200=60%p). ratio<0이면 두 값 모두 non-null.
                            ? `한도 초과 — 현황이 실효 한도를 ${Math.round((detailFeature.currentFarPct as number) - (detailFeature.effectiveFarPct as number))}%p 상회`
                            : `개발여력 ${Math.round(ratio * 100)}% (실효 대비 잔여)`}
                        </p>
                      );
                    })()}
                  </div>

                  {detailFeature.officialPricePerSqm && detailFeature.areaSqm ? (
                    <div className="col-span-2 border-t border-[var(--border-muted)] pt-2">
                      <dt className="font-black text-[var(--text-hint)]">공시지가 총액(참고 — 공시지가×면적)</dt>
                      <dd className="mt-0.5 font-mono font-bold text-[var(--accent-strong)]">
                        {Math.round((detailFeature.officialPricePerSqm * detailFeature.areaSqm) / 10_000).toLocaleString()}만원
                      </dd>
                    </div>
                  ) : null}
                </dl>

                {/* 원클릭 산출물 퍼널 — Output Dock과 동일 공용통로(handleOutputClick: 프로젝트 연결 규약 유지) */}
                <p className="mt-3 text-[11px] font-black uppercase tracking-[0.18em] text-[var(--on-surface-muted)]">
                  이 선택으로 바로 실행
                </p>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {outputActions.map((action) => (
                    <button
                      key={action.id}
                      type="button"
                      disabled={selectedParcels.length === 0}
                      onClick={() => void handleOutputClick(action)}
                      className="rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2 text-left text-xs font-black text-[var(--text-primary)] transition hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {action.label}
                    </button>
                  ))}
                  {/* I3: 카카오 로드뷰(현장 확인) — URL 계약 라이브 검증(302→파노라마). 좌표 없으면 미표시(정직). */}
                  {(() => {
                    const roadview = kakaoRoadviewUrl(detailFeature.lat, detailFeature.lon);
                    return roadview ? (
                      <a
                        href={roadview}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="col-span-2 rounded-2xl border border-[var(--border-muted)] bg-[var(--surface-panel)] px-3 py-2 text-left text-xs font-black text-[var(--text-primary)] transition hover:border-[var(--accent-strong)]/40 hover:bg-[var(--accent-strong)]/10"
                      >
                        <span className="inline-flex items-center gap-1">
                          <Route className="size-3.5" aria-hidden />카카오 로드뷰로 현장 보기 ↗
                        </span>
                      </a>
                    ) : null;
                  })()}
                </div>
                <p className="mt-3 font-mono text-[9px] text-[var(--text-hint)]">
                  출처 VWorld·국토교통부 공간정보 — 무자료 항목은 &quot;-&quot;로 표기(추정 금지)
                </p>
              </div>
            )}
          </div>

          <div className="mt-3 rounded-[var(--r-panel)] border border-[var(--border-muted)] bg-[var(--surface-elevated)] p-3 text-[var(--text-primary)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[var(--accent-strong)]">
                  Output Dock
                </p>
                <h3 className="mt-1 text-lg font-black">선택 필지로 만들 산출물</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsOutputDockOpen((value) => !value)}
                className="rounded-full border border-[var(--border-muted)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-black text-[var(--text-primary)] transition hover:bg-[var(--surface-muted)]"
              >
                {isOutputDockOpen ? "접기" : "열기"}
              </button>
            </div>
            {isOutputDockOpen && (
              <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                {outputActions.map((action) => {
                  const Icon = action.icon;
                  const disabled = selectedParcels.length === 0;
                  return (
                    <button
                      key={action.id}
                      type="button"
                      onClick={() => void handleOutputClick(action)}
                      disabled={disabled}
                      className={`min-h-[112px] rounded-[var(--r-panel)] border p-3 text-left transition ${action.tone} ${
                        disabled ? "cursor-not-allowed opacity-50" : "hover:-translate-y-0.5 hover:shadow-xl"
                      }`}
                    >
                      <Icon className="size-5" aria-hidden />
                      <span className="mt-4 block text-sm font-black">{action.label}</span>
                      <span className="mt-1 block text-xs font-bold opacity-70">{action.description}</span>
                    </button>
                  );
                })}
              </div>
            )}
            {selectedParcels.length === 0 && (
              <p className="mt-3 text-xs font-semibold text-[var(--text-hint)]">
                필지를 하나 이상 선택하면 산출물 생성 경로가 활성화됩니다.
              </p>
            )}
          </div>

          {/* 공공데이터 고지(DESIGN.md B1) — 지도/산출물 데이터 뷰 하단 공용 컴포넌트. */}
          <DataSourceNotice
            source="VWorld·국토교통부·공공데이터포털"
            note="참고용 · 법적 효력 없음"
          />
        </section>
      </div>
    </section>
  );
}

export default SatongMapShell;
