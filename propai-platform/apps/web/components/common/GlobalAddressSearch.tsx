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

import { useCallback, useRef, useState } from "react";
import { KakaoAddressSearch, type KakaoAddressResult } from "@/components/ui/KakaoAddressSearch";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient, apiV1BaseUrl } from "@/lib/api-client";

export interface AddressEntry {
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
      return [{ fullAddress: initialAddress, jibunAddress: "", roadAddress: "", sido: "", sigungu: "", bname: "", zonecode: "", bcode: "" }];
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
  // WP-D: store 비기록 모드(writeToContext=false)의 요약 표시·콜백용 로컬 분석값.
  const [localAnalysis, setLocalAnalysis] = useState<AddressAnalysisSummary | null>(null);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 로컬 state가 있으면 그것을 표시, 없으면 빈 상태 (siteAnalysis 참조 제거 — 새 프로젝트 시 이전 데이터 잔류 방지)
  const displayAddresses = addresses;

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

  const handleAddressSelect = useCallback((result: KakaoAddressResult) => {
    const entry: AddressEntry = {
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
      // 다필지: 중복 방지 후 추가
      const exists = addresses.some((a) => a.fullAddress === entry.fullAddress);
      newAddresses = exists ? addresses : [...addresses, entry];
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

      // 자동 종합 분석 트리거 (bcode + 지번주소 포함)
      triggerComprehensiveAnalysis(primary.fullAddress, primary.bcode, primary.jibunAddress);
    }

    onChange?.(newAddresses);
  }, [single, addresses, siteAnalysis, updateSiteAnalysis, onChange, writeToContext, triggerComprehensiveAnalysis]);

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
        parcels?: Array<{ address?: string | null; jibun?: string | null; bcode?: string | null; pnu?: string | null; area_sqm?: number | null }>;
        note?: string; error?: string; registry_guidance?: { message?: string };
      }>("/zoning/parse-parcels", { body: fd, useMock: false, timeoutMs: 120000 });
      if (res.error) { setUploadInfo({ note: res.error }); return; }
      const entries: AddressEntry[] = (res.parcels ?? [])
        .filter((p) => (p.address || p.pnu))
        .map((p) => ({
          fullAddress: p.address || p.pnu || "",
          jibunAddress: p.jibun || p.address || "",
          roadAddress: "", sido: "", sigungu: "", bname: "", zonecode: "",
          bcode: p.bcode || "",
          ...(p.area_sqm ? { areaSqm: p.area_sqm } : {}),
        }));
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
    } catch (e: any) {
      setUploadInfo({ note: e?.message || "엑셀 처리 실패" });
    } finally {
      setUploading(false);
    }
  }, [single, addresses, onChange, writeToContext, updateSiteAnalysis, triggerComprehensiveAnalysis]);

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
      {/* 등록된 필지 목록 */}
      {displayAddresses.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {displayAddresses.map((addr, idx) => (
            <div
              key={`${addr.fullAddress}-${idx}`}
              className="flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2"
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-md bg-[var(--accent-strong)] text-[10px] font-bold text-white flex-shrink-0">
                {idx + 1}
              </span>
              <span className="text-sm text-[var(--text-primary)] truncate flex-1">
                {addr.fullAddress}
              </span>
              {addr.areaSqm ? (
                <span className="text-[10px] text-[var(--accent-strong)] font-bold flex-shrink-0">
                  {addr.areaSqm.toLocaleString()}m² ({(addr.areaSqm / 3.305785).toFixed(1)}평)
                </span>
              ) : addr.sido ? (
                <span className="text-[10px] text-[var(--text-hint)] flex-shrink-0">
                  {addr.sido} {addr.sigungu}
                </span>
              ) : null}
              {addresses.length > 0 && (
                <button
                  type="button"
                  onClick={() => handleRemove(idx)}
                  className="flex-shrink-0 rounded-md p-0.5 text-[var(--text-hint)] hover:text-red-500 hover:bg-red-500/10 transition-colors"
                  aria-label="필지 삭제"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
              )}
            </div>
          ))}
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

      {/* 다필지 요약 + 면적 합계 */}
      {!single && displayAddresses.length > 1 && (() => {
        const totalSqm = displayAddresses.reduce((sum, a) => sum + (a.areaSqm || 0), 0);
        return (
          <div className="rounded-lg bg-[var(--surface-soft)] p-2.5 text-[10px]">
            <div className="flex items-center justify-between">
              <span className="text-[var(--text-secondary)] font-bold">
                {displayAddresses.length}개 필지 등록
              </span>
              {totalSqm > 0 && (
                <span className="text-[var(--accent-strong)] font-bold">
                  합계: {totalSqm.toLocaleString()}m² ({(totalSqm / 3.305785).toFixed(1)}평)
                </span>
              )}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
