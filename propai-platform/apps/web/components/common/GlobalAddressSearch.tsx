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

export interface AddressEntry {
  fullAddress: string;
  jibunAddress: string;
  roadAddress: string;
  sido: string;
  sigungu: string;
  bname: string;
  zonecode: string;
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
  const updateSiteAnalysis = useProjectContextStore((s) => s.updateSiteAnalysis);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

  // 기존 siteAnalysis에 주소가 있으면 초기값으로 표시
  const displayAddresses = addresses.length > 0 ? addresses : (
    siteAnalysis?.address ? [{ fullAddress: siteAnalysis.address, jibunAddress: "", roadAddress: "", sido: "", sigungu: "", bname: "", zonecode: "" }] : []
  );

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
              {addr.sido && (
                <span className="text-[10px] text-[var(--text-hint)] flex-shrink-0">
                  {addr.sido} {addr.sigungu}
                </span>
              )}
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

      {/* 다필지 요약 */}
      {!single && displayAddresses.length > 1 && (
        <p className="text-[10px] text-[var(--text-hint)]">
          {displayAddresses.length}개 필지 등록됨 — 합필 분석 시 전체 면적이 합산됩니다.
        </p>
      )}
    </div>
  );
}
