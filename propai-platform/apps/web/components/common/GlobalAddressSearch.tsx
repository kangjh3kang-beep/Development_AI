"use client";

/**
 * 글로벌 주소 검색 컴포넌트 — 단일/다필지 입력 지원.
 *
 * 카카오 주소 검색 API로 주소를 입력하면:
 * 1. PNU 자동 추출 (VWORLD PARCEL 지오코딩)
 * 2. ProjectContextStore에 저장 (Single Source of Truth)
 * 3. 전체 모듈에 자동 반영 (Once-and-Done Input)
 *
 * UX 원칙:
 * - Single Source of Truth (NN/G EAS Framework)
 * - Once-and-Done Input (Chrome 연구: 25% 완료율 향상)
 * - Progressive Disclosure (Jakob Nielsen, 1995)
 */

import { useCallback, useMemo, useRef, useState } from "react";
import { KakaoAddressSearch, type KakaoAddressResult } from "@/components/ui/KakaoAddressSearch";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient, apiV1BaseUrl } from "@/lib/api-client";
import { LandShareModal } from "@/components/operations/LandShareModal";
import { dynamicMap, MapShell } from "@/components/common/MapShell";
import type { ParcelAtPointResult } from "@/components/map/ParcelPickerMap";

// 지도 클릭 필지 선택 컴포넌트 — SSR 없이 동적 로드(Leaflet은 window 필요)
const ParcelPickerMapDynamic = dynamicMap(
  () => import("@/components/map/ParcelPickerMap"),
  { pick: "ParcelPickerMap", height: 360, loadingMessage: "필지 선택 지도 로딩…" },
);

// 행 불변 식별자 — 객체 spread({...a})로 보존되므로 참조 교체에 영향받지 않는 안정 매칭 키.
let _uidSeq = 0;
function newUid(): string {
  _uidSeq += 1;
  return `p${_uidSeq}_${Math.floor(Math.random() * 1e6)}`;
}

export interface AddressEntry {
  __uid?: string; // 행 불변 식별자(토지정보 보강 매칭용)
  fullAddress: string;
  jibunAddress: string;
  roadAddress: string;
  sido: string;
  sigungu: string;
  bname: string;
  zonecode: string;
  bcode: string; // 법정동 코드 (10자리) — PNU 구성에 사용
  areaSqm?: number; // 면적 (m²) — API에서 자동 반영
  areaPyeong?: number; // 면적 (평) — 자동 환산
  // ── 필지별 토지정보(/zoning/parcels-info 일괄 보강) — 등록된 모든 필지가 갖는다 ──
  pnu?: string; // PNU(19자리)
  zoneCode?: string; // 용도지역
  bcrPct?: number; // 건폐율 상한(%)
  farPct?: number; // 용적률 상한(%)
  jimok?: string; // 지목(형질)
  officialPrice?: number; // 개별공시지가(원/㎡)
  // ── 집합건물(공동주택·빌라) 플래그 — 호실/대지지분 안내용 ──
  isAggregate?: boolean;
  buildingName?: string;
  mainPurpose?: string;
  unitCount?: number;
  infoStatus?: "ok" | "ambiguous" | "failed"; // 토지정보 보강 결과
}

/** 종합 토지분석 결과 요약 — onAnalyzed 콜백으로 전달(store 비기록 모드에서도 면적 자동채움 등 유지) */
export interface AddressAnalysisSummary {
  address: string;
  pnu: string | null;
  landAreaSqm: number | null;
  zoneCode: string | null;
  effectiveBcr: number | null;
  effectiveFar: number | null;
  dataSource: string | null;
}

interface GlobalAddressSearchProps {
  /** 단일 필지만 허용 */
  single?: boolean;
  /** 주소 변경 시 콜백 */
  onChange?: (addresses: AddressEntry[]) => void;
  /** 추가 CSS */
  className?: string;
  /** placeholder */
  placeholder?: string;
  /** 비활성화 */
  disabled?: boolean;
  /** 초기 주소 (스토어에서 가져온 값 사전 표시) */
  initialAddress?: string;
  /**
   * WP-D: ProjectContextStore(SSOT) 기록 여부 — 기본 true(기존 동작 불변).
   * false면 store에 일절 기록하지 않고 onChange/onAnalyzed 콜백으로만 데이터를 전달한다
   * (활성 프로젝트와 무관한 검색이 updateSiteAnalysis→withSnap 스냅샷을 오염시키는 사슬 차단).
   */
  writeToContext?: boolean;
  /** 종합 토지분석 도착 시 콜백 — writeToContext=false 소비자(PreCheck 등)의 면적 자동채움용 */
  onAnalyzed?: (analysis: AddressAnalysisSummary) => void;
}

export function GlobalAddressSearch({
  single = false,
  onChange,
  className = "",
  placeholder = "주소를 검색하세요",
  disabled = false,
  initialAddress,
  writeToContext = true,
  onAnalyzed,
}: GlobalAddressSearchProps) {
  const [addresses, setAddresses] = useState<AddressEntry[]>(() => {
    if (initialAddress) {
      return [{ __uid: newUid(), fullAddress: initialAddress, jibunAddress: "", roadAddress: "", sido: "", sigungu: "", bname: "", zonecode: "", bcode: "" }];
    }
    return [];
  });
  const [isSearching, setIsSearching] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  // 지번 직접검색(VWorld) — Daum이 못 찾는 지번·산·농지 등을 직접 입력으로 해석.
  const [directQuery, setDirectQuery] = useState("");
  const [directBusy, setDirectBusy] = useState(false);
  const [directMsg, setDirectMsg] = useState("");
  // 토지지번검색(자동완성) — 타이핑하면 후보를 띄워 선택(다음 주소검색 UX).
  type AddrCandidate = { address: string; road_address?: string; pnu?: string | null; lat?: number | null; lon?: number | null; kind?: string };
  const [candidates, setCandidates] = useState<AddrCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [showCandidates, setShowCandidates] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeq = useRef(0); // 응답 경합 가드: 마지막 요청만 반영(stale 응답 무시)
  const [shareParcel, setShareParcel] = useState<AddressEntry | null>(null); // 호실/대지지분 모달 대상
  const enrichSeq = useRef(0); // 토지정보 보강 응답 경합 가드(stale 머지 차단)
  // WP-D: store 비기록 모드(writeToContext=false)의 요약 표시·콜백용 로컬 분석값.
  const [localAnalysis, setLocalAnalysis] = useState<AddressAnalysisSummary | null>(null);
  // 지도 클릭 필지 선택 패널 표시 여부(다필지 모드 전용)
  const [showMapPicker, setShowMapPicker] = useState(false);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 로컬 state가 있으면 그것을 표시, 없으면 빈 상태 (siteAnalysis 참조 제거 — 새 프로젝트 시 이전 데이터 잔류 방지)
  const displayAddresses = addresses;

  // 다필지 표시용 행 데이터 — 지번(번지) 우선 + 면적/평 + 상태(면적확보/보완필요).
  // 대량(수백 필지) 가독성: 요약 헤더 + 스크롤 컴팩트 리스트로 일목요연하게.
  const parcelRows = useMemo(() =>
    displayAddresses.map((a) => {
      const label = (a.jibunAddress || a.fullAddress || "").trim(); // 번지 포함 지번 우선
      return {
        label: label || "(주소 미상)",
        areaSqm: a.areaSqm ?? null,
        zoneCode: a.zoneCode ?? null,
        bcrPct: a.bcrPct ?? null,
        farPct: a.farPct ?? null,
        jimok: a.jimok ?? null,
        isAggregate: a.isAggregate ?? false,
        unitCount: a.unitCount ?? null,
        pnu: a.pnu ?? null,
        entry: a,
      };
    }), [displayAddresses]);

  const parcelStats = useMemo(() => {
    const n = parcelRows.length;
    const withArea = parcelRows.filter((r) => r.areaSqm && r.areaSqm > 0);
    const totalSqm = withArea.reduce((s, r) => s + (r.areaSqm || 0), 0);
    // 지역(시군구) 수 — "시 구" 앞 2토큰 기준
    const regions = new Set(parcelRows.map((r) => r.label.split(" ").slice(0, 2).join(" ")).filter(Boolean));
    return { n, withAreaCnt: withArea.length, needFixCnt: n - withArea.length, totalSqm, regionCnt: regions.size };
  }, [parcelRows]);

  // 종합 토지 분석 자동 트리거 (주소 입력 즉시 백그라운드 실행)
  // 카카오에서 얻은 bcode(법정동코드) + 지번주소를 백엔드에 전달하여 토지정보 조회
  const triggerComprehensiveAnalysis = useCallback(async (address: string, bcode?: string, jibunAddress?: string) => {
    // WP-D race 가드: 트리거 시점의 활성 projectId 캡처 — 응답 도착 시
    // 불일치(분석 중 프로젝트 전환)면 store 기록을 중단해 오염을 차단한다.
    const triggeredProjectId = useProjectContextStore.getState().projectId;
    setIsAnalyzing(true);
    try {
      const data = await apiClient.post<{
        pnu: string | null;
        coordinates: { lat: number; lon: number } | null;
        zone_type: string | null;
        zone_limits: { max_bcr_pct: number; max_far_pct: number } | null;
        land_register: { land_category: string; area_sqm: number; official_price_per_sqm: number } | null;
        building_info: { building_name: string; main_purpose: string; total_area_sqm: number; ground_floors: number } | null;
        official_prices: Array<{ pnu: string; year: number; price_per_sqm: number }>;
        local_ordinance: { sido: string; sigungu: string | null; effective_bcr: number; effective_far: number; source: string } | null;
      }>("/zoning/comprehensive", {
        body: { address, bcode: bcode ?? "", jibun_address: jibunAddress ?? "" },
        useMock: false,
      });

      const analyzedAreaSqm = data.land_register?.area_sqm
        ?? (data as Record<string, unknown>).land_area_sqm as number | undefined
        ?? null;

      // 로컬 요약/콜백 — store와 무관하게 전달(비기록 모드의 면적 자동채움 등 기존 동작 유지).
      const summary: AddressAnalysisSummary = {
        address,
        pnu: data.pnu ?? null,
        landAreaSqm: analyzedAreaSqm,
        zoneCode: data.zone_type ?? null,
        effectiveBcr: data.local_ordinance?.effective_bcr ?? null,
        effectiveFar: data.local_ordinance?.effective_far ?? null,
        dataSource: "백엔드 API (bcode:" + (bcode ?? "없음") + ")",
      };
      setLocalAnalysis(summary);
      // 필지 칩에 면적 자동 반영(로컬 state) — onChange 데이터(areaSqm)로도 노출된다.
      if (analyzedAreaSqm && analyzedAreaSqm > 0) {
        setAddresses((prev) => prev.map((a) =>
          a.fullAddress === address || a.jibunAddress === address
            ? { ...a, areaSqm: analyzedAreaSqm, areaPyeong: analyzedAreaSqm / 3.305785 }
            : a,
        ));
      }
      onAnalyzed?.(summary);

      // WP-D 가드: 비기록 모드면 store 기록 생략, 트리거 시점과 활성 프로젝트가
      // 다르면(전환 race) 기록 중단 — 무관 프로젝트 스냅샷 오염 차단.
      if (!writeToContext || useProjectContextStore.getState().projectId !== triggeredProjectId) {
        return;
      }

      updateSiteAnalysis({
        address,
        pnu: data.pnu ?? siteAnalysis?.pnu ?? null,
        estimatedValue: siteAnalysis?.estimatedValue ?? null,
        landAreaSqm: analyzedAreaSqm ?? siteAnalysis?.landAreaSqm ?? null,
        zoneCode: data.zone_type ?? siteAnalysis?.zoneCode ?? null,
        coordinates: data.coordinates ?? undefined,
        officialPrices: data.official_prices?.map((p) => ({ pnu: p.pnu, year: p.year, pricePerSqm: p.price_per_sqm })),
        ordinance: data.local_ordinance ? {
          sido: data.local_ordinance.sido,
          sigungu: data.local_ordinance.sigungu,
          nationalBcr: data.zone_limits?.max_bcr_pct ?? 60,
          nationalFar: data.zone_limits?.max_far_pct ?? 250,
          ordinanceBcr: data.local_ordinance.effective_bcr,
          ordinanceFar: data.local_ordinance.effective_far,
          effectiveBcr: data.local_ordinance.effective_bcr,
          effectiveFar: data.local_ordinance.effective_far,
          source: data.local_ordinance.source,
          legalBasis: "",
        } : undefined,
        buildingInfo: data.building_info ? {
          buildingName: data.building_info.building_name,
          mainPurpose: data.building_info.main_purpose,
          totalAreaSqm: data.building_info.total_area_sqm,
          groundFloors: data.building_info.ground_floors,
          structure: "",
          useApprovalDate: "",
        } : undefined,
        dataSource: "백엔드 API (bcode:" + (bcode ?? "없음") + ")",
        fetchedAt: new Date().toISOString(),
      });
    } catch {
      // 분석 실패해도 주소는 이미 저장됨
    } finally {
      setIsAnalyzing(false);
    }
  }, [siteAnalysis, updateSiteAnalysis, writeToContext, onAnalyzed]);

  // ★등록된 '모든' 필지의 토지정보(면적·용도지역·건폐/용적·지목·공시지가)+집합건물 여부 일괄 보강.
  //   (처음 1필지만 분석되던 근본문제 해결 — 개별등록·엑셀 공통). 주소 매칭으로 머지.
  const enrichParcels = useCallback(async (entries: AddressEntry[]) => {
    // 토지정보(면적·용도지역) 또는 건폐/용적·집합건물 플래그가 없는 행만 보강(엑셀 완전입력행도 bcr/far·빌라 보강).
    const need = entries.filter((e) =>
      (e.fullAddress || e.jibunAddress) &&
      (!e.areaSqm || !e.zoneCode || e.bcrPct == null || e.isAggregate === undefined),
    );
    if (need.length === 0) return;
    type P = {
      __rid?: number; area_sqm?: number | null; zone_type?: string | null; jimok?: string | null;
      pnu?: string | null; official_price_per_sqm?: number | null; bcr_pct?: number | null; far_pct?: number | null;
      building?: { is_aggregate?: boolean; building_name?: string; main_purpose?: string; unit_count?: number | null } | null;
      status?: string | null;
    };
    const seq = ++enrichSeq.current;
    const CHUNK = 60; // 필지당 최대 3 외부콜 — 타임아웃 회피 위해 분할 호출(부분결과 즉시 반영)
    // need 내 인덱스(=__rid)와 entry 참조를 함께 보존 → 주소 충돌 없이 정확 매칭.
    for (let start = 0; start < need.length; start += CHUNK) {
      const slice = need.slice(start, start + CHUNK);
      let parcels: P[] = [];
      try {
        const r = await apiClient.post<{ parcels: P[] }>("/zoning/parcels-info", {
          body: { parcels: slice.map((e, i) => ({ __rid: i, address: e.fullAddress, jibun: e.jibunAddress, pnu: e.pnu, bcode: e.bcode })) },
          useMock: false, timeoutMs: 90000,
        });
        parcels = r.parcels || [];
      } catch {
        continue; // 이 청크 실패는 '보완필요'로 남김(가짜 생성 없음)
      }
      if (seq !== enrichSeq.current) return; // 더 새로운 보강이 시작됐으면 stale 머지 폐기
      // 결과 __rid(슬라이스 인덱스)→해당 행의 불변 uid로 변환해 매칭.
      //   (참조매칭은 triggerComprehensiveAnalysis가 객체를 교체하면 깨지지만, uid는 spread로 보존돼 안전.)
      const byUid = new Map<string, P>();
      for (const p of parcels) {
        if (typeof p.__rid !== "number") continue;
        const uid = slice[p.__rid]?.__uid;
        if (uid) byUid.set(uid, p);
      }
      setAddresses((prev) => prev.map((a) => {
        const m = a.__uid ? byUid.get(a.__uid) : undefined;
        if (!m) return a;
        return {
          ...a,
          areaSqm: m.area_sqm ?? a.areaSqm,
          areaPyeong: m.area_sqm ? m.area_sqm / 3.305785 : a.areaPyeong,
          pnu: m.pnu || a.pnu,
          zoneCode: m.zone_type || a.zoneCode,
          bcrPct: m.bcr_pct ?? a.bcrPct,
          farPct: m.far_pct ?? a.farPct,
          jimok: m.jimok || a.jimok,
          officialPrice: m.official_price_per_sqm ?? a.officialPrice,
          isAggregate: m.building?.is_aggregate ?? a.isAggregate ?? false,
          buildingName: m.building?.building_name || a.buildingName,
          mainPurpose: m.building?.main_purpose || a.mainPurpose,
          unitCount: m.building?.unit_count ?? a.unitCount,
          infoStatus: (m.status as AddressEntry["infoStatus"]) || a.infoStatus,
        };
      }));
    }
  }, []);

  const handleAddressSelect = useCallback((result: KakaoAddressResult) => {
    const entry: AddressEntry = {
      __uid: newUid(),
      fullAddress: result.fullAddress,
      jibunAddress: result.jibunAddress,
      roadAddress: result.roadAddress,
      sido: result.sido,
      sigungu: result.sigungu,
      bname: result.bname,
      zonecode: result.zonecode,
      bcode: result.bcode,
    };

    let newAddresses: AddressEntry[];
    if (single) {
      newAddresses = [entry];
    } else {
      // 다필지: 중복이면 조기 반환(불필요한 종합분석·보강 재발사 차단).
      if (addresses.some((a) => a.fullAddress === entry.fullAddress)) {
        setIsSearching(false);
        onChange?.(addresses);
        return;
      }
      newAddresses = [...addresses, entry];
    }

    setAddresses(newAddresses);
    setIsSearching(false);

    // ProjectContextStore에 자동 저장 (Single Source of Truth)
    // 주소만 즉시 저장, 나머지 필드는 기존값 유지 (partial merge)
    // WP-D: writeToContext=false면 store 기록 생략(콜백 전용 모드).
    const primary = newAddresses[0];
    if (primary) {
      if (writeToContext) {
        updateSiteAnalysis({
          address: primary.fullAddress,
        });
      }

      // 자동 종합 분석 트리거 (bcode + 지번주소 포함) — 대표 필지는 store/파이프라인용 풀분석.
      triggerComprehensiveAnalysis(primary.fullAddress, primary.bcode, primary.jibunAddress);
    }
    // ★등록된 모든 필지(대표 포함)의 토지정보 일괄 보강 — 비대표 필지도 면적·용도·건폐/용적이 채워진다.
    if (!single) void enrichParcels(newAddresses);

    onChange?.(newAddresses);
  }, [single, addresses, siteAnalysis, updateSiteAnalysis, onChange, writeToContext, triggerComprehensiveAnalysis, enrichParcels]);

  const handleRemove = useCallback((index: number) => {
    const newAddresses = addresses.filter((_, i) => i !== index);
    setAddresses(newAddresses);

    // 첫 번째 주소가 변경되면 store 업데이트 (partial merge)
    // WP-D: writeToContext=false면 store 기록 생략(콜백 전용 모드).
    if (newAddresses.length > 0 && writeToContext) {
      updateSiteAnalysis({
        address: newAddresses[0].fullAddress,
      });
    }

    onChange?.(newAddresses);
  }, [addresses, siteAnalysis, updateSiteAnalysis, onChange, writeToContext]);

  // 지번/주소 직접검색(VWorld) → 해석되면 필지로 추가(Daum이 못 찾는 지번 대응).
  const handleDirectAdd = useCallback(async () => {
    const q = directQuery.trim();
    if (!q || directBusy) return;
    setDirectBusy(true);
    setDirectMsg("");
    try {
      const r = await apiClient.post<{
        found: boolean; address?: string; jibun_address?: string;
        pnu?: string | null; bcode?: string | null; reason?: string;
      }>("/zoning/geocode", { body: { query: q }, useMock: false, timeoutMs: 30000 });
      if (!r.found) {
        setDirectMsg(r.reason || "해당 주소/지번을 찾지 못했습니다.");
        return;
      }
      // KakaoAddressResult 형태로 변환해 기존 추가 로직(handleAddressSelect) 재사용.
      handleAddressSelect({
        fullAddress: r.address || q,
        jibunAddress: r.jibun_address || r.address || q,
        roadAddress: "",
        sido: "", sigungu: "", bname: "", buildingName: "",
        zonecode: "", bcode: r.bcode || "",
      });
      setDirectQuery("");
      setDirectMsg("");
    } catch {
      setDirectMsg("검색 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setDirectBusy(false);
    }
  }, [directQuery, directBusy, handleAddressSelect]);

  // 토지지번검색 자동완성 — 입력 디바운스(350ms) 후 후보 조회(다음 주소검색처럼).
  const runSearch = useCallback(async (q: string) => {
    const query = q.trim();
    if (query.length < 2) { setCandidates([]); setShowCandidates(false); return; }
    const mySeq = ++searchSeq.current; // 이 요청의 순번
    setSearching(true);
    try {
      const r = await apiClient.post<{ candidates: AddrCandidate[] }>(
        "/zoning/search", { body: { query, size: 8 }, useMock: false, timeoutMs: 15000 },
      );
      if (mySeq !== searchSeq.current) return; // 더 새로운 요청이 떴으면 stale 응답 폐기
      setCandidates(r.candidates || []);
      setShowCandidates(true);
    } catch {
      if (mySeq === searchSeq.current) setCandidates([]);
    } finally {
      if (mySeq === searchSeq.current) setSearching(false);
    }
  }, []);

  const onDirectChange = useCallback((v: string) => {
    setDirectQuery(v);
    setDirectMsg("");
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => void runSearch(v), 350);
  }, [runSearch]);

  // 지도 단일 클릭 필지 선택(하위호환) → KakaoAddressResult 형태로 변환 후 기존 추가 로직 재사용.
  // bcode는 PNU 앞 10자리로 구성(pickCandidate 패턴 동일).
  const handleMapPick = useCallback((parcel: ParcelAtPointResult) => {
    if (!parcel.found || !parcel.address) return;
    const bcode = parcel.bcode || (parcel.pnu && parcel.pnu.length >= 10 ? parcel.pnu.slice(0, 10) : "");
    handleAddressSelect({
      fullAddress: parcel.address,
      jibunAddress: parcel.jibun || parcel.address,
      roadAddress: "",
      sido: "", sigungu: "", bname: "", buildingName: "",
      zonecode: "", bcode,
    });
    // 지도 패널은 필지 추가 후 닫는다(사용자가 원하면 다시 열 수 있음)
    setShowMapPicker(false);
  }, [handleAddressSelect]);

  // 지도 다중 선택 완료 콜백 — staged 배열을 일괄로 기존 handleAddressSelect 경로에 넣는다.
  // 각 필지를 KakaoAddressResult 형태로 변환해 순차 추가(중복은 handleAddressSelect 내부에서 방지).
  const handleMapPickMany = useCallback((parcels: ParcelAtPointResult[]) => {
    if (parcels.length === 0) return;

    // 현재 addresses를 읽어 중복 체크용 Set 생성(함수 호출 시점 스냅샷).
    // handleAddressSelect 내부에서도 중복 체크하므로 실질적으로 이중 방어.
    const existingAddresses = new Set(addresses.map((a) => a.fullAddress));

    let merged = [...addresses];

    for (const parcel of parcels) {
      if (!parcel.found || !parcel.address) continue;
      const fullAddress = parcel.address;
      if (existingAddresses.has(fullAddress)) continue; // 이미 있으면 건너뜀
      existingAddresses.add(fullAddress);

      const bcode = parcel.bcode || (parcel.pnu && parcel.pnu.length >= 10 ? parcel.pnu.slice(0, 10) : "");
      const entry: AddressEntry = {
        __uid: newUid(),
        fullAddress,
        jibunAddress: parcel.jibun || fullAddress,
        roadAddress: "",
        sido: "", sigungu: "", bname: "", zonecode: "", bcode,
        pnu: parcel.pnu,
        // parcel-at-point가 이미 반환한 토지정보 활용(enrichParcels 부담 최소화)
        ...(parcel.area_sqm != null ? { areaSqm: parcel.area_sqm, areaPyeong: parcel.area_sqm / 3.305785 } : {}),
        ...(parcel.zone_type ? { zoneCode: parcel.zone_type } : {}),
        ...(parcel.jimok ? { jimok: parcel.jimok } : {}),
        ...(parcel.bcr_pct != null ? { bcrPct: parcel.bcr_pct } : {}),
        ...(parcel.far_pct != null ? { farPct: parcel.far_pct } : {}),
      };
      merged = [...merged, entry];
    }

    if (merged.length === addresses.length) {
      // 새로 추가된 필지가 없으면 패널만 닫음
      setShowMapPicker(false);
      return;
    }

    setAddresses(merged);

    // 대표 필지(첫 번째)로 store·종합분석 갱신(기존 handleAddressSelect 동작 동일)
    const primary = merged[0];
    if (primary) {
      if (writeToContext) {
        updateSiteAnalysis({ address: primary.fullAddress });
      }
      triggerComprehensiveAnalysis(primary.fullAddress, primary.bcode, primary.jibunAddress);
    }

    // 토지정보가 완전히 채워지지 않은 필지 보강(면적·용도지역 등)
    if (!single) void enrichParcels(merged);

    onChange?.(merged);
    setShowMapPicker(false);
  }, [addresses, single, writeToContext, updateSiteAnalysis, triggerComprehensiveAnalysis, enrichParcels, onChange]);

  // 후보 선택 → 필지로 추가(PNU 보유 시 bcode 직접 구성, 종합분석 재실행).
  const pickCandidate = useCallback((c: AddrCandidate) => {
    const bcode = c.pnu && c.pnu.length >= 10 ? c.pnu.slice(0, 10) : "";
    handleAddressSelect({
      fullAddress: c.address,
      jibunAddress: c.address,
      roadAddress: c.road_address || "",
      sido: "", sigungu: "", bname: "", buildingName: "",
      zonecode: "", bcode,
    });
    setDirectQuery("");
    setCandidates([]);
    setShowCandidates(false);
    setDirectMsg("");
  }, [handleAddressSelect]);

  // 하단 요약 표시용 — store 기록 모드면 SSOT(siteAnalysis), 비기록 모드면 로컬 분석값만
  // 사용한다(무관 프로젝트의 store 데이터가 비기록 화면에 표시되는 혼선 방지).
  const displayAnalysis = writeToContext
    ? siteAnalysis
      ? {
          zoneCode: siteAnalysis.zoneCode,
          landAreaSqm: siteAnalysis.landAreaSqm,
          effectiveBcr: siteAnalysis.ordinance?.effectiveBcr ?? null,
          effectiveFar: siteAnalysis.ordinance?.effectiveFar ?? null,
          dataSource: siteAnalysis.dataSource ?? null,
        }
      : null
    : localAnalysis;

  // ── 다필지 엑셀 업로드 — 토지조서 양식 업로드 → 필지 추출(주소만 적어도 PNU·면적·용도 자동보강) ──
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadInfo, setUploadInfo] = useState<{ note: string; registry?: string } | null>(null);

  const handleExcelUpload = useCallback(async (file: File) => {
    setUploading(true);
    setUploadInfo(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiClient.post<{
        parcels?: Array<{ address?: string | null; jibun?: string | null; bcode?: string | null; pnu?: string | null; area_sqm?: number | null; zone_type?: string | null; jimok?: string | null; official_price_per_sqm?: number | null }>;
        note?: string; error?: string; registry_guidance?: { message?: string };
      }>("/zoning/parse-parcels", { body: fd, useMock: false, timeoutMs: 120000 });
      if (res.error) { setUploadInfo({ note: res.error }); return; }
      // parse-parcels가 이미 채운 면적·용도지역·지목·공시지가를 보존(이전엔 areaSqm만 받고 폐기).
      const entries: AddressEntry[] = (res.parcels ?? [])
        .filter((p) => (p.address || p.pnu))
        .map((p) => {
          // ★소재지(동)와 지번(번지)이 분리된 양식이면 결합해 '완전한 지번주소'를 fullAddress로.
          //   (이게 누락돼 동 단위 주소만 들어가 부지분석·구획도가 동 대표필지로 수렴하던 근본버그.)
          const addr = (p.address || "").trim();
          const jb = (p.jibun || "").trim();
          const full = (jb && addr && !addr.includes(jb)) ? `${addr} ${jb}` : (addr || jb || p.pnu || "");
          return ({
          __uid: newUid(),
          fullAddress: full,
          jibunAddress: jb || addr || "",
          roadAddress: "", sido: "", sigungu: "", bname: "", zonecode: "",
          bcode: p.bcode || "",
          pnu: p.pnu || undefined,
          ...(p.area_sqm ? { areaSqm: p.area_sqm, areaPyeong: p.area_sqm / 3.305785 } : {}),
          ...(p.zone_type ? { zoneCode: p.zone_type } : {}),
          ...(p.jimok ? { jimok: p.jimok } : {}),
          ...(p.official_price_per_sqm ? { officialPrice: p.official_price_per_sqm } : {}),
        });
        });
      // ★업로드한 필지를 앞에 둔다(기존 검색분은 뒤로 보존, 혼용 가능). 방금 올린 토지조서가
      //   대표(primary)가 되어 이전에 검색한 주소가 분석에 잔류하는 오류를 막는다.
      const merged = single
        ? entries.slice(0, 1)
        : [...entries, ...addresses.filter((a) => !entries.some((e) => e.fullAddress === a.fullAddress))];
      setAddresses(merged);

      // ★검색 경로(handleAddressSelect)와 동일하게 대표 필지로 store 갱신 + 종합분석 재실행.
      //   (이게 누락돼 엑셀 업로드 시 이전 검색 주소의 분석이 그대로 표시되던 버그를 근본수정.)
      const primary = merged[0];
      if (primary) {
        if (writeToContext) updateSiteAnalysis({ address: primary.fullAddress });
        triggerComprehensiveAnalysis(primary.fullAddress, primary.bcode, primary.jibunAddress);
      }
      onChange?.(merged);
      setUploadInfo({ note: res.note || `${entries.length}필지 등록`, registry: res.registry_guidance?.message });
      // 건폐율/용적률·집합건물(빌라) 여부 보강 — parse-parcels엔 없는 항목을 일괄 채운다.
      if (!single) void enrichParcels(merged);
    } catch (e: any) {
      setUploadInfo({ note: e?.message || "엑셀 처리 실패" });
    } finally {
      setUploading(false);
    }
  }, [single, addresses, onChange, writeToContext, updateSiteAnalysis, triggerComprehensiveAnalysis, enrichParcels]);

  const downloadTemplate = useCallback(async () => {
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const res = await fetch(`${apiV1BaseUrl()}/zoning/land-schedule-template`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "PropAI_토지조서_양식.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setUploadInfo({ note: "양식 다운로드 실패 — 잠시 후 다시 시도해 주세요." });
    }
  }, []);

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {/* 등록된 필지 목록 — 요약 헤더 + 컴팩트 스크롤 리스트(대량 필지 가독성 극대화) */}
      {displayAddresses.length > 0 && (
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden">
          {/* 요약 헤더: 필지수·합계면적·면적확보/보완필요·지역수 */}
          {displayAddresses.length > 1 && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--line)] bg-[var(--surface-muted)]/50 px-3 py-2 text-[11px]">
              <span className="font-bold text-[var(--text-primary)]">필지 {parcelStats.n.toLocaleString()}개</span>
              {parcelStats.totalSqm > 0 && (
                <span className="text-[var(--accent-strong)] font-bold">합계 {Math.round(parcelStats.totalSqm).toLocaleString()}㎡ ({(parcelStats.totalSqm / 3.305785).toFixed(1)}평)</span>
              )}
              {parcelStats.regionCnt > 0 && <span className="text-[var(--text-secondary)]">지역 {parcelStats.regionCnt}곳</span>}
              <span className="text-[var(--text-secondary)]">면적확보 <b className="text-[var(--text-primary)]">{parcelStats.withAreaCnt}</b></span>
              {parcelStats.needFixCnt > 0 && (
                <span className="rounded bg-[color-mix(in_srgb,var(--status-warning)_15%,transparent)] px-1.5 py-0.5 font-semibold text-[var(--status-warning)]">보완필요 {parcelStats.needFixCnt}</span>
              )}
            </div>
          )}
          {/* 컴팩트 리스트: 지번 + 토지정보(면적·용도지역·건폐/용적·지목) 2행 + 공동주택(호실·대지지분) */}
          <ul className={`divide-y divide-[var(--line)]/60 ${displayAddresses.length > 8 ? "max-h-[360px] overflow-y-auto" : ""}`}>
            {parcelRows.map((row, idx) => (
              <li key={`${row.label}-${idx}`} className="flex items-start gap-2 px-3 py-1.5 hover:bg-[var(--surface-muted)]/40">
                <span className="mt-0.5 w-7 shrink-0 text-right text-[10px] tabular-nums text-[var(--text-hint)]">{idx + 1}</span>
                <div className="min-w-0 flex-1">
                  {/* 1행: 지번 + 면적 */}
                  <div className="flex items-center gap-2">
                    <span className="flex-1 truncate text-[12px] font-medium text-[var(--text-primary)]" title={row.label}>{row.label}</span>
                    {row.areaSqm && row.areaSqm > 0 ? (
                      <span className="shrink-0 text-[10px] font-bold tabular-nums text-[var(--accent-strong)]">
                        {Math.round(row.areaSqm).toLocaleString()}㎡ · {(row.areaSqm / 3.305785).toFixed(1)}평
                      </span>
                    ) : (
                      <span className="shrink-0 rounded bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] px-1 py-0.5 text-[9px] font-semibold text-[var(--status-warning)]">{isAnalyzing ? "조회중…" : "보완필요"}</span>
                    )}
                  </div>
                  {/* 2행: 용도지역·건폐/용적·지목 + 공동주택(빌라) 배지 */}
                  {(row.zoneCode || row.bcrPct || row.jimok || row.isAggregate) && (
                    <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[9.5px] text-[var(--text-secondary)]">
                      {row.zoneCode && <span className="rounded bg-[var(--accent-soft)] px-1 py-0.5 font-semibold text-[var(--accent-strong)]">{row.zoneCode}</span>}
                      {(row.bcrPct || row.farPct) && <span>건폐 {row.bcrPct ?? "—"}% · 용적 {row.farPct ?? "—"}%</span>}
                      {row.jimok && <span>지목 {row.jimok}</span>}
                      {row.isAggregate && (
                        <button
                          type="button"
                          onClick={() => setShareParcel(row.entry)}
                          title="공동주택(빌라) — 호실·세대 대지지분 보기/반영"
                          className="rounded bg-[color-mix(in_srgb,var(--accent-strong)_14%,transparent)] px-1.5 py-0.5 font-bold text-[var(--accent-strong)] hover:bg-[color-mix(in_srgb,var(--accent-strong)_24%,transparent)]"
                        >
                          🏢 공동주택{row.unitCount ? ` ${row.unitCount}세대` : ""} · 호실/대지지분 ▸
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => handleRemove(idx)}
                  className="mt-0.5 shrink-0 rounded p-0.5 text-[var(--text-hint)] hover:bg-red-500/10 hover:text-red-500 transition-colors"
                  aria-label="필지 삭제"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 다필지 안내 — 검색 추가와 엑셀 일괄등록이 병행됨을 명시(단일 모드는 숨김) */}
      {!single && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--text-secondary)]">
          <span className="font-bold text-[var(--text-primary)]">다필지 등록</span>
          <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 font-semibold text-[var(--accent-strong)]">🔍 검색으로 한 필지씩 추가</span>
          <span className="text-[var(--text-hint)]">또는</span>
          <span className="rounded bg-[var(--accent-soft)] px-1.5 py-0.5 font-semibold text-[var(--accent-strong)]">📊 엑셀로 일괄 등록</span>
          <span className="text-[var(--text-hint)]">— 둘 다 사용 가능(혼용 OK)</span>
        </div>
      )}

      {/* 주소 검색 입력 */}
      {(isSearching || displayAddresses.length === 0) ? (
        <KakaoAddressSearch
          onSelect={handleAddressSelect}
          placeholder={placeholder}
          disabled={disabled}
        />
      ) : (
        <div className="flex gap-2">
          {/* 주소 변경 (단일) 또는 필지 추가 (다필지) */}
          {single ? (
            <button
              type="button"
              onClick={() => setIsSearching(true)}
              className="flex-1 rounded-xl border border-dashed border-[var(--line-strong)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] transition-all"
            >
              주소 변경
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setIsSearching(true)}
              className="flex-1 rounded-xl border border-dashed border-[var(--line-strong)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] hover:bg-[var(--accent-soft)] transition-all flex items-center justify-center gap-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
              필지 추가
            </button>
          )}
        </div>
      )}

      {/* 토지지번검색(VWorld 자동완성) — 타이핑하면 후보를 띄워 선택(다음 주소검색 UX).
          Daum이 못 찾는 지번·산·농지도 직접 검색·선택해 추가(다필지 누적). */}
      {!single && (
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/40 px-3 py-2">
          <div className="relative flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-bold text-[var(--text-secondary)]">📍 토지지번 검색</span>
            <div className="relative min-w-[180px] flex-1">
              <input
                value={directQuery}
                disabled={disabled || directBusy}
                onChange={(e) => onDirectChange(e.target.value)}
                onFocus={() => { if (candidates.length) setShowCandidates(true); }}
                onBlur={() => setTimeout(() => setShowCandidates(false), 150)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (candidates.length) pickCandidate(candidates[0]); else void handleDirectAdd(); } }}
                placeholder="예) 의정부동 224, 산 12-3 — 입력하면 후보가 표시됩니다"
                className="w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 py-1.5 text-[11px] text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
              />
              {/* 자동완성 후보 드롭다운 */}
              {showCandidates && (candidates.length > 0 || searching) && (
                <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-64 overflow-y-auto rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
                  {searching && <li className="px-3 py-2 text-[11px] text-[var(--text-tertiary)]">검색 중…</li>}
                  {candidates.map((c, i) => (
                    <li key={`${c.address}-${i}`}>
                      <button
                        type="button"
                        onMouseDown={(e) => { e.preventDefault(); pickCandidate(c); }}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[11px] hover:bg-[var(--accent-soft)]"
                      >
                        <span className="truncate text-[var(--text-primary)]">{c.address}</span>
                        <span className="shrink-0 rounded bg-[var(--surface-strong)] px-1.5 py-0.5 text-[9px] font-bold text-[var(--text-tertiary)]">{c.kind || "지번"}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button
              type="button"
              disabled={disabled || directBusy || !directQuery.trim()}
              onClick={() => { if (candidates.length) pickCandidate(candidates[0]); else void handleDirectAdd(); }}
              className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 disabled:opacity-50"
            >
              {directBusy ? "검색 중…" : "＋ 추가"}
            </button>
          </div>
          {directMsg && <p className="mt-1 text-[11px] font-semibold text-amber-500">⚠ {directMsg}</p>}
        </div>
      )}

      {/* 지도에서 선택 — 지도를 직접 클릭해 필지를 추가(다필지 모드 전용) */}
      {!single && (
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/40 px-3 py-2">
          {/* 토글 헤더 버튼 */}
          <button
            type="button"
            disabled={disabled}
            onClick={() => setShowMapPicker((v) => !v)}
            className="flex w-full items-center justify-between gap-2 text-[11px] font-bold text-[var(--text-secondary)] hover:text-[var(--accent-strong)] transition-colors disabled:opacity-50"
          >
            <span className="flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>
              지도에서 선택
            </span>
            {/* 열림/닫힘 화살표 */}
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
              style={{ transform: showMapPicker ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }}>
              <path d="m6 9 6 6 6-6"/>
            </svg>
          </button>
          {/* 지도 패널 — 토글 열릴 때만 마운트(Leaflet은 DOM 필요) */}
          {showMapPicker && (
            <div className="mt-2">
              <MapShell height={360} label="필지 선택 지도" loadingMessage="필지 선택 지도 로딩…">
                <ParcelPickerMapDynamic onPick={handleMapPick} onPickMany={handleMapPickMany} height={360} />
              </MapShell>
            </div>
          )}
        </div>
      )}

      {/* 다필지 엑셀 등록 — 토지조서 양식 업로드/다운로드(주소만 적어도 PNU·면적·용도·공시지가 자동보강) */}
      {!single && (
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/40 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleExcelUpload(f); e.target.value = ""; }}
            />
            <button
              type="button"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-primary)] hover:border-[var(--accent-strong)] disabled:opacity-50"
            >
              📊 {uploading ? "처리 중…" : "엑셀로 다필지 등록"}
            </button>
            <button
              type="button"
              onClick={() => void downloadTemplate()}
              className="text-[11px] font-semibold text-[var(--accent-strong)] underline-offset-2 hover:underline"
            >
              양식 다운로드 ↓
            </button>
            <span className="text-[10px] text-[var(--text-hint)]">주소·지번만 적어도 PNU·면적·용도지역·공시지가 자동수집</span>
          </div>
          {uploadInfo && (
            <div className="mt-2 rounded-md border border-[var(--line)] bg-[var(--surface)]/60 px-2.5 py-1.5 text-[11px] text-[var(--text-secondary)]">
              <p>📍 {uploadInfo.note}</p>
              {uploadInfo.registry && <p className="mt-1 font-semibold text-amber-500">🏛️ {uploadInfo.registry}</p>}
            </div>
          )}
        </div>
      )}

      {/* 분석 중 표시 */}
      {isAnalyzing && (
        <div className="flex items-center gap-2 text-xs text-[var(--accent-strong)]">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
          토지정보 종합 분석 중...
        </div>
      )}

      {/* 분석 완료 — 기본 정보 요약 (기록 모드: SSOT / 비기록 모드: 로컬 분석값) */}
      {!isAnalyzing && displayAnalysis?.zoneCode && displayAddresses.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[10px]">
          <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 font-bold text-[var(--accent-strong)]">
            {displayAnalysis.zoneCode}
          </span>
          {displayAnalysis.landAreaSqm && (
            <span className="text-[var(--text-secondary)]">
              {displayAnalysis.landAreaSqm.toLocaleString()}m²
            </span>
          )}
          {displayAnalysis.effectiveBcr && (
            <span className="text-[var(--text-hint)]">
              건폐율 {displayAnalysis.effectiveBcr}% · 용적률 {displayAnalysis.effectiveFar}%
            </span>
          )}
          {displayAnalysis.dataSource && (
            <span className="text-[var(--text-hint)]">
              ({displayAnalysis.dataSource})
            </span>
          )}
        </div>
      )}

      {/* 공동주택(빌라) 호실·세대 대지지분 모달 — 검색/등록한 필지에서 바로 호실 분석/반영 */}
      {shareParcel && (
        <LandShareModal
          jibun={shareParcel.jibunAddress || shareParcel.fullAddress}
          pnu={shareParcel.pnu}
          onClose={() => setShareParcel(null)}
          onApplyArea={() => { /* 검색 컨텍스트에선 행 면적 갱신 불필요(토지조서에서 반영) */ }}
        />
      )}
    </div>
  );
}
