"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ChevronRight,
  Download,
  FileSpreadsheet,
  Gavel,
  Home,
  Landmark,
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

import { apiClient, apiV1BaseUrl } from "@/lib/api-client";
import type {
  ParcelAtPointResult,
  SatongDevelopmentPayload,
  SatongMarketPayload,
  SatongMultiMapProps,
  SatongPoiPayload,
} from "@/components/map/SatongMultiMap";
import {
  isRenderableSatongMapLayer,
  type SatongMapFeature,
  type SatongMapLayerId,
  type SatongMapLayerState,
} from "@/lib/satong-map-layers";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  readSatongMapSelection,
  selectionToSiteAnalysisPatch,
  siteAnalysisParcelsToSelection,
  writeSatongMapSelection,
  type SatongSelectionParcel,
} from "./satong-map-selection";

const SatongMultiMap = dynamic<SatongMultiMapProps>(
  () =>
    import("@/components/map/SatongMultiMap").then(
      (mod) => mod.SatongMultiMap as ComponentType<SatongMultiMapProps>,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="grid h-[720px] place-items-center rounded-[24px] border border-slate-200 bg-slate-50 text-sm font-bold text-slate-500">
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
};

type ParseParcelsResponse = {
  parcels?: ParsedParcel[];
  note?: string | null;
  error?: string | null;
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

const LAYERS: SatongLayer[] = [
  {
    id: "cadastre",
    label: "지적도",
    shortLabel: "지적",
    description: "필지 경계, 지목, 면적, PNU를 선택 기준으로 사용합니다.",
    icon: MapIcon,
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
    source: "VWorld 용도지역(NED 토지특성)",
    controls: [
      { id: "land-use", label: "용도지역", mapEffect: true },
      { id: "district-unit", label: "지구단위", mapEffect: false, description: "도시군관리계획 원천 연결 후 활성화" },
      { id: "development-limit", label: "개발행위 제한", mapEffect: false, description: "개발행위허가 제한구역 원천 연결 후 활성화" },
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
    source: "VWorld 개별공시지가(NED)",
    controls: [
      { id: "unit-price", label: "㎡당 단가", mapEffect: true },
      { id: "year", label: "연도", mapEffect: false, description: "연도별 공시지가 이력 연결 후 활성화" },
      { id: "change-rate", label: "변동률", mapEffect: false, description: "연도별 공시지가 이력 연결 후 활성화" },
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
      { id: "unit-price", label: "면적당 단가", mapEffect: false, description: "면적당 단가 필터 — 향후 제공" },
    ],
  },
  {
    id: "presale",
    label: "분양정보",
    shortLabel: "분양",
    description: "인근 분양 단지, 공급가, 청약 수요 신호를 함께 봅니다.",
    icon: Sparkles,
    status: "needs-source",
    tone: "bg-violet-100 text-violet-950 border-violet-200",
    source: "청약홈/민간 분양자료 수집 필요",
    controls: [
      { id: "supply-type", label: "공급유형", mapEffect: false },
      { id: "presale-price", label: "분양가", mapEffect: false },
      { id: "move-in", label: "입주시기", mapEffect: false },
    ],
  },
  {
    id: "auction",
    label: "공·경매",
    shortLabel: "경매",
    description: "공매와 경매 물건을 토지 속성과 함께 검토합니다.",
    icon: Gavel,
    status: "needs-source",
    tone: "bg-amber-100 text-amber-950 border-amber-200",
    source: "온비드/법원경매 연동 필요",
    controls: [
      { id: "appraisal", label: "감정가", mapEffect: false },
      { id: "minimum-bid", label: "최저가", mapEffect: false },
      { id: "bid-date", label: "입찰일", mapEffect: false },
      { id: "bid-rate", label: "낙찰률", mapEffect: false },
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
    source: "VWorld/국토정보 플랫폼 연동 필요",
    controls: [
      { id: "base", label: "기본지도", mapEffect: true },
      { id: "satellite", label: "위성", mapEffect: true },
      { id: "hybrid", label: "항공뷰", mapEffect: true },
      { id: "elevation", label: "표고", mapEffect: false, description: "표고/경사도 격자 원천 연결 후 활성화" },
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
  if (status === "active") return "bg-emerald-100 text-emerald-700";
  if (status === "ready") return "bg-blue-100 text-blue-700";
  return "bg-amber-100 text-amber-700";
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
  // 읽기 셀렉터 — 활성 프로젝트 필지를 precheck 선택으로 하이드레이션(SSOT 통일). 헤더가 읽는
  //   siteAnalysis와 동일 출처라 균열 아님. sessionStorage(자기세션 선택)가 우선, 이건 폴백.
  const storeParcels = useProjectContextStore((state) => state.siteAnalysis?.parcels);
  const storeCoordinates = useProjectContextStore((state) => state.siteAnalysis?.coordinates);
  const [query, setQuery] = useState("");
  const [searchCandidates, setSearchCandidates] = useState<SearchCandidate[]>([]);
  const [searchStatus, setSearchStatus] = useState<"idle" | "loading" | "error">("idle");
  const [searchError, setSearchError] = useState("");
  const [selectedParcels, setSelectedParcels] = useState<SatongParcel[]>([]);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "loading" | "error">("idle");
  const [uploadNote, setUploadNote] = useState("");
  const [focusTarget, setFocusTarget] = useState<{ lat: number; lon: number; label?: string } | null>(null);
  const [enabledLayers, setEnabledLayers] = useState<Set<SatongMapLayerId>>(() => new Set(["cadastre"]));
  const [layerControls, setLayerControls] = useState<SatongMapLayerState["controlsByLayer"]>(() => defaultControlsByLayer());
  const [activeLayerId, setActiveLayerId] = useState<SatongMapLayerId | null>(null);
  const [isOutputDockOpen, setIsOutputDockOpen] = useState(true);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);

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
  // ★선택필지가 있으면 그 필지 좌표만 사용(좌표 없으면 null → POI는 주소 지오코딩으로 해소).
  //   선택이 전혀 없을 때만(브라우즈 모드) 지도중심 폴백(P1). 좌표없는 선택필지(엑셀 업로드 등)가
  //   엉뚱한 지도중심 POI로 폴백되는 역전을 차단(리뷰 LOW).
  const hasSelection = marketAnchor != null;
  const poiAnchorLat = hasSelection ? marketAnchor?.lat ?? null : mapCenter?.lat ?? null;
  const poiAnchorLon = hasSelection ? marketAnchor?.lon ?? null : mapCenter?.lon ?? null;
  useEffect(() => {
    if (!poiEnabled || (poiAnchorLat == null && !marketAnchorAddress)) {
      setPoiPayload(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongPoiPayload>("/site-score/poi-infra", {
          body: {
            lat: poiAnchorLat ?? undefined,
            lon: poiAnchorLon ?? undefined,
            address: marketAnchorAddress || undefined,
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
  }, [poiEnabled, poiAnchorLat, poiAnchorLon, marketAnchorAddress]);

  // ── 개발계획 레이어 배선: 레이어 ON + 선택필지 좌표 있으면 주변 도시계획시설 조회 ──
  //   /zoning/development-facilities 는 lat/lon 필수(주소 지오코딩 없음) — 좌표 없으면 조회 생략.
  //   무자료·실패는 빈 facilities + note 정직 전달(무날조). 패턴은 실거래·POI와 동일.
  const [developmentPayload, setDevelopmentPayload] = useState<SatongDevelopmentPayload | null>(null);
  const developmentEnabled = enabledLayers.has("development");
  useEffect(() => {
    if (!developmentEnabled || poiAnchorLat == null || poiAnchorLon == null) {
      setDevelopmentPayload(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiClient.post<SatongDevelopmentPayload>("/zoning/development-facilities", {
          // kinds:"all" — 지도 레이어는 전체 도시계획시설(도로·광장·학교·유통 등) 표시.
          //   (기본 "rail"은 입지 신호용 철도 전용 — 기존 소비처 동작 보존)
          body: { lat: poiAnchorLat, lon: poiAnchorLon, radius_m: 1000, kinds: "all" },
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
  }, [developmentEnabled, poiAnchorLat, poiAnchorLon]);

  const outputActions: OutputAction[] = useMemo(
    () => [
      {
        id: "analysis",
        label: "종합 부지분석",
        description: "다필지·규제·입지",
        href: `/${locale}/analysis`,
        icon: MapPin,
        tone: "border-lime-200 bg-lime-50 text-lime-950",
      },
      {
        id: "permits",
        label: "인허가 체크리스트",
        description: "허가 가능성·보완 항목",
        href: `/${locale}/permits`,
        icon: CheckCircle2,
        tone: "border-rose-200 bg-rose-50 text-rose-950",
      },
      {
        id: "market",
        label: "시장·분양 리포트",
        description: "시세·수요·공급",
        href: `/${locale}/market-insights`,
        icon: LineChart,
        tone: "border-sky-200 bg-sky-50 text-sky-950",
      },
      {
        id: "design",
        label: "건축개요·CAD 계획도면",
        description: "법규 맞춤 계획안",
        href: `/${locale}/design-studio`,
        icon: Building2,
        tone: "border-blue-200 bg-blue-50 text-blue-950",
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

  const addParcels = useCallback(
    (incoming: SatongParcel[]) => {
      if (incoming.length === 0) return;
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
        commitParcelsToContext(next);
        saveSelectionForOutputs(next);
        return next;
      });
    },
    [commitParcelsToContext],
  );

  const removeParcel = useCallback(
    (id: string) => {
      setSelectedParcels((prev) => {
        const next = prev.filter((parcel) => parcel.id !== id);
        if (next.length > 0) {
          commitParcelsToContext(next);
          saveSelectionForOutputs(next);
        }
        return next;
      });
    },
    [commitParcelsToContext],
  );

  const clearParcels = useCallback(() => {
    setSelectedParcels([]);
    setFocusTarget(null);
    saveSelectionForOutputs([]);
  }, []);

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
      const form = new FormData();
      form.append("file", file);
      try {
        const data = await apiClient.post<ParseParcelsResponse>("/zoning/parse-parcels", {
          body: form,
          useMock: false,
          timeoutMs: 60000,
        });
        if (data.error) {
          setUploadStatus("error");
          setUploadNote(data.error);
          return;
        }
        const parcels = (data.parcels ?? []).map(parsedParcelToSelection);
        addParcels(parcels);
        setUploadStatus("idle");
        setUploadNote(
          data.note ||
            (parcels.length > 0
              ? `${parcels.length}개 필지를 지도 선택 목록에 반영했습니다.`
              : "엑셀에서 등록 가능한 필지를 찾지 못했습니다."),
        );
      } catch {
        setUploadStatus("error");
        setUploadNote("엑셀 파일 처리 중 오류가 발생했습니다.");
      } finally {
        event.target.value = "";
      }
    },
    [addParcels],
  );

  const handleTemplateDownload = useCallback(() => {
    if (typeof window === "undefined") return;
    window.location.href = `${apiV1BaseUrl()}/zoning/land-schedule-template`;
  }, []);

  const handleLayerClick = useCallback((layerId: SatongMapLayerId) => {
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

  const handleOutputClick = useCallback(
    (action: OutputAction) => {
      saveSelectionForOutputs(selectedParcels);
      commitParcelsToContext(selectedParcels);
      router.push(action.href);
    },
    [commitParcelsToContext, router, selectedParcels],
  );

  // 최초 1회만 하이드레이션(이후 사용자 선택을 덮지 않도록 ref 가드). 우선순위:
  //   1) sessionStorage(자기세션 선택 — 좌표·경계까지 리치) → 있으면 그대로(기존 동작).
  //   2) 비었으면 활성 프로젝트 스토어 필지 폴백 → 헤더의 12필지를 지도/산출물에 복원.
  //   ★스토어 seed 시 commitParcelsToContext 재호출 금지(이미 스토어에 있는 값 되쓰면 되먹임 루프·#178).
  const hydratedRef = useRef(false);
  useEffect(() => {
    if (hydratedRef.current) return;
    const stored = readSatongMapSelection();
    if (stored?.parcels.length) {
      hydratedRef.current = true;
      setSelectedParcels(stored.parcels);
      commitParcelsToContext(stored.parcels); // sessionStorage 경로는 기존대로 SSOT 동기화
      const focused = stored.parcels.find((parcel) => parcel.lat != null && parcel.lon != null);
      if (focused?.lat != null && focused.lon != null) {
        setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
      }
      return;
    }
    // 폴백: 활성 프로젝트 필지로 seed(재커밋 금지 — 이미 스토어 값).
    if (storeParcels?.length) {
      const seeded = siteAnalysisParcelsToSelection(storeParcels, storeCoordinates ?? null);
      // ★유효 seed(주소 있는 필지)가 하나라도 나왔을 때만 latch. 전부 주소없어 []면 미확정으로 두어
      //   다음 storeParcels 변경(늦은 rehydrate) 때 재시도 허용(리뷰 LOW).
      if (seeded.length) {
        hydratedRef.current = true;
        setSelectedParcels(seeded);
        const focused = seeded.find((parcel) => parcel.lat != null && parcel.lon != null);
        if (focused?.lat != null && focused.lon != null) {
          setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
        }
      }
    }
  }, [commitParcelsToContext, storeParcels, storeCoordinates]);

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

  return (
    <section className="min-w-0 rounded-[32px] border border-slate-200 bg-[#f5f9fb] p-4 shadow-[0_24px_80px_rgba(15,23,42,0.08)] md:p-5">
      <div className="mb-4 flex flex-col gap-3 rounded-[28px] border border-white/80 bg-white/90 p-4 shadow-sm lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.24em] text-emerald-700">
            Satong Map OS
          </p>
          <h1 className="mt-2 text-2xl font-black tracking-normal text-slate-950 md:text-3xl">
            지도 위에서 입력부터 산출물 생성까지 이어갑니다.
          </h1>
          <p className="mt-2 max-w-3xl text-sm font-semibold leading-6 text-slate-600">
            지번·주소 검색, 엑셀 다필지 등록, 지도 선택, 레이어 검토를 한 화면에 통합했습니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-lime-100 px-3 py-2 text-xs font-black text-lime-950">
            필지 선택 {selectedParcels.length}건
          </span>
          <span className="rounded-full bg-sky-100 px-3 py-2 text-xs font-black text-sky-950">
            합산 면적 {formatArea(selectedTotalArea || null)}
          </span>
        </div>
      </div>

      <div className="grid min-w-0 gap-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        <aside className="min-w-0 rounded-[28px] border border-slate-200 bg-white p-4 shadow-sm">
          <div className="rounded-[24px] bg-[#0b120d] p-4 text-white shadow-[0_18px_60px_rgba(11,18,13,0.18)]">
            <p className="text-[11px] font-black uppercase tracking-[0.24em] text-lime-300">
              Parcel Intake
            </p>
            <h2 className="mt-2 text-xl font-black tracking-normal">통합 필지 입력</h2>
            <p className="mt-2 text-xs font-semibold leading-5 text-white/70">
              검색하면 지도 중심이 이동하고, 엑셀을 올리면 다필지 목록이 같은 선택 목록으로 합쳐집니다.
            </p>
          </div>

          <div className="mt-4 space-y-3">
            <div className="relative">
              <label className="mb-2 flex items-center gap-2 text-xs font-black text-slate-700">
                <Search className="size-4 text-blue-600" aria-hidden />
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
                  className="min-w-0 flex-1 rounded-full border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-900 outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
                />
                <button
                  type="button"
                  onClick={handleSearchSubmit}
                  disabled={!query.trim() || searchStatus === "loading"}
                  className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-45"
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
                <div className="absolute left-0 right-14 top-[78px] z-30 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
                  {searchCandidates.slice(0, 6).map((candidate, index) => {
                    const label = getCandidateLabel(candidate);
                    return (
                      <button
                        key={`${label}-${index}`}
                        type="button"
                        onClick={() => void handleCandidatePick(candidate)}
                        className="flex w-full items-start gap-3 border-b border-slate-100 px-4 py-3 text-left last:border-0 hover:bg-slate-50"
                      >
                        <MapPin className="mt-0.5 size-4 shrink-0 text-blue-600" aria-hidden />
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-black text-slate-900">
                            {label}
                          </span>
                          <span className="mt-0.5 block text-xs font-semibold text-slate-500">
                            {candidate.kind || candidate.pnu || "주소 후보"}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
              {searchError && (
                <p className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-rose-600">
                  <AlertTriangle className="size-3.5" aria-hidden />
                  {searchError}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-xs font-black text-slate-800 transition hover:border-blue-200 hover:bg-blue-50"
              >
                {uploadStatus === "loading" ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <FileSpreadsheet className="size-4 text-emerald-600" aria-hidden />
                )}
                엑셀 파일 선택
              </button>
              <button
                type="button"
                onClick={handleTemplateDownload}
                className="inline-flex items-center justify-center gap-2 rounded-2xl border border-lime-200 bg-lime-100 px-3 py-3 text-xs font-black text-lime-950 transition hover:bg-lime-200"
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
            {uploadNote && (
              <p
                className={`rounded-2xl px-3 py-2 text-xs font-bold ${
                  uploadStatus === "error"
                    ? "bg-rose-50 text-rose-700"
                    : "bg-emerald-50 text-emerald-700"
                }`}
              >
                {uploadNote}
              </p>
            )}
          </div>

          <div className="mt-5 rounded-[24px] border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-black text-slate-950">선택 필지</h3>
                <p className="mt-1 text-xs font-semibold text-slate-500">
                  검색·엑셀·지도 선택이 같은 목록으로 통합됩니다.
                </p>
              </div>
              {selectedParcels.length > 0 && (
                <button
                  type="button"
                  onClick={clearParcels}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-black text-slate-600 hover:text-rose-600"
                >
                  초기화
                </button>
              )}
            </div>

            <div className="mt-3 max-h-[360px] space-y-2 overflow-auto pr-1">
              {selectedParcels.length === 0 ? (
                <div className="rounded-[22px] border border-dashed border-slate-300 bg-white px-4 py-10 text-center">
                  <MapPin className="mx-auto size-8 text-slate-300" aria-hidden />
                  <p className="mt-3 text-sm font-black text-slate-700">
                    아직 선택된 필지가 없습니다.
                  </p>
                  <p className="mt-1 text-xs font-semibold text-slate-500">
                    검색하거나 지도에서 필지를 선택하세요.
                  </p>
                </div>
              ) : (
                selectedParcels.map((parcel, index) => (
                  <div
                    key={`${parcel.id}-${index}`}
                    className="rounded-[20px] border border-slate-200 bg-white p-3 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-black text-slate-950">
                          {parcel.address}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] font-bold">
                          <span className="rounded-full bg-blue-50 px-2 py-1 text-blue-700">
                            {sourceLabel[parcel.source]}
                          </span>
                          {parcel.zoneType && (
                            <span className="rounded-full bg-lime-50 px-2 py-1 text-lime-800">
                              {parcel.zoneType}
                            </span>
                          )}
                          {parcel.jimok && (
                            <span className="rounded-full bg-slate-100 px-2 py-1 text-slate-600">
                              지목 {parcel.jimok}
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeParcel(parcel.id)}
                        className="rounded-full p-2 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                        aria-label="필지 제거"
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </button>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs font-bold text-slate-500">
                      <span>면적 {formatArea(parcel.areaSqm)}</span>
                      <span className="truncate">PNU {parcel.pnu || "-"}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </aside>

        <section className="min-w-0 rounded-[28px] border border-slate-200 bg-white p-3 shadow-sm md:p-4">
          <div className="relative min-h-[720px] overflow-hidden rounded-[24px] border border-slate-200 bg-slate-100">
            <div className="pointer-events-auto absolute left-4 top-4 z-[380] flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={(event) => event.stopPropagation()}
                className="rounded-full bg-[#0b120d]/90 px-3 py-2 text-xs font-black text-white shadow-xl"
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
                  className="rounded-full bg-white/90 px-3 py-2 text-xs font-black text-slate-800 shadow transition hover:bg-white"
                  aria-label={`${layer.label} 레이어 전환`}
                >
                  {layer.label}
                </button>
              ))}
              {activeLayers.length > 4 && (
                <span className="rounded-full bg-white/90 px-3 py-2 text-xs font-black text-slate-800 shadow">
                  +{activeLayers.length - 4}
                </span>
              )}
            </div>

            <div className="p-2">
              <SatongMultiMap
                onPickMany={handleMapPickMany}
                focusTarget={focusTarget}
                autoPreviewFocus
                height={720}
                chrome="immersive"
                selectedParcels={selectedMapFeatures}
                layerState={mapLayerState}
                marketPayload={marketEnabled ? marketPayload : null}
                // v1 스코프: 아파트 매매 고정(명시). 유형/기간 필터는 '향후 제공' 컨트롤과 함께 확장 —
                // apt 실거래 없는 토지권역은 '실거래 무자료'로 정직 표기(리뷰 MEDIUM 인지·의도 명시).
                marketLayer={{ kind: "trade", type: "apt" }}
                poiPayload={poiEnabled ? poiPayload : null}
                developmentPayload={developmentEnabled ? developmentPayload : null}
                onCenterChange={setMapCenter}
              />
            </div>

            <div
              ref={railRef}
              className="absolute right-4 top-20 z-[420] flex flex-col gap-2 rounded-[22px] border border-white/70 bg-white/90 p-2 shadow-2xl backdrop-blur"
            >
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
                    className={`group grid size-12 place-items-center rounded-2xl border text-slate-600 transition ${
                      isActive
                        ? "border-slate-950 bg-slate-950 text-white"
                        : enabled
                          ? "border-blue-200 bg-blue-50 text-blue-700"
                          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                    }`}
                    aria-label={layer.label}
                  >
                    <Icon className="size-5" aria-hidden />
                  </button>
                );
              })}
            </div>

            {activeLayer && (
              <div
                ref={popoverRef}
                className="absolute right-20 top-20 z-[430] w-[min(360px,calc(100%-112px))] rounded-[26px] border border-slate-200 bg-white p-4 shadow-2xl"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2.5 py-1 text-[11px] font-black ${statusClass(activeLayer.status)}`}>
                        {statusText(activeLayer.status)}
                      </span>
                      <span className="text-[11px] font-black uppercase tracking-[0.16em] text-slate-400">
                        Layer
                      </span>
                    </div>
                    <h3 className="mt-2 text-lg font-black text-slate-950">{activeLayer.label}</h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => setActiveLayerId(null)}
                    className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                    aria-label="레이어 설정 닫기"
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>
                <p className="mt-2 text-sm font-semibold leading-6 text-slate-600">
                  {activeLayer.description}
                </p>
                <div className="mt-4 rounded-[20px] border border-slate-200 bg-slate-50 p-3">
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400">
                    Source
                  </p>
                  <p className="mt-1 text-sm font-bold text-slate-700">{activeLayer.source}</p>
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
                          ? "border-blue-300 bg-blue-600 text-white"
                          : control.mapEffect
                            ? "border-slate-200 bg-white text-slate-700 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                            : "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
                      }`}
                    >
                      {control.label}
                    </button>
                  ))}
                </div>
                {!isRenderableSatongMapLayer(activeLayer.id) ? (
                  <div className="mt-4 rounded-2xl bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-800">
                    이 레이어는 아직 공식 데이터 소스와 지도 렌더러가 연결되지 않아 지도에 표시하지 않습니다.
                  </div>
                ) : activeLayer.status !== "active" && (
                  <div className="mt-4 rounded-2xl bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-800">
                    선택 필지의 실제 속성 데이터가 확보된 범위에서만 지도에 반영됩니다. 무자료 필지는 추정 표시하지 않습니다.
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="mt-3 rounded-[24px] border border-slate-200 bg-[#0b120d] p-3 text-white">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.22em] text-lime-300">
                  Output Dock
                </p>
                <h3 className="mt-1 text-lg font-black">선택 필지로 만들 산출물</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsOutputDockOpen((value) => !value)}
                className="rounded-full border border-white/15 bg-white/10 px-3 py-2 text-xs font-black text-white transition hover:bg-white/15"
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
                      onClick={() => handleOutputClick(action)}
                      disabled={disabled}
                      className={`min-h-[112px] rounded-[22px] border p-3 text-left transition ${action.tone} ${
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
              <p className="mt-3 text-xs font-semibold text-white/55">
                필지를 하나 이상 선택하면 산출물 생성 경로가 활성화됩니다.
              </p>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

export default SatongMapShell;
