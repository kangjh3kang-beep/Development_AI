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
import { SATONG_POPUP_YIELD } from "@/lib/satong-map-z";
import { KakaoRoadview } from "@/components/map/KakaoRoadview";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { MARKET_RENT_TYPES, MARKET_TRADE_TYPES, resolveMapCenter } from "@/lib/satong-map-layers";
import { selectLocatedGroups } from "@/lib/market/comparable-sample";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { marketRadiusRequest } from "@/lib/market/market-radius";

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
  /** 반경 필터가 실제로 적용됐는지(중심좌표+radius_m 확보 시 true). 옵셔널(배선 진행 중). */
  radius_applied?: boolean;
  /** 반경 밖으로 걸러진 그룹 수. 옵셔널(배선 진행 중) — 있을 때만 라벨에 부연. */
  radius_filtered_out_count?: number;
  /** ★표본 감쇠 사슬 — 원본 몇 곳이 어디서 깎여 화면의 N 이 됐는지(백엔드 SSOT).
   *  종전엔 이 라벨이 `radius_filtered_out_count` **하나만** 말했는데, 라이브 실측에서
   *  그건 306곳이고 **정작 가장 큰 사전컷 1,761곳은 아무 데도 없었다**. */
  sample_attenuation?: {
    source_group_count: number;
    shown_group_count: number;
    dropped_total: number;
    dropped_pct: number;
    headline: string;
    reconciles: boolean;
    stages: { key: string; label: string; dropped: number; reason: string }[];
    /** ★차감이 **아니다** — 좌표를 못 얻어 반경 판정을 못 했을 뿐 표시에는 남는다.
     *  종전엔 이걸 제외로 세어 "제외됐다"는 거짓을 말했고 사슬도 깨졌다(제천 실측). */
    unlocated_group_count?: number;
    unlocated_note?: string | null;
    in_radius_group_count?: number;
  } | null;
  lawd_cd: string;
  months: string[];
  categories: Record<string, Category>;
  /** AI 시세(AVM) 요약 — 백엔드(nearby_map_service._compute_avm_summary)가 apt_trade
   *  그룹(반경 필터 적용 후)으로 계산해 싣는다(SSOT). 비교 표본 0건이면 null(무날조). */
  avm?: {
    estimated_price: number; // 원(84㎡ 환산)
    price_per_sqm: number;   // 원/㎡
    confidence_score: number;
    comparable_count: number;
    sample_count: number;     // 신뢰도(CV) 산출에 실제 사용된 개별 거래 표본 수
    price_cv_percent: number; // 표본 가격 변동계수(CV, %) — 낮을수록 가격이 고르게 형성됨
    /** ★비교 **거래** 건수의 명시적 별칭(`comparable_count`가 이름과 달리 거래 수였다). */
    comparable_deal_count?: number;
    comparable_group_count?: number;
    /** ★이 시세가 무엇으로부터 나왔는가 — 반경 적용 여부·통과 그룹 수. */
    basis?: {
      radius_applied: boolean;
      radius_m: number | null;
      in_radius_group_count: number | null;
      scope: string;
    };
  } | null;
  /**
   * ★AVM **신뢰성 단서**. AVM 유무와 **무관하게** 붙을 수 있다 — 가장 위험한 단서
   *   ("반경 필터 미적용")는 오히려 **AVM이 있을 때** 붙는다. 이걸 소비하지 않으면 화면이
   *   "실거래가 없어 시세를 추정할 수 없습니다"라고 말하면서 같은 화면에서 거래 수십 건을
   *   보여주는 자기모순이 난다(날조된 숫자를 날조된 설명으로 바꾸는 것).
   */
  avm_caveat?: string | null;
  /** @deprecated `avm_caveat`과 동일 값(한 릴리스 호환). */
  avm_unavailable_reason?: string | null;
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

// ★색상 SSOT 통합(분석품질 레인G): 종전 이 파일의 로컬 TRADE_TYPES와 SatongMultiMap의
//   MARKET_TYPE_COLORS가 같은 6색을 각자 하드코딩했다 — lib/satong-map-layers.ts로 승격.
// ★RENT_TYPES도 SSOT(MARKET_RENT_TYPES) 참조로 통일(R1 후속) — 이 파일의 slice(0,4)가
//   "정답 기준선"이었으나, SatongMapShell 경로가 별도로 필터링 없이 6종을 요청하는
//   비대칭이 있었다. 이제 두 컴포넌트가 같은 배열을 공유해 이중 정의 자체를 제거한다.
const TRADE_TYPES = MARKET_TRADE_TYPES;
const RENT_TYPES = MARKET_RENT_TYPES;
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
  // 선택 위치 로드뷰(카카오 SDK, 백엔드 불요) — 접힘 기본값(additive), focusTarget 확보 시에만 노출.
  const [showRoadview, setShowRoadview] = useState(false);
  // 반경 선택(500m/1km/3km) — 요청 radius_m 변경 시 재조회. 기본값은 기존 하드코딩 동일(1000m).
  const [radiusM, setRadiusM] = useState(1000);

  const onPayloadRef = useRef(onPayload);
  const onLoadingRef = useRef(onLoading);
  onPayloadRef.current = onPayload;
  onLoadingRef.current = onLoading;

  // 반경 칩(500m/1km/3km) 연타 시 요청이 중첩될 수 있다 — 느린 선행 응답이 나중에 도착해
  // 최신 반경 결과를 덮는 레이스를 시퀀스 가드로 차단(마지막 요청만 반영). (R1 P3)
  const fetchSeqRef = useRef(0);

  const fetchData = useCallback(async () => {
    if (!address) return;
    const seq = ++fetchSeqRef.current;
    setLoading(true);
    onLoadingRef.current?.(true);
    setError("");
    try {
      const res = await apiClient.post<NearbyMapPayload>("/zoning/nearby-map", {
        // ★요청 조립을 **공용 함수**로 통일한다(2026-08-23). 종전엔 여기서 손으로
        //   `radius_m` 만 실었고, 형제(사통맵)는 `marketRadiusRequest` 를 썼다 — 같은
        //   엔드포인트에 **조립이 두 벌**이었다.
        //   ★지금은 동작이 같다(이 화면의 반경은 항상 숫자라 수동 모드이고, 백엔드
        //     `auto_expand_radius` 기본값도 False 다). 그래서 이건 **동작 변경이 아니라
        //     발산 차단**이다 — 자동확대 정책이 바뀌는 날 두 화면이 갈리지 않는다.
        body: { address, pnu, ...marketRadiusRequest(radiusM), months: 3 },
        useMock: false,
        timeoutMs: 90000,
      });
      if (seq !== fetchSeqRef.current) return; // stale 응답 — 이후 요청이 이미 발화됨
      setPayload(res);
      onPayloadRef.current?.(res);
    } catch (e: unknown) {
      if (seq !== fetchSeqRef.current) return;
      // 원시 예외(TypeError: Failed to fetch 등)를 화면에 그대로 노출하지 않는다
      //   (PopulationDensityMap의 관례 미러 — 정직하되 사용자 대면 텍스트는 정규화).
      const message = e instanceof ApiClientError
        ? ((e.payload as { detail?: string; message?: string } | null)?.detail
          || (e.payload as { detail?: string; message?: string } | null)?.message
          || e.message)
        : "주변 실거래 조회에 실패했습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요.";
      setError(message);
      setPayload(null);
      onPayloadRef.current?.(null);
    } finally {
      if (seq === fetchSeqRef.current) {
        setLoading(false);
        onLoadingRef.current?.(false);
      }
    }
  }, [address, pnu, radiusM]);

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
    setShowRoadview(false);
    // ★분양 결과도 반드시 비운다 — 안 비우면 **직전 주소의 분양 단지가 새 주소 화면에 남는다**.
    //   위 조회 가드가 `presale === null` 일 때만 재조회하므로, 한 번 채워지면 주소가 바뀌어도
    //   다시는 조회되지 않았다(런타임 실측: A→B 전환 시 /presale/nearby 호출 1회, 마커·배지 모두
    //   A 의 것). 이 컴포넌트는 `key` 없이 마운트가 유지되는 소비처가 있어 실제로 재현된다
    //   (MarketInsightsWorkspaceClient · SiteAnalysisDetail).
    setPresale(null);
    setPresaleLoading(false);
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
    // ★단일유형 선택 UI(이 컴포넌트의 칩 토글)는 그대로 유지 — 항상 1개 유형만 배열로 감싸
    //   SatongMultiMap의 다중유형 렌더 계약(types: string[])에 맞춘다(회귀 없음).
    () => ({
      kind,
      types: [type],
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

  // 반경 라벨 — 응답의 radius_m(요청→응답 에코, 백엔드가 실제 필터에 사용)을 우선하고,
  //   응답 전이면 현재 요청 중인 radiusM으로 폴백(실값 연동).
  //   radius_applied(옵셔널·배선 진행 중)는 그 radius_m이 실제로 필터에 쓰였는지 여부(boolean) —
  //   false면 중심좌표 미확보로 필터가 적용되지 않았다는 뜻이라 정직하게 부연한다.
  const radiusVal = payload?.radius_m ?? radiusM;
  const radiusLabel = radiusVal >= 1000 ? `${(radiusVal / 1000).toLocaleString()}km` : `${radiusVal}m`;
  const radiusNotApplied = payload?.radius_applied === false;

  return (
    <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-base font-bold text-[var(--text-primary)]">
            <span className="text-[var(--accent-strong)]">◉</span> 주변 실거래 지도
          </h3>
          <p className="mt-0.5 text-[11px] text-[var(--text-hint)]">
            {payload?.center?.address || address} 중심 · 반경 {radiusLabel}
            {radiusNotApplied ? "(미적용 — 좌표 미확보)" : ""} · 최근 {payload?.months?.length || 3}개월
            {" · 마커 클릭 시 상세"}
          </p>
          {/* ★D9 — 감쇠 사슬을 한 줄로. 종전엔 반경 초과 한 갈래만 말해, 실측에서
              **가장 크게 깎인 사전컷(1,761곳)** 이 화면 어디에도 없었다. */}
          {payload?.sample_attenuation && payload.sample_attenuation.dropped_total > 0 ? (
            <p
              className="mt-1 text-[11px] text-[var(--text-secondary)]"
              title={payload.sample_attenuation.stages
                .filter((st) => st.dropped > 0)
                .map((st) => `${st.label} ${st.dropped.toLocaleString()}곳 — ${st.reason}`)
                .join("\n")}
              data-testid="sample-attenuation-headline"
            >
              {payload.sample_attenuation.headline}
              {!payload.sample_attenuation.reconciles ? " (계기 불일치 — 사슬은 참고용)" : ""}
              {payload.sample_attenuation.unlocated_note ? (
                <span className="block text-[var(--text-hint)]">
                  {payload.sample_attenuation.unlocated_note.replace(/\*\*/g, "")}
                </span>
              ) : null}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex overflow-hidden rounded-xl border border-[var(--line-strong)]">
            {([500, 1000, 3000] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRadiusM(r)}
                aria-pressed={radiusM === r}
                className={`px-3 py-1.5 text-xs font-bold transition-colors ${
                  radiusM === r
                    ? "bg-[var(--accent-strong)] text-white"
                    : "bg-[var(--surface-muted)] text-[var(--text-secondary)]"
                }`}
              >
                {r >= 1000 ? `${r / 1000}km` : `${r}m`}
              </button>
            ))}
          </div>
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
          // ★W1-b — 이 칩은 바로 위 "반경 N" 헤더 아래에 놓인다. 종전엔 `cat.count`(= 반경밖
          //   단정 불가분과 위치 미확인분을 **포함한** 혼합 합계)를 그대로 찍어, 헤더의 반경
          //   주장과 결합해 "반경 안에 N건"으로 읽혔다. 집계 코드가 아니라 **카운트 표시**라
          //   가격 누산 금지 규칙에도 안 걸리는 종류의 오염이다.
          const cat = payload?.categories?.[`${item.key}_${kind}`];
          const chipBasis = selectLocatedGroups(cat as never).basis;
          const count = chipBasis.locatedCount;
          // ★W1-b 리뷰(M-4) — 칩은 위치확인분만 세는데 **지도 마커는 개략 좌표분도 찍는다**
          //   (마커는 "좌표가 있으면 찍는다"가 맞다 — 기준이 다르다). 그대로 두면 "토지 0" 칩
          //   아래에 토지 마커가 여러 개 보이는 모순이 되고, 설명이 없으면 사용자는 둘 중
          //   무엇이 틀렸는지 알 수 없다. **내 변경이 새로 만든 불일치**이므로 여기서 밝힌다.
          const approxOnMap = chipBasis.approximateCount;
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
              {item.label}
              <span className="opacity-70">{count}</span>
              {approxOnMap > 0 && (
                <span className="opacity-60" title="위치가 동 단위까지만 확인돼 집계에서 뺐지만, 지도에는 개략 위치로 표시됩니다">
                  (개략 {approxOnMap})
                </span>
              )}
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

        {/* ★양보 계약 — **시각만 양보**한다(흐려지되 계속 막는다).
            겹침은 실재한다: `fetchData` 는 `setLoading(true)` 만 하고 payload 를 비우지 않아
            **이전 마커와 열린 팝업이 그대로 살아 있고**, 재조회 타임아웃이 90초라 그동안
            이 스크림이 팝업을 덮는다(반경 칩 500m/1km/3km · '분양 겹쳐보기' 토글로 재현).
            그건 #676 이 고치려던 바로 그 증상이다.
            ★종전엔 면제였다. "차단이 목적이라 감쇄하면 클릭이 되살아난다"는 이유였는데,
              그건 계약이 opacity 와 pointer-events 를 **한 규칙에 묶어** 이분법만 준 탓이다.
              `passive-visual` 을 만들어 끊었다 — 흐려져서 팝업이 읽히고, 클릭은 계속 막힌다.
            ★대가(정직) — 두 가지다. ①스크림 안의 "수집 중…" 문구도 함께 흐려진다.
              ②`pointer-events` 는 그대로 두므로 **팝업을 읽을 수는 있어도 만질 수는 없다** —
              팝업의 닫기 버튼·링크도 재조회가 끝날 때까지(최대 90초) 눌리지 않는다.
              종전(불투명 스크림이 팝업을 완전히 가림)보다 나아진 것이지 겹침이 사라진 것은
              아니다. 둘 다 팝업이 열려 있는 동안만이고, 조회가 끝나면 스크림 자체가 사라진다. */}
        {(loading || presaleLoading) && (
          <div
            {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveVisualValue }}
            className="absolute inset-0 z-[400] flex items-center justify-center rounded-xl bg-black/40 backdrop-blur-sm"
          >
            <div className="flex items-center gap-2 text-sm font-bold text-white">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              {presaleLoading ? "분양 단지 수집·지오코딩 중…" : "주변 실거래 수집·지오코딩 중…"}
            </div>
          </div>
        )}

        {/* ★양보 계약 — **면제**(SATONG_POPUP_YIELD.exemptReasons: blocking-error).
            ① 안에 '다시 시도' 버튼이 있어 pointer-events:none 을 걸면 복구 수단이 죽는다.
            ② 오류 경로는 위 `catch` 에서 `setPayload(null)` 이라 마커가 지워지고 팝업도 닫힌다
               — 애초에 팝업과 공존하지 않는다(코드 판독. 라이브 재확인은 안 했다).
            시각만 양보(`passive-visual`)로 낮추지 않는 이유는 ①이다(흐린 오류 패널의 버튼을
            누르게 만드는 것보다, 팝업과 공존하지 않는다는 ②에 기대는 편이 낫다). */}
        {error && !loading && (
          <div
            {...{ [SATONG_POPUP_YIELD.exemptAttr]: "blocking-error" }}
            className="absolute inset-0 z-[400] flex flex-col items-center justify-center gap-2 rounded-xl bg-[var(--surface-muted)]"
          >
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

        {/* ★양보 계약 — 사용자가 연 것이 아닌 **상시 고지 리본**이라 팝업을 읽는 동안 물러난다.
            ★정직: 지금 이 배너와 팝업이 함께 뜨는 경로는 **찾지 못했다**. 조건 `!focusTarget`
              은 실거래 마커 렌더의 조기반환 조건과 같고(center 미확보), 분양 조회도 center 가
              없으면 시작 자체를 안 한다. 그래도 양보 표시를 둔다 — 조건 하나만 바뀌어도
              되살아나는 자리이고, 물러나서 잃는 것이 없기 때문이다(비용 0의 예방).
            (종전 주석은 "직전 주소에서 남은 분양 마커" 경로를 근거로 댔는데, 그건 이 커밋이
             고친 **버그**였다. 버그를 근거로 삼은 주석은 버그가 사라지면 거짓이 된다.) */}
        {payload && !loading && !focusTarget && fallbackFailed && (
          <div
            {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveValue }}
            className="absolute top-3 left-1/2 z-[400] flex max-w-[92%] -translate-x-1/2 items-center gap-2 rounded-xl border border-[var(--status-warning)]/40 bg-[color-mix(in_srgb,var(--status-warning)_15%,transparent)] px-4 py-2 text-center text-xs font-bold text-[var(--status-warning)] backdrop-blur">
            <AlertTriangle className="size-4 shrink-0" aria-hidden />
            위치 확인 불가 — 선택 위치의 좌표를 확인하지 못해 지도가 기본 위치로 표시 중입니다. 아래 실거래 목록·건수는 정상 조회 결과입니다.
          </div>
        )}

        {/* ★양보 계약 — 상시 고지 리본. 하단 중앙이라 아래쪽 마커의 팝업과 정면으로 겹친다.
            (실거래 마커는 fetch_failed 면 안 그려지지만 분양 마커는 독립 이펙트라 뜬다.) */}
        {payload && !loading && payload.fetch_failed && (
          <div
            {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveValue }}
            className="absolute bottom-3 left-1/2 z-[400] flex max-w-[92%] -translate-x-1/2 items-center gap-2 rounded-xl border border-[var(--status-warning)]/40 bg-[color-mix(in_srgb,var(--status-warning)_15%,transparent)] px-4 py-2 text-center text-xs font-bold text-[var(--status-warning)] backdrop-blur">
            <AlertTriangle className="size-4 shrink-0" aria-hidden /> {payload.note || "국토부 실거래 공공데이터가 일시적으로 응답하지 않습니다. 거래가 없는 것이 아니라 조회 실패입니다."}
          </div>
        )}

        {payload && !loading && !payload.fetch_failed && activeCategory && activeCategory.groups?.length === 0 && (
          <div
            /* ★양보 계약 — 상시 고지 pill. 선택 유형에 거래가 없어도 중심 마커·분양 마커의
               팝업은 열리므로 하단 중앙에서 겹칠 수 있다. */
            {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveValue }}
            className="absolute bottom-3 left-1/2 z-[400] -translate-x-1/2 rounded-full bg-black/60 px-4 py-1.5 text-xs font-bold text-white"
          >
            해당 유형 최근 거래 없음
          </div>
        )}

        {showPresale && !presaleLoading && presale && presale.length === 0 && (
          <div
            /* ★양보 계약 — 상시 고지 pill. 실거래 마커 팝업과 하단에서 겹칠 수 있다. */
            {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveValue }}
            className="absolute bottom-12 left-1/2 z-[400] -translate-x-1/2 rounded-full bg-[#f59e0b]/80 px-4 py-1.5 text-xs font-bold text-white"
          >
            반경 내 분양 단지 없음 또는 청약홈 연동 필요
          </div>
        )}
      </div>

      {focusTarget && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowRoadview((value) => !value)}
            aria-expanded={showRoadview}
            className="flex items-center gap-1.5 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-1.5 text-xs font-bold text-[var(--text-secondary)] transition-colors hover:border-[var(--accent-strong)]"
          >
            <span className="text-[var(--accent-strong)]">◉</span>
            {showRoadview ? "선택 위치 로드뷰 접기" : "선택 위치 로드뷰 보기"}
          </button>
          {showRoadview && (
            <div className="mt-2">
              <KakaoRoadview lat={focusTarget.lat} lon={focusTarget.lon} height={220} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default NearbyTransactionsMap;
