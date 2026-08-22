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
import { createPortal } from "react-dom";

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
  bcode: string;           // 법정동 코드 (10자리)
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
  /** 법정동 코드 (10자리) — PNU 구성에 사용 */
  bcode: string;
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
  /** ★외부 제어 모드 — open이 정의되면 내부 박스 트리거를 숨기고 부모가 팝업 개폐를 제어한다.
   *   (통합 검색에서 '건물명·아파트로 찾기' 보조 링크로 다음 팝업만 열 때 사용) */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
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
    // ★`//` 프로토콜 상대 URL 이었다 — 명시적으로 https 를 쓴다(다운그레이드 여지 제거).
    script.src = "https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js";
    script.async = true;
    script.onload = () => {
      scriptLoaded = true;
      scriptLoading = false;
      loadCallbacks.forEach((cb) => cb());
      loadCallbacks.length = 0;
    };
    // ★종전에 `onerror` 가 **없었다.** 그래서 스크립트를 못 받으면
    //   ①쌓아 둔 `resolve` 가 영원히 안 불려 `await` 가 **무한 대기**하고
    //   ②`scriptLoading` 이 true 로 굳어 **페이지를 새로고침하기 전엔 재시도도 못 했다.**
    //   화면에는 빈 상자만 남고 아무 안내가 없었다 — 이 저장소가 반복해서 데인 "조용한 실패".
    //   정답 기준선은 `lib/kakao-map.ts` 다: 상태를 되돌려 **다음 시도를 허용**한다.
    script.onerror = () => {
      scriptLoading = false;
      script.remove(); // 실패한 태그를 남기지 않는다(다음 시도가 새로 붙인다).
      loadCallbacks.forEach((cb) => cb()); // 대기자를 깨운다 — 무한 대기 방지.
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
  open: openProp,
  onOpenChange,
}: KakaoAddressSearchProps) {
  const [displayValue, setDisplayValue] = useState(value);
  const [openState, setOpenState] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  // 외부 제어 모드(open prop 정의) ↔ 내부 상태 모드. 기존 사용처는 prop 미전달=내부 모드(하위호환).
  const controlled = openProp !== undefined;
  const open = controlled ? !!openProp : openState;
  const setOpen = useCallback((v: boolean) => {
    if (controlled) onOpenChange?.(v);
    else setOpenState(v);
  }, [controlled, onOpenChange]);

  // 외부 value 변경 시 동기화
  useEffect(() => {
    setDisplayValue(value);
  }, [value]);

  const openSearch = useCallback(() => {
    if (!disabled) setOpen(true);
  }, [disabled, setOpen]);

  /* ── 모바일 안전: 별도 팝업(.open) 대신 인라인 임베드(.embed).
        .open() 은 모바일에서 oncomplete 콜백이 원래 페이지로 안정적으로 돌아오지 않아
        선택값이 입력에 반영되지 않는다. embed 는 같은 페이지 컨텍스트에서 동작. ── */
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      await loadDaumPostcodeScript();
      if (cancelled || !boxRef.current) return;
      const daum = (window as any).daum;
      if (!daum?.Postcode) {
        // ★종전엔 여기서 **아무 말 없이** 반환해 빈 상자만 남았다.
        boxRef.current.innerHTML =
          '<p style="padding:16px;font-size:12px;line-height:1.6">' +
          "주소 검색 서비스를 불러오지 못했습니다.<br/>네트워크를 확인하고 다시 열어 주세요." +
          "</p>";
        return;
      }
      boxRef.current.innerHTML = "";
      new daum.Postcode({
        oncomplete: (data: DaumPostcodeData) => {
          let fullAddress = data.userSelectedType === "R" ? data.roadAddress : data.jibunAddress;
          if (data.buildingName) fullAddress += ` (${data.buildingName})`;
          const result: KakaoAddressResult = {
            fullAddress,
            roadAddress: data.roadAddress,
            jibunAddress: data.jibunAddress,
            zonecode: data.zonecode,
            sido: data.sido,
            sigungu: data.sigungu,
            bname: data.bname || data.bname2,
            buildingName: data.buildingName,
            bcode: data.bcode ?? "",
          };
          setDisplayValue(fullAddress);
          onSelect(result);
          setOpen(false);
        },
        width: "100%",
        height: "100%",
      }).embed(boxRef.current, { autoClose: false });
    })();
    return () => { cancelled = true; };
  }, [open, onSelect, setOpen]);

  return (
    <div className="space-y-2">
      {/* 주소 입력/표시 필드 — 외부 제어 모드(open prop)에선 숨김(부모가 별도 버튼으로 팝업을 연다) */}
      {!controlled && (
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
      )}

      {/* 주소 검색 오버레이 — Portal로 body에 렌더.
          (backdrop-blur/transform 조상이 있으면 fixed가 그 안에 갇혀 검색창이
           프레임에 클립되던 문제 근본 해결: 조상 컨테이닝블록 탈출) */}
      {open && typeof document !== "undefined" && createPortal(
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/60 p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="flex w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)] shadow-[var(--shadow-lg)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[var(--line)] px-4 py-3">
              <span className="text-sm font-bold text-[var(--text-primary)]">주소 검색</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
                aria-label="닫기"
              >
                ✕
              </button>
            </div>
            {/* Kakao embed는 height:100%를 쓰므로 컨테이너에 '명시적 높이'가 있어야
                검색창이 잘리지 않는다(flex-1만으론 퍼센트 높이 미해소). */}
            <div
              ref={boxRef}
              className="w-full"
              style={{ height: "min(70vh, 520px)" }}
            />
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
