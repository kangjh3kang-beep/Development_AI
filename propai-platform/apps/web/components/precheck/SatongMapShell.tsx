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
import type { ParcelAtPointResult } from "@/components/map/ParcelPickerMap";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  readSatongMapSelection,
  selectionToSiteAnalysisPatch,
  writeSatongMapSelection,
  type SatongSelectionParcel,
} from "./satong-map-selection";

type ParcelPickerMapProps = {
  onPickMany?: (parcels: ParcelAtPointResult[]) => void;
  focusTarget?: { lat: number; lon: number; label?: string } | null;
  autoPreviewFocus?: boolean;
  height?: number;
  chrome?: "default" | "immersive";
};

const ParcelPickerMap = dynamic<ParcelPickerMapProps>(
  () =>
    import("@/components/map/ParcelPickerMap").then(
      (mod) => mod.ParcelPickerMap as ComponentType<ParcelPickerMapProps>,
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
  id: string;
  label: string;
  shortLabel: string;
  description: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  status: LayerStatus;
  tone: string;
  source: string;
  controls: string[];
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
    controls: ["필지 경계", "선택 필지", "주변 필지"],
  },
  {
    id: "zoning",
    label: "용도지역",
    shortLabel: "용도",
    description: "국계법 상한과 지자체 조례 연결을 전제로 레이어를 분리합니다.",
    icon: Landmark,
    status: "ready",
    tone: "bg-sky-100 text-sky-950 border-sky-200",
    source: "토지이음/공간정보 연동 필요",
    controls: ["용도지역", "지구단위", "개발행위 제한"],
  },
  {
    id: "official-price",
    label: "공시지가",
    shortLabel: "공시",
    description: "선택 필지의 연도별 개별공시지가와 주변 단가를 비교합니다.",
    icon: LineChart,
    status: "ready",
    tone: "bg-emerald-100 text-emerald-950 border-emerald-200",
    source: "공시가격 API 연동 필요",
    controls: ["연도", "㎡당 단가", "변동률"],
  },
  {
    id: "age",
    label: "노후도",
    shortLabel: "노후",
    description: "건축물대장 기반 준공연도와 정비 가능성을 색상으로 구분합니다.",
    icon: Building2,
    status: "ready",
    tone: "bg-rose-100 text-rose-950 border-rose-200",
    source: "건축물대장/세움터 연동 필요",
    controls: ["건축연도", "구조", "층수", "주용도"],
  },
  {
    id: "transactions",
    label: "실거래·시세",
    shortLabel: "시세",
    description: "실거래, 경매 감정가, 주변 유사 사례를 같은 지도에서 비교합니다.",
    icon: Home,
    status: "ready",
    tone: "bg-blue-100 text-blue-950 border-blue-200",
    source: "국토부 실거래/매물 DB 연동 필요",
    controls: ["거래연도", "거래유형", "총액", "면적당 단가"],
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
    controls: ["공급유형", "분양가", "입주시기"],
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
    controls: ["감정가", "최저가", "입찰일", "낙찰률"],
  },
  {
    id: "poi",
    label: "교통·편의 POI",
    shortLabel: "POI",
    description: "역세권, 학교, 상권, 편의시설을 입지 점수화에 사용합니다.",
    icon: TrainFront,
    status: "ready",
    tone: "bg-cyan-100 text-cyan-950 border-cyan-200",
    source: "카카오/공공데이터 POI 연동 필요",
    controls: ["역", "학교", "상권", "공원", "병원"],
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
    controls: ["지형", "위성", "항공뷰", "표고"],
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
    controls: ["로드뷰", "접도", "차량 진입", "보행 접근"],
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
  return `${Math.round(value).toLocaleString()}㎡`;
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
    source: "map",
  };
}

function saveSelectionForOutputs(parcels: SatongParcel[]): void {
  writeSatongMapSelection(parcels);
}

export function SatongMapShell({ locale }: { locale: string }) {
  const router = useRouter();
  const updateSiteAnalysis = useProjectContextStore((state) => state.updateSiteAnalysis);
  const [query, setQuery] = useState("");
  const [searchCandidates, setSearchCandidates] = useState<SearchCandidate[]>([]);
  const [searchStatus, setSearchStatus] = useState<"idle" | "loading" | "error">("idle");
  const [searchError, setSearchError] = useState("");
  const [selectedParcels, setSelectedParcels] = useState<SatongParcel[]>([]);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "loading" | "error">("idle");
  const [uploadNote, setUploadNote] = useState("");
  const [focusTarget, setFocusTarget] = useState<{ lat: number; lon: number; label?: string } | null>(null);
  const [enabledLayers, setEnabledLayers] = useState<Set<string>>(() => new Set(["cadastre"]));
  const [activeLayerId, setActiveLayerId] = useState<string | null>(null);
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

  const handleLayerClick = useCallback((layerId: string) => {
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

  useEffect(() => {
    const stored = readSatongMapSelection();
    if (!stored?.parcels.length) return;
    setSelectedParcels(stored.parcels);
    commitParcelsToContext(stored.parcels);
    const focused = stored.parcels.find((parcel) => parcel.lat != null && parcel.lon != null);
    if (focused?.lat != null && focused.lon != null) {
      setFocusTarget({ lat: focused.lat, lon: focused.lon, label: focused.address });
    }
  }, [commitParcelsToContext]);

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
            <div className="pointer-events-none absolute left-4 top-4 z-[380] flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-[#0b120d]/90 px-3 py-2 text-xs font-black text-white shadow-xl">
                사통팔땅 멀티지도
              </span>
              {activeLayers.slice(0, 4).map((layer) => (
                <span
                  key={layer.id}
                  className="rounded-full bg-white/90 px-3 py-2 text-xs font-black text-slate-800 shadow"
                >
                  {layer.label}
                </span>
              ))}
              {activeLayers.length > 4 && (
                <span className="rounded-full bg-white/90 px-3 py-2 text-xs font-black text-slate-800 shadow">
                  +{activeLayers.length - 4}
                </span>
              )}
            </div>

            <div className="p-2">
              <ParcelPickerMap
                onPickMany={handleMapPickMany}
                focusTarget={focusTarget}
                autoPreviewFocus
                height={720}
                chrome="immersive"
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
                      key={control}
                      type="button"
                      className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                    >
                      {control}
                    </button>
                  ))}
                </div>
                {activeLayer.status !== "active" && (
                  <div className="mt-4 rounded-2xl bg-amber-50 px-3 py-2 text-xs font-bold leading-5 text-amber-800">
                    실데이터 연결 전까지 이 레이어는 설정 구조와 산출물 연결 상태만 표시합니다.
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
