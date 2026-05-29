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

import { useCallback, useState } from "react";
import { KakaoAddressSearch, type KakaoAddressResult } from "@/components/ui/KakaoAddressSearch";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";
import { fetchVWorldComprehensive } from "@/lib/vworld-client";

export interface AddressEntry {
  fullAddress: string;
  jibunAddress: string;
  roadAddress: string;
  sido: string;
  sigungu: string;
  bname: string;
  zonecode: string;
  areaSqm?: number; // 면적 (m²) — API에서 자동 반영
  areaPyeong?: number; // 면적 (평) — 자동 환산
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
}

export function GlobalAddressSearch({
  single = false,
  onChange,
  className = "",
  placeholder = "주소를 검색하세요",
  disabled = false,
}: GlobalAddressSearchProps) {
  const [addresses, setAddresses] = useState<AddressEntry[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 로컬 state가 있으면 그것을 표시, 없으면 빈 상태 (siteAnalysis 참조 제거 — 새 프로젝트 시 이전 데이터 잔류 방지)
  const displayAddresses = addresses;

  // 종합 토지 분석 자동 트리거 (주소 입력 즉시 백그라운드 실행)
  // Railway 서버(해외 IP)에서 VWORLD 502 에러 발생하므로 브라우저에서 직접 호출
  const triggerComprehensiveAnalysis = useCallback(async (address: string) => {
    setIsAnalyzing(true);
    try {
      // 1차: 브라우저에서 직접 VWORLD API 호출 (한국 IP → 정상 동작)
      const vworldData = await fetchVWorldComprehensive(address);

      if (vworldData && (vworldData.pnu || vworldData.land_register)) {
        // VWORLD 직접 호출 성공 → 결과 저장
        const bcr = vworldData.zone_limits?.max_bcr_pct ?? 60;
        const far = vworldData.zone_limits?.max_far_pct ?? 250;

        updateSiteAnalysis({
          address,
          pnu: vworldData.pnu ?? siteAnalysis?.pnu ?? null,
          estimatedValue: siteAnalysis?.estimatedValue ?? null,
          landAreaSqm: vworldData.land_register?.area_sqm ?? siteAnalysis?.landAreaSqm ?? null,
          zoneCode: vworldData.zone_type ?? siteAnalysis?.zoneCode ?? null,
          coordinates: vworldData.coordinates ?? undefined,
          officialPrices: vworldData.land_register?.official_price_per_sqm
            ? [{ pnu: vworldData.pnu ?? "", year: 2025, pricePerSqm: vworldData.land_register.official_price_per_sqm }]
            : undefined,
          ordinance: {
            sido: "",
            sigungu: null,
            nationalBcr: bcr,
            nationalFar: far,
            ordinanceBcr: bcr,
            ordinanceFar: far,
            effectiveBcr: bcr,
            effectiveFar: far,
            source: "VWORLD(브라우저 직접호출)",
            legalBasis: "국토계획법 제78조",
          },
          dataSource: "VWORLD(브라우저 직접호출)",
          fetchedAt: new Date().toISOString(),
        });
        return;
      }

      // 2차 폴백: 백엔드 API 호출 (VWORLD 직접 호출 실패 시)
      const data = await apiClient.post<{
        pnu: string | null;
        coordinates: { lat: number; lon: number } | null;
        zone_type: string | null;
        zone_limits: { max_bcr_pct: number; max_far_pct: number } | null;
        land_register: { land_category: string; area_sqm: number; official_price_per_sqm: number } | null;
        building_info: { building_name: string; main_purpose: string; total_area_sqm: number; ground_floors: number } | null;
        official_prices: Array<{ pnu: string; year: number; price_per_sqm: number }>;
        local_ordinance: { sido: string; sigungu: string | null; effective_bcr: number; effective_far: number; source: string } | null;
      }>("/zoning/comprehensive", { body: { address }, useMock: false });

      updateSiteAnalysis({
        address,
        pnu: data.pnu ?? siteAnalysis?.pnu ?? null,
        estimatedValue: siteAnalysis?.estimatedValue ?? null,
        landAreaSqm: data.land_register?.area_sqm ?? siteAnalysis?.landAreaSqm ?? null,
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
        dataSource: "백엔드 API",
        fetchedAt: new Date().toISOString(),
      });
    } catch {
      // 분석 실패해도 주소는 이미 저장됨
    } finally {
      setIsAnalyzing(false);
    }
  }, [siteAnalysis, updateSiteAnalysis]);

  const handleAddressSelect = useCallback((result: KakaoAddressResult) => {
    const entry: AddressEntry = {
      fullAddress: result.fullAddress,
      jibunAddress: result.jibunAddress,
      roadAddress: result.roadAddress,
      sido: result.sido,
      sigungu: result.sigungu,
      bname: result.bname,
      zonecode: result.zonecode,
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
    const primary = newAddresses[0];
    if (primary) {
      updateSiteAnalysis({
        estimatedValue: siteAnalysis?.estimatedValue ?? null,
        landAreaSqm: siteAnalysis?.landAreaSqm ?? null,
        zoneCode: siteAnalysis?.zoneCode ?? null,
        address: primary.fullAddress,
        pnu: siteAnalysis?.pnu ?? null,
      });

      // 자동 종합 분석 트리거 (백그라운드)
      triggerComprehensiveAnalysis(primary.fullAddress);
    }

    onChange?.(newAddresses);
  }, [single, addresses, siteAnalysis, updateSiteAnalysis, onChange]);

  const handleRemove = useCallback((index: number) => {
    const newAddresses = addresses.filter((_, i) => i !== index);
    setAddresses(newAddresses);

    // 첫 번째 주소가 변경되면 store 업데이트
    if (newAddresses.length > 0) {
      updateSiteAnalysis({
        estimatedValue: siteAnalysis?.estimatedValue ?? null,
        landAreaSqm: siteAnalysis?.landAreaSqm ?? null,
        zoneCode: siteAnalysis?.zoneCode ?? null,
        address: newAddresses[0].fullAddress,
        pnu: siteAnalysis?.pnu ?? null,
      });
    }

    onChange?.(newAddresses);
  }, [addresses, siteAnalysis, updateSiteAnalysis, onChange]);

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

      {/* 분석 중 표시 */}
      {isAnalyzing && (
        <div className="flex items-center gap-2 text-xs text-[var(--accent-strong)]">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
          토지정보 종합 분석 중...
        </div>
      )}

      {/* 분석 완료 — 기본 정보 요약 */}
      {!isAnalyzing && siteAnalysis?.zoneCode && displayAddresses.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[10px]">
          <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 font-bold text-[var(--accent-strong)]">
            {siteAnalysis.zoneCode}
          </span>
          {siteAnalysis.landAreaSqm && (
            <span className="text-[var(--text-secondary)]">
              {siteAnalysis.landAreaSqm.toLocaleString()}m²
            </span>
          )}
          {siteAnalysis.ordinance?.effectiveBcr && (
            <span className="text-[var(--text-hint)]">
              건폐율 {siteAnalysis.ordinance.effectiveBcr}% · 용적률 {siteAnalysis.ordinance.effectiveFar}%
            </span>
          )}
          {siteAnalysis.dataSource && (
            <span className="text-[var(--text-hint)]">
              ({siteAnalysis.dataSource})
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
