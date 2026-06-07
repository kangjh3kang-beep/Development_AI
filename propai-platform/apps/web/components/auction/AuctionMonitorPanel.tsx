"use client";

/**
 * 경·공매 모니터링 센터 (내 경공매 탭).
 *
 * 관심대상 3방법 등록 + 관심대상별 매칭결과 모니터링.
 *  ⓐ 토지조서 보유토지: 자동연동 안내 + 등록수(GET /auction/watchlist landschedule)
 *  ⓑ Excel 업로드: POST /auction/watchlist/upload (multipart, field `file`)
 *  ⓒ 지도 구획 그리기: Leaflet 네이티브 클릭 폴리곤 → POST /auction/regions
 *  + 매칭결과: GET /auction/monitor?group_by=source / 수동실행 POST /auction/monitor/run
 *
 * ★무목업: 실 API·실데이터만. 매칭 없으면 빈상태 안내, 업로드 실패/미인식 정직 표기,
 *  지오코딩/키없음 note 노출. 가짜 물건/좌표 금지.
 *
 * 지도 엔진: Leaflet + OpenStreetMap (CDN 동적로드, 새 npm 의존성 0).
 * 폴리곤: leaflet-draw 미설치 → 지도 클릭으로 정점 추가, "구역 완료" 버튼으로 폴리곤 닫기(네이티브).
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

declare global {
  interface Window {
    L: any;
  }
}

// ---- 백엔드 계약 타입 (prefix /api/v1/auction) ----
type WatchTarget = {
  id?: number | string | null;
  label?: string | null;
  watch_source?: string | null; // landschedule | excel | region
  pnu?: string | null;
  address?: string | null;
  project_id?: string | null;
  created_at?: string | null;
};

type WatchlistResponse = {
  items?: WatchTarget[];
  total?: number | null;
  note?: string | null;
};

type UploadResponse = {
  created?: number | null;
  parsed_count?: number | null;
  skipped_rows?: number | null;
  total_rows?: number | null;
  detected_columns?: { pnu?: string | null; address?: string | null; label?: string | null } | null;
  examples?: Array<Record<string, unknown>> | null;
  note?: string | null;
};

type RegionGeoJson = {
  type: "Polygon";
  coordinates: number[][][];
};

type Region = {
  id: number | string;
  label?: string | null;
  geojson?: RegionGeoJson | null;
  created_at?: string | null;
};

type RegionsResponse = {
  items?: Region[];
  total?: number | null;
};

type EstWin = {
  est_win_low?: number | null;
  est_win_mid?: number | null;
  est_win_high?: number | null;
  is_estimate?: boolean | null;
} | null;

type MonitorMatch = {
  address?: string | null;
  usage?: string | null;
  kind?: string | null;
  appraisal_price?: number | null;
  min_bid_price?: number | null;
  fail_count?: number | null;
  est_win?: EstWin;
  status?: string | null;
  watch_target_id?: number | string | null;
  watch_label?: string | null;
  project_id?: string | null;
};

type MonitorGroups = {
  landschedule?: MonitorMatch[];
  excel?: MonitorMatch[];
  region?: MonitorMatch[];
};

type MonitorResponse = {
  group_by?: string | null;
  groups?: MonitorGroups | null;
  total_matched?: number | null;
  targets?: number | null;
  data_source?: string | null;
  note?: string | null;
  subscriber_only?: boolean | null;
};

const SOURCE_META: { key: keyof MonitorGroups; label: string; icon: string; desc: string }[] = [
  { key: "landschedule", label: "보유토지(토지조서)", icon: "🗂️", desc: "토지조서 자동연동" },
  { key: "excel", label: "업로드 토지", icon: "📄", desc: "Excel 업로드 토지조서" },
  { key: "region", label: "관심 구역", icon: "🗺️", desc: "지도에서 그린 구역" },
];

function formatCurrency(locale: Locale, value: number | null | undefined) {
  if (value == null) return "-";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatText(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  return value;
}

function extractErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return "실시간 조회를 위해 로그인(메인 인증)이 필요합니다.";
    }
    return `요청이 실패했습니다 (HTTP ${error.status}).`;
  }
  if (error instanceof Error) return error.message;
  return "데이터를 불러오지 못했습니다.";
}

// ---- Leaflet CDN 동적로드 (NearbyTransactionsMap과 동일 패턴, 새 의존성 0) ----
let leafletLoading: Promise<void> | null = null;
function loadLeaflet(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.L) return Promise.resolve();
  if (leafletLoading) return leafletLoading;
  leafletLoading = new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-leaflet]')) {
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

export function AuctionMonitorPanel({ locale, canUseLiveApi }: { locale: Locale; canUseLiveApi: boolean }) {
  const queryClient = useQueryClient();

  // ----- 관심대상(watchlist) -----
  const watchlistQuery = useQuery({
    queryKey: ["auction", "watchlist"],
    enabled: canUseLiveApi,
    queryFn: () => apiClient.get<WatchlistResponse>("/auction/watchlist"),
  });

  const watchTargets = useMemo(() => watchlistQuery.data?.items ?? [], [watchlistQuery.data]);
  const sourceCounts = useMemo(() => {
    const c: Record<string, number> = { landschedule: 0, excel: 0, region: 0 };
    for (const t of watchTargets) {
      const s = (t.watch_source ?? "").toLowerCase();
      if (s in c) c[s] += 1;
    }
    return c;
  }, [watchTargets]);

  // ----- 매칭 결과(monitor) -----
  const monitorQuery = useQuery({
    queryKey: ["auction", "monitor"],
    enabled: canUseLiveApi,
    queryFn: () => apiClient.get<MonitorResponse>("/auction/monitor?group_by=source"),
  });

  const runMutation = useMutation({
    mutationFn: () => apiClient.post<MonitorResponse>("/auction/monitor/run", { timeoutMs: 120000 }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["auction", "monitor"] });
      void queryClient.invalidateQueries({ queryKey: ["auction", "watchlist"] });
    },
  });

  // ----- Excel 업로드 -----
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [uploadError, setUploadError] = useState("");
  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return apiClient.post<UploadResponse>("/auction/watchlist/upload", { body: fd, timeoutMs: 120000 });
    },
    onSuccess: (data) => {
      setUploadResult(data);
      setUploadError("");
      void queryClient.invalidateQueries({ queryKey: ["auction", "watchlist"] });
      void queryClient.invalidateQueries({ queryKey: ["auction", "monitor"] });
    },
    onError: (error) => {
      setUploadResult(null);
      setUploadError(extractErrorMessage(error));
    },
  });

  function handleFilePick(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) uploadMutation.mutate(file);
    // 동일 파일 재선택 허용
    e.target.value = "";
  }

  // ----- 관심 구역(regions) + 지도 그리기 -----
  const regionsQuery = useQuery({
    queryKey: ["auction", "regions"],
    enabled: canUseLiveApi,
    queryFn: () => apiClient.get<RegionsResponse>("/auction/regions"),
  });
  const regions = useMemo(() => regionsQuery.data?.items ?? [], [regionsQuery.data]);

  const [regionName, setRegionName] = useState("");
  const [regionError, setRegionError] = useState("");
  const saveRegionMutation = useMutation({
    mutationFn: (payload: { name: string; geojson: RegionGeoJson }) =>
      apiClient.post<Region>("/auction/regions", { body: payload }),
    onSuccess: () => {
      setRegionName("");
      setRegionError("");
      clearDraft();
      void queryClient.invalidateQueries({ queryKey: ["auction", "regions"] });
      void queryClient.invalidateQueries({ queryKey: ["auction", "monitor"] });
    },
    onError: (error) => setRegionError(extractErrorMessage(error)),
  });
  const deleteRegionMutation = useMutation({
    mutationFn: (id: number | string) => apiClient.delete<void>(`/auction/regions/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["auction", "regions"] });
      void queryClient.invalidateQueries({ queryKey: ["auction", "monitor"] });
    },
  });

  // 지도 상태
  const [sdkReady, setSdkReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [drawing, setDrawing] = useState(false);
  const [draftCount, setDraftCount] = useState(0); // 현재 그리는 폴리곤 정점 수

  // 편집 모드 상태(저장 구역 점 드래그 수정)
  const [editing, setEditing] = useState<Region | null>(null);
  const [editPointCount, setEditPointCount] = useState(0);

  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const savedLayerRef = useRef<any>(null); // 저장된 구역 레이어
  const draftMarkersRef = useRef<any[]>([]); // 그리는 중 정점 마커
  const draftLineRef = useRef<any>(null); // 그리는 중 폴리라인
  const draftPointsRef = useRef<[number, number][]>([]); // [lat,lng]
  const drawingRef = useRef(false);

  // 편집 레이어 refs
  const editLayerRef = useRef<any>(null); // 편집용 layerGroup(드래그 마커+폴리곤)
  const editMarkersRef = useRef<any[]>([]); // 드래그 가능 정점 마커
  const editPolygonRef = useRef<any>(null); // 편집 중 폴리곤
  const editPointsRef = useRef<[number, number][]>([]); // [lat,lng]
  const editingRef = useRef<Region | null>(null);

  useEffect(() => {
    drawingRef.current = drawing;
  }, [drawing]);

  useEffect(() => {
    editingRef.current = editing;
  }, [editing]);

  const clearDraft = useCallback(() => {
    const L = window.L;
    if (L && mapRef.current) {
      (draftMarkersRef.current ?? []).forEach((m) => mapRef.current.removeLayer(m));
      if (draftLineRef.current) mapRef.current.removeLayer(draftLineRef.current);
    }
    draftMarkersRef.current = [];
    draftLineRef.current = null;
    draftPointsRef.current = [];
    setDraftCount(0);
  }, [setDraftCount]);

  const clearEdit = useCallback(() => {
    if (editLayerRef.current) editLayerRef.current.clearLayers();
    editMarkersRef.current = [];
    editPolygonRef.current = null;
    editPointsRef.current = [];
    setEditPointCount(0);
  }, [setEditPointCount]);

  // 그리는 중 마지막 정점 1개 취소(undo) — 시각 갱신.
  const undoLastVertex = useCallback(() => {
    const L = window.L;
    if (!L || !mapRef.current) return;
    if (!draftPointsRef.current?.length) return;
    draftPointsRef.current.pop();
    const lastMarker = draftMarkersRef.current.pop();
    if (lastMarker) mapRef.current.removeLayer(lastMarker);
    if (draftLineRef.current) {
      mapRef.current.removeLayer(draftLineRef.current);
      draftLineRef.current = null;
    }
    if (draftPointsRef.current?.length >= 2) {
      draftLineRef.current = L.polyline(draftPointsRef.current, {
        color: "#ef4444",
        weight: 2,
        dashArray: "6",
      }).addTo(mapRef.current);
    }
    setDraftCount(draftPointsRef.current?.length);
  }, [setDraftCount]);

  useEffect(() => {
    let alive = true;
    loadLeaflet()
      .then(() => alive && setSdkReady(true))
      .catch((e) => alive && setMapError(String(e?.message || e)));
    return () => {
      alive = false;
    };
  }, []);

  // Ctrl+Z / ⌘+Z: 그리는 중 마지막 정점 취소(undo). 그리기 모드일 때만 활성, cleanup 필수.
  useEffect(() => {
    if (!drawing) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        undoLastVertex();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [drawing, undoLastVertex]);

  // 지도 초기화 (서울 중심 기본 — 구역은 사용자가 직접 그림)
  useEffect(() => {
    if (!sdkReady || !mapEl.current || mapRef.current) return;
    const L = window.L;
    const map = L.map(mapEl.current, { center: [36.5, 127.8], zoom: 7, scrollWheelZoom: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);
    savedLayerRef.current = L.layerGroup().addTo(map);
    editLayerRef.current = L.layerGroup().addTo(map);

    // 지도 클릭 → 그리는 중이면 정점 추가
    map.on("click", (ev: any) => {
      if (editingRef.current) return; // 편집 중에는 새 정점 추가 금지
      if (!drawingRef.current) return;
      const pt: [number, number] = [ev.latlng.lat, ev.latlng.lng];
      draftPointsRef.current.push(pt);
      const marker = L.circleMarker(pt, {
        radius: 5,
        color: "#fff",
        weight: 2,
        fillColor: "#ef4444",
        fillOpacity: 1,
      }).addTo(map);
      draftMarkersRef.current.push(marker);
      if (draftLineRef.current) map.removeLayer(draftLineRef.current);
      draftLineRef.current = L.polyline(draftPointsRef.current, {
        color: "#ef4444",
        weight: 2,
        dashArray: "6",
      }).addTo(map);
      setDraftCount(draftPointsRef.current?.length);
    });

    mapRef.current = map;
    const sizeTimer = setTimeout(() => map.invalidateSize(), 100);

    // 언마운트 시 지도·리스너·레이어 제거(메모리릭 방지).
    return () => {
      clearTimeout(sizeTimer);
      map.off();
      map.remove();
      mapRef.current = null;
      savedLayerRef.current = null;
      editLayerRef.current = null;
      draftMarkersRef.current = [];
      draftLineRef.current = null;
      editMarkersRef.current = [];
      editPolygonRef.current = null;
    };
  }, [sdkReady]);

  // 구역 bounds로 확대 이동
  const zoomToRegion = useCallback((region: Region) => {
    const L = window.L;
    if (!L || !mapRef.current) return;
    const coords = region.geojson?.coordinates?.[0];
    if (!Array.isArray(coords) || coords.length < 3) return;
    const latlngs = coords.map((c) => [c[1], c[0]] as [number, number]);
    try {
      mapRef.current.fitBounds(L.latLngBounds(latlngs), { padding: [40, 40], maxZoom: 16 });
    } catch {
      /* noop */
    }
  }, []);

  // 저장된 구역 렌더 (편집 중에는 재렌더 생략 — 드래그 상태 보존)
  useEffect(() => {
    if (!sdkReady || !mapRef.current || !window.L || !savedLayerRef.current) return;
    if (editing) return;
    const L = window.L;
    savedLayerRef.current.clearLayers();
    const bounds: [number, number][] = [];
    regions.forEach((r) => {
      const coords = r.geojson?.coordinates?.[0];
      if (!Array.isArray(coords) || coords.length < 3) return;
      // geojson은 [lng,lat] → leaflet은 [lat,lng]
      const latlngs = coords.map((c) => [c[1], c[0]] as [number, number]);
      latlngs.forEach((p) => bounds.push(p));
      const poly = L.polygon(latlngs, {
        color: "#14b8a6",
        weight: 2,
        fillColor: "#14b8a6",
        fillOpacity: 0.12,
      }).addTo(savedLayerRef.current);
      // 폴리곤 클릭 → 해당 구역으로 확대(그리기 중이 아닐 때).
      poly.on("click", (ev: any) => {
        if (drawingRef.current || editingRef.current) return;
        if (ev?.originalEvent) L.DomEvent.stopPropagation(ev.originalEvent);
        zoomToRegion(r);
      });
    });
    if (bounds.length > 1 && !drawingRef.current) {
      try {
        mapRef.current.fitBounds(L.latLngBounds(bounds), { padding: [30, 30], maxZoom: 14 });
      } catch {
        /* noop */
      }
    }
  }, [regions, sdkReady, zoomToRegion, editing]);

  function startDrawing() {
    setRegionError("");
    clearDraft();
    setDrawing(true);
  }

  function finishDrawing() {
    setDrawing(false);
    if (draftPointsRef.current?.length < 3) {
      setRegionError("폴리곤은 최소 3개 정점이 필요합니다. 지도를 더 클릭하세요.");
      return;
    }
    // draft 라인을 닫힌 폴리곤으로 시각화
    const L = window.L;
    if (L && mapRef.current && draftLineRef.current) {
      mapRef.current.removeLayer(draftLineRef.current);
      draftLineRef.current = L.polygon(draftPointsRef.current, {
        color: "#f59e0b",
        weight: 2,
        fillColor: "#f59e0b",
        fillOpacity: 0.15,
      }).addTo(mapRef.current);
    }
  }

  function handleSaveRegion() {
    if (!regionName.trim()) {
      setRegionError("구역 이름을 입력하세요.");
      return;
    }
    const pts = draftPointsRef.current;
    if (pts.length < 3) {
      setRegionError("저장할 폴리곤이 없습니다. 지도에서 구역을 먼저 그리세요(3개 이상 정점).");
      return;
    }
    // leaflet [lat,lng] → geojson [lng,lat], 시작점으로 폴리곤 닫기
    const ring: number[][] = pts.map((p) => [p[1], p[0]]);
    ring.push([pts[0][1], pts[0][0]]);
    saveRegionMutation.mutate({
      name: regionName.trim(),
      geojson: { type: "Polygon", coordinates: [ring] },
    });
  }

  // 편집 중 폴리곤 시각 갱신(드래그 시).
  const refreshEditPolygon = useCallback(() => {
    const L = window.L;
    if (!L || !mapRef.current || !editLayerRef.current) return;
    if (editPolygonRef.current) {
      editLayerRef.current.removeLayer(editPolygonRef.current);
      editPolygonRef.current = null;
    }
    if (editPointsRef.current?.length >= 2) {
      editPolygonRef.current = L.polygon(editPointsRef.current, {
        color: "#f59e0b",
        weight: 2,
        fillColor: "#f59e0b",
        fillOpacity: 0.15,
      }).addTo(editLayerRef.current);
    }
  }, []);

  // 저장 구역 → 편집 모드 진입(각 정점 드래그 마커 + 폴리곤).
  const enterEdit = useCallback(
    (region: Region) => {
      const L = window.L;
      if (!L || !mapRef.current || !editLayerRef.current) return;
      const coords = region.geojson?.coordinates?.[0];
      if (!Array.isArray(coords) || coords.length < 3) return;
      // 그리기 모드 해제·draft 정리
      setDrawing(false);
      clearDraft();
      clearEdit();
      setRegionError("");

      // 닫힘점(마지막=시작) 제거 후 [lat,lng] 정점 배열
      const ring = coords.slice();
      const first = ring[0];
      const last = ring[ring.length - 1];
      if (ring.length > 3 && first && last && first[0] === last[0] && first[1] === last[1]) {
        ring.pop();
      }
      const pts: [number, number][] = ring.map((c) => [c[1], c[0]]);
      editPointsRef.current = pts;

      pts.forEach((pt, idx) => {
        const marker = L.marker(pt, {
          draggable: true,
          icon: L.divIcon({
            className: "",
            html: '<span style="display:block;width:14px;height:14px;border-radius:9999px;background:#f59e0b;border:2px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.3)"></span>',
            iconSize: [14, 14],
            iconAnchor: [7, 7],
          }),
        }).addTo(editLayerRef.current);
        marker.on("drag", (ev: any) => {
          const ll = ev.target.getLatLng();
          editPointsRef.current[idx] = [ll.lat, ll.lng];
          refreshEditPolygon();
        });
        editMarkersRef.current.push(marker);
      });

      refreshEditPolygon();
      setEditPointCount(pts.length);
      setEditing(region);
      setRegionName(region.label ?? "");
      zoomToRegion(region);
    },
    [
      clearDraft,
      clearEdit,
      refreshEditPolygon,
      zoomToRegion,
      setDrawing,
      setEditPointCount,
      setEditing,
      setRegionError,
      setRegionName,
    ],
  );

  const cancelEdit = useCallback(() => {
    clearEdit();
    setEditing(null);
    setRegionName("");
    setRegionError("");
  }, [clearEdit, setEditing, setRegionName, setRegionError]);

  // 편집 저장: PUT 없음 → DELETE 기존 + POST 신규(같은 이름).
  const editSaveMutation = useMutation({
    mutationFn: async (payload: {
      id: number | string;
      name: string;
      geojson: RegionGeoJson;
    }) => {
      await apiClient.delete<void>(`/auction/regions/${payload.id}`);
      return apiClient.post<Region>("/auction/regions", {
        body: { name: payload.name, geojson: payload.geojson },
      });
    },
    onSuccess: () => {
      clearEdit();
      setEditing(null);
      setRegionName("");
      setRegionError("");
      void queryClient.invalidateQueries({ queryKey: ["auction", "regions"] });
      void queryClient.invalidateQueries({ queryKey: ["auction", "monitor"] });
    },
    onError: (error) => setRegionError(extractErrorMessage(error)),
  });

  function handleSaveEdit() {
    if (!editing) return;
    if (!regionName.trim()) {
      setRegionError("구역 이름을 입력하세요.");
      return;
    }
    const pts = editPointsRef.current;
    if (pts.length < 3) {
      setRegionError("폴리곤은 최소 3개 정점이 필요합니다.");
      return;
    }
    // leaflet [lat,lng] → geojson [lng,lat], 시작점으로 닫기
    const ring: number[][] = pts.map((p) => [p[1], p[0]]);
    ring.push([pts[0][1], pts[0][0]]);
    editSaveMutation.mutate({
      id: editing.id,
      name: regionName.trim(),
      geojson: { type: "Polygon", coordinates: [ring] },
    });
  }

  // ---- 렌더 ----
  if (!canUseLiveApi) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-5 text-sm font-semibold text-[var(--text-hint)]">
        경·공매 모니터링은 로그인(메인 인증) 후 이용할 수 있습니다.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 자동모니터링 안내 + 수동실행 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/40 px-4 py-3">
        <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
          📡 관심대상(보유토지·업로드·관심구역)을 정기적으로{" "}
          <strong className="text-[var(--text-primary)]">자동 모니터링</strong>하여 경·공매로 나오는 물건을
          찾아드립니다. 아래에서 즉시 갱신할 수도 있습니다.
        </p>
        <button
          type="button"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="shrink-0 whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white shadow-[var(--shadow-glow)] transition-transform hover:scale-[1.02] active:scale-95 disabled:opacity-50"
        >
          {runMutation.isPending ? "모니터링 실행 중…" : "지금 모니터링 실행"}
        </button>
      </div>
      {runMutation.isError ? (
        <p className="rounded-xl bg-[var(--surface-soft)] px-4 py-2 text-xs font-bold text-[var(--spot)]">
          모니터링 실행 실패: {extractErrorMessage(runMutation.error)}
        </p>
      ) : null}

      {/* ===== 관심대상 등록 3방법 ===== */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* ⓐ 보유토지(토지조서) */}
        <div className="flex flex-col rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/40 p-5">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-lg">🗂️</span>
            <h3 className="text-sm font-black text-[var(--text-primary)]">보유토지 자동연동</h3>
          </div>
          <p className="flex-1 text-xs leading-relaxed text-[var(--text-secondary)]">
            토지조서에 등록한 보유 토지는 별도 등록 없이 자동으로 경·공매 모니터링 대상이 됩니다.
          </p>
          <div className="mt-4 rounded-xl bg-[var(--surface-muted)] px-4 py-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
              현재 모니터링 중
            </p>
            <p className="text-2xl font-black text-[var(--accent-strong)]">
              {watchlistQuery.isLoading ? "…" : `${sourceCounts.landschedule}건`}
            </p>
          </div>
        </div>

        {/* ⓑ Excel 업로드 */}
        <div className="flex flex-col rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/40 p-5">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-lg">📄</span>
            <h3 className="text-sm font-black text-[var(--text-primary)]">토지조서 Excel 업로드</h3>
          </div>
          <p className="flex-1 text-xs leading-relaxed text-[var(--text-secondary)]">
            보유·관심 토지 목록(xlsx·xls·csv)을 업로드하면 PNU/주소 컬럼을 자동 인식하여 모니터링합니다.
            다양한 토지조서 양식을 지원합니다.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            onChange={handleFilePick}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="mt-4 rounded-xl border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-4 py-2.5 text-xs font-bold text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-soft)]/70 disabled:opacity-50"
          >
            {uploadMutation.isPending ? "업로드·파싱 중…" : "파일 선택 (xlsx/xls/csv)"}
          </button>
          {uploadError ? (
            <p className="mt-2 text-xs font-bold text-[var(--spot)]">업로드 실패: {uploadError}</p>
          ) : null}
          {uploadResult ? (
            <div className="mt-3 rounded-xl bg-[var(--surface-muted)] px-4 py-3 text-[11px] leading-relaxed text-[var(--text-secondary)]">
              <p className="font-bold text-[var(--text-primary)]">
                {uploadResult.created ?? 0}건 등록 · {uploadResult.parsed_count ?? 0}건 파싱
                {(uploadResult.skipped_rows ?? 0) > 0
                  ? ` · 미인식 ${uploadResult.skipped_rows}행`
                  : ""}
                {uploadResult.total_rows != null ? ` / 총 ${uploadResult.total_rows}행` : ""}
              </p>
              {uploadResult.detected_columns ? (
                <p className="mt-1">
                  인식 컬럼 — PNU: {formatText(uploadResult.detected_columns.pnu)} / 주소:{" "}
                  {formatText(uploadResult.detected_columns.address)} / 명칭:{" "}
                  {formatText(uploadResult.detected_columns.label)}
                </p>
              ) : null}
              {Array.isArray(uploadResult.examples) && uploadResult.examples?.length ? (
                <p className="mt-1 truncate text-[var(--text-hint)]">
                  예시: {uploadResult.examples
                    .slice(0, 2)
                    .map((ex) => Object.values(ex).filter(Boolean).slice(0, 2).join(" "))
                    .join(" · ")}
                </p>
              ) : null}
              {uploadResult.note ? (
                <p className="mt-1 text-[var(--text-hint)]">{uploadResult.note}</p>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* ⓒ 등록 현황 요약 */}
        <div className="flex flex-col rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/40 p-5">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-lg">📊</span>
            <h3 className="text-sm font-black text-[var(--text-primary)]">관심대상 현황</h3>
          </div>
          {watchlistQuery.isError ? (
            <p className="text-xs font-bold text-[var(--spot)]">
              {extractErrorMessage(watchlistQuery.error)}
            </p>
          ) : (
            <ul className="flex-1 space-y-2 text-xs">
              {SOURCE_META.map((m) => (
                <li
                  key={m.key}
                  className="flex items-center justify-between rounded-lg bg-[var(--surface-muted)] px-3 py-2"
                >
                  <span className="font-bold text-[var(--text-secondary)]">
                    {m.icon} {m.label}
                  </span>
                  <span className="font-black text-[var(--text-primary)]">
                    {watchlistQuery.isLoading ? "…" : `${sourceCounts[m.key] ?? 0}건`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {watchlistQuery.data?.note ? (
            <p className="mt-2 text-[10px] text-[var(--text-hint)]">{watchlistQuery.data.note}</p>
          ) : null}
        </div>
      </div>

      {/* ===== 지도 구획 그리기 ===== */}
      <div className="rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/40 p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-black text-[var(--text-primary)]">
              <span>🗺️</span> 지도에서 관심 구역 그리기
            </h3>
            <p className="mt-0.5 text-[11px] text-[var(--text-hint)]">
              {editing
                ? `편집 모드 — "${formatText(editing.label)}" 구역의 정점(${editPointCount}개)을 드래그해 수정한 뒤 "수정 저장"을 누르세요.`
                : drawing
                  ? `그리기 모드 — 지도를 클릭해 경계를 찍으세요 (정점 ${draftCount}개). Ctrl+Z(⌘+Z)로 마지막 정점 취소. 3개 이상 찍고 "구역 완료".`
                  : "‘구역 그리기 시작’ → 지도 클릭으로 경계를 찍고(Ctrl+Z 취소) ‘구역 완료’ → 이름 입력 후 저장. 저장 구역 클릭 시 확대·편집할 수 있습니다."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {editing ? (
              <>
                <span className="inline-flex items-center rounded-xl bg-[#f59e0b]/15 px-3 py-2 text-xs font-black text-[#f59e0b]">
                  편집 중 ({editPointCount})
                </span>
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  편집 취소
                </button>
              </>
            ) : !drawing ? (
              <button
                type="button"
                onClick={startDrawing}
                disabled={!sdkReady}
                className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-bold text-white disabled:opacity-50"
              >
                구역 그리기 시작
              </button>
            ) : (
              <button
                type="button"
                onClick={finishDrawing}
                className="rounded-xl bg-[#f59e0b] px-4 py-2 text-xs font-black text-white"
              >
                구역 완료 ({draftCount})
              </button>
            )}
            {!editing ? (
              <button
                type="button"
                onClick={() => {
                  clearDraft();
                  setDrawing(false);
                  setRegionError("");
                }}
                className="rounded-xl border border-[var(--line-strong)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                지우기
              </button>
            ) : null}
          </div>
        </div>

        <div className="relative">
          <div
            ref={mapEl}
            className="z-0 w-full overflow-hidden rounded-xl border border-[var(--line-strong)]"
            style={{ height: 400 }}
          />
          {!sdkReady && !mapError ? (
            <div className="absolute inset-0 z-[400] flex items-center justify-center rounded-xl bg-black/40 backdrop-blur-sm">
              <span className="flex items-center gap-2 text-sm font-bold text-white">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                지도 로딩…
              </span>
            </div>
          ) : null}
          {mapError ? (
            <div className="absolute inset-0 z-[400] flex items-center justify-center rounded-xl bg-[var(--surface-muted)]">
              <p className="text-sm text-[var(--text-secondary)]">지도 표시 실패: {mapError}</p>
            </div>
          ) : null}
        </div>

        {/* 저장 폼 */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            value={regionName}
            onChange={(e) => setRegionName(e.target.value)}
            placeholder="구역 이름 (예: 강남 재개발 관심구역)"
            className="w-60 max-w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
          />
          {editing ? (
            <button
              type="button"
              onClick={handleSaveEdit}
              disabled={editSaveMutation.isPending || editPointCount < 3}
              className="rounded-xl border border-[#f59e0b]/50 bg-[#f59e0b]/15 px-4 py-2 text-sm font-bold text-[#f59e0b] transition-colors hover:bg-[#f59e0b]/25 disabled:opacity-50"
            >
              {editSaveMutation.isPending ? "수정 저장 중…" : "수정 저장"}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSaveRegion}
              disabled={saveRegionMutation.isPending || draftCount < 3}
              className="rounded-xl border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-4 py-2 text-sm font-bold text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-soft)]/70 disabled:opacity-50"
            >
              {saveRegionMutation.isPending ? "저장 중…" : "구역 저장"}
            </button>
          )}
          {regionError ? (
            <span className="text-xs font-bold text-[var(--spot)]">{regionError}</span>
          ) : null}
        </div>

        {/* 저장된 구역 목록 */}
        {regionsQuery.isError ? (
          <p className="mt-3 text-xs font-bold text-[var(--spot)]">
            {extractErrorMessage(regionsQuery.error)}
          </p>
        ) : regions.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {regions.map((r) => (
              <span
                key={r.id}
                className={`inline-flex items-center gap-2 rounded-full border bg-[var(--surface-soft)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] ${
                  editing?.id === r.id
                    ? "border-[#f59e0b]/60"
                    : "border-[var(--line-strong)]"
                }`}
              >
                <button
                  type="button"
                  aria-label={`${r.label ?? "구역"} 확대`}
                  onClick={() => zoomToRegion(r)}
                  className="hover:text-[var(--accent-strong)]"
                >
                  🗺️ {formatText(r.label)}
                </button>
                <button
                  type="button"
                  aria-label={`${r.label ?? "구역"} 편집`}
                  onClick={() => enterEdit(r)}
                  className="text-[var(--text-hint)] hover:text-[#f59e0b]"
                >
                  편집
                </button>
                <button
                  type="button"
                  aria-label={`${r.label ?? "구역"} 삭제`}
                  onClick={() => deleteRegionMutation.mutate(r.id)}
                  className="text-[var(--text-hint)] hover:text-[var(--spot)]"
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-xs text-[var(--text-hint)]">저장된 관심 구역이 없습니다.</p>
        )}
      </div>

      {/* ===== 매칭 결과 ===== */}
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-black tracking-tight text-[var(--text-primary)]">
            관심대상별 매칭 결과
          </h2>
          {monitorQuery.data?.total_matched != null ? (
            <span className="rounded-full bg-[var(--accent-strong)]/10 px-3 py-1 text-xs font-bold text-[var(--accent-strong)]">
              총 {monitorQuery.data.total_matched}건 매칭
            </span>
          ) : null}
        </div>

        {monitorQuery.data?.subscriber_only ? (
          <div className="rounded-2xl border border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10 px-5 py-4">
            <p className="text-sm font-black text-[var(--text-primary)]">🔒 구독자 전용 기능</p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              공·경매 모니터링은 구독자만 이용할 수 있습니다. 구독 후 보유토지·관심물건을 지속
              모니터링하고 AI 분석(LLM 사용량에 따라 과금)을 활용하세요.
            </p>
          </div>
        ) : monitorQuery.data?.note ? (
          <p className="rounded-xl bg-[var(--surface-soft)] px-4 py-3 text-xs font-medium text-[var(--text-hint)]">
            {monitorQuery.data.note}
          </p>
        ) : null}

        {monitorQuery.isLoading ? (
          <SkeletonLoader count={3} itemClassName="h-24 rounded-2xl" />
        ) : monitorQuery.isError ? (
          <WorkspaceQueryErrorCard
            title="매칭 결과 로드 실패"
            description="관심대상과 경·공매 물건의 매칭 결과를 불러오지 못했습니다."
            message={extractErrorMessage(monitorQuery.error)}
            actionLabel="다시 시도"
            onRetry={() => void monitorQuery.refetch()}
          />
        ) : monitorQuery.data ? (
          <div className="space-y-5">
            {SOURCE_META.map((m) => {
              const matches = monitorQuery.data?.groups?.[m.key] ?? [];
              return (
                <div
                  key={m.key}
                  className="rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/40 p-5"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="flex items-center gap-2 text-sm font-black text-[var(--text-primary)]">
                      <span>{m.icon}</span> {m.label}
                      <span className="text-[10px] font-bold text-[var(--text-hint)]">{m.desc}</span>
                    </p>
                    <span className="rounded-full bg-[var(--surface-muted)] px-3 py-1 text-xs font-bold text-[var(--text-secondary)]">
                      {matches.length}건
                    </span>
                  </div>
                  {matches.length ? (
                    <MatchTable matches={matches} locale={locale} />
                  ) : (
                    <p className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--surface-muted)]/40 px-4 py-6 text-center text-xs font-bold text-[var(--text-hint)]">
                      해당 조건 매칭 물건 없음 (자동 모니터링 중)
                    </p>
                  )}
                </div>
              );
            })}
            {monitorQuery.data.data_source ? (
              <p className="text-right text-[10px] text-[var(--text-hint)]">
                출처: {monitorQuery.data.data_source}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function MatchTable({ matches, locale }: { matches: MonitorMatch[]; locale: Locale }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--line)] text-left text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
            <th className="py-3 pr-4">관심대상</th>
            <th className="py-3 pr-4">주소</th>
            <th className="py-3 pr-4">용도</th>
            <th className="py-3 pr-4 text-right">감정가</th>
            <th className="py-3 pr-4 text-right">최저입찰가</th>
            <th className="py-3 pr-4 text-right">유찰</th>
            <th className="py-3 pr-4 text-right">낙찰가능가(추정)</th>
            <th className="py-3 pr-4">상태</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((item, idx) => (
            <tr
              key={`${item.watch_target_id ?? "t"}-${idx}`}
              className="border-b border-[var(--line)]/60"
            >
              <td className="py-3 pr-4 font-bold text-[var(--accent-strong)]">
                {formatText(item.watch_label)}
              </td>
              <td className="max-w-[220px] truncate py-3 pr-4 font-bold text-[var(--text-primary)]">
                {formatText(item.address)}
              </td>
              <td className="py-3 pr-4 text-[var(--text-secondary)]">
                {formatText(item.usage ?? item.kind)}
              </td>
              <td className="py-3 pr-4 text-right text-[var(--text-primary)]">
                {formatCurrency(locale, item.appraisal_price)}
              </td>
              <td className="py-3 pr-4 text-right text-[var(--text-primary)]">
                {item.min_bid_price == null ? "비공개" : formatCurrency(locale, item.min_bid_price)}
              </td>
              <td className="py-3 pr-4 text-right text-[var(--text-secondary)]">
                {item.fail_count == null ? "-" : `${item.fail_count}회`}
              </td>
              <td className="py-3 pr-4 text-right font-bold text-[var(--accent-strong)]">
                {item.est_win?.est_win_mid == null
                  ? "-"
                  : formatCurrency(locale, item.est_win.est_win_mid)}
              </td>
              <td className="py-3 pr-4 text-[var(--text-secondary)]">{formatText(item.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
