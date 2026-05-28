"use client";

/**
 * 카카오 주소 검색 컴포넌트.
 *
 * Daum Postcode API를 사용하여 구주소/도로명 주소를 검색합니다.
 * API 키 불필요, 무료 서비스입니다.
 *
 * @see https://postcode.map.kakao.com/guide
 */

import { useCallback, useEffect, useRef, useState } from "react";

/* ── 카카오 주소 검색 결과 타입 ── */
interface DaumPostcodeData {
  zonecode: string;        // 우편번호
  address: string;         // 기본 주소 (도로명 또는 지번)
  addressType: "R" | "J";  // R: 도로명, J: 지번
  roadAddress: string;     // 도로명 주소
  jibunAddress: string;    // 지번 주소
  bname: string;           // 법정동/법정리명
  buildingName: string;    // 건물명
  apartment: "Y" | "N";    // 아파트 여부
  sido: string;            // 시도명
  sigungu: string;         // 시군구명
  bname1: string;          // 법정동 첫 번째 부분
  bname2: string;          // 법정동 두 번째 부분
  userSelectedType: "R" | "J"; // 사용자가 선택한 주소 유형
}

/* ── Props ── */
export interface KakaoAddressResult {
  /** 전체 주소 (도로명 우선, 없으면 지번) */
  fullAddress: string;
  /** 도로명 주소 */
  roadAddress: string;
  /** 지번 주소 */
  jibunAddress: string;
  /** 우편번호 */
  zonecode: string;
  /** 시도 */
  sido: string;
  /** 시군구 */
  sigungu: string;
  /** 법정동 */
  bname: string;
  /** 건물명 */
  buildingName: string;
}

interface KakaoAddressSearchProps {
  /** 주소 선택 시 콜백 */
  onSelect: (result: KakaoAddressResult) => void;
  /** 현재 주소 값 (제어 컴포넌트용) */
  value?: string;
  /** placeholder */
  placeholder?: string;
  /** 추가 CSS 클래스 */
  className?: string;
  /** 비활성화 */
  disabled?: boolean;
}

/* ── Daum Postcode 스크립트 로드 ── */
let scriptLoaded = false;
let scriptLoading = false;
const loadCallbacks: Array<() => void> = [];

function loadDaumPostcodeScript(): Promise<void> {
  return new Promise((resolve) => {
    if (scriptLoaded) {
      resolve();
      return;
    }

    loadCallbacks.push(resolve);

    if (scriptLoading) return;
    scriptLoading = true;

    const script = document.createElement("script");
    script.src = "//t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js";
    script.async = true;
    script.onload = () => {
      scriptLoaded = true;
      scriptLoading = false;
      loadCallbacks.forEach((cb) => cb());
      loadCallbacks.length = 0;
    };
    document.head.appendChild(script);
  });
}

/* ── 컴포넌트 ── */
export function KakaoAddressSearch({
  onSelect,
  value = "",
  placeholder = "주소를 검색하세요 (클릭하면 검색창이 열립니다)",
  className = "",
  disabled = false,
}: KakaoAddressSearchProps) {
  const [displayValue, setDisplayValue] = useState(value);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 외부 value 변경 시 동기화
  useEffect(() => {
    setDisplayValue(value);
  }, [value]);

  /* ── 카카오 주소 검색 팝업 열기 ── */
  const openSearch = useCallback(async () => {
    if (disabled) return;

    await loadDaumPostcodeScript();

    const daum = (window as any).daum;
    if (!daum?.Postcode) return;

    setIsOpen(true);

    new daum.Postcode({
      oncomplete: (data: DaumPostcodeData) => {
        // 사용자가 선택한 주소 유형에 따라 전체 주소 결정
        let fullAddress = data.userSelectedType === "R" ? data.roadAddress : data.jibunAddress;

        // 건물명 추가
        if (data.buildingName) {
          fullAddress += ` (${data.buildingName})`;
        }

        const result: KakaoAddressResult = {
          fullAddress,
          roadAddress: data.roadAddress,
          jibunAddress: data.jibunAddress,
          zonecode: data.zonecode,
          sido: data.sido,
          sigungu: data.sigungu,
          bname: data.bname || data.bname2,
          buildingName: data.buildingName,
        };

        setDisplayValue(fullAddress);
        setIsOpen(false);
        onSelect(result);
      },
      onclose: () => {
        setIsOpen(false);
      },
      width: "100%",
      height: "100%",
    }).embed(containerRef.current);
  }, [disabled, onSelect]);

  return (
    <div className="space-y-2">
      {/* 주소 입력/표시 필드 */}
      <div
        onClick={openSearch}
        className={`
          relative flex items-center gap-3 rounded-xl border border-[var(--line)]
          bg-[var(--surface-soft)] px-4 py-3 cursor-pointer
          hover:border-[var(--accent-strong)] hover:bg-[var(--surface-muted)]
          transition-all ${disabled ? "opacity-50 cursor-not-allowed" : ""}
          ${className}
        `}
      >
        {/* 검색 아이콘 */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-[var(--accent-strong)] flex-shrink-0"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.3-4.3" />
        </svg>

        {/* 주소 텍스트 */}
        {displayValue ? (
          <span className="text-sm font-medium text-[var(--text-primary)] truncate">
            {displayValue}
          </span>
        ) : (
          <span className="text-sm text-[var(--text-hint)]">{placeholder}</span>
        )}

        {/* 변경 버튼 */}
        {displayValue && (
          <span className="ml-auto text-[10px] text-[var(--accent-strong)] font-bold flex-shrink-0">
            변경
          </span>
        )}
      </div>

      {/* 카카오 주소 검색 임베드 영역 */}
      {isOpen && (
        <div className="rounded-xl border border-[var(--line)] overflow-hidden shadow-lg">
          <div
            ref={containerRef}
            style={{ width: "100%", height: "400px" }}
          />
        </div>
      )}
    </div>
  );
}
