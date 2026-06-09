/**
 * 카카오맵 JS SDK 동적 로더(단일 인스턴스).
 *
 * - 키: NEXT_PUBLIC_KAKAO_MAP_KEY (빌드타임 인라인). JavaScript 키 사용.
 * - autoload=false + kakao.maps.load(cb)로 안전 초기화(SDK 객체 준비 보장).
 * - 카카오 콘솔 "플랫폼 ▸ Web ▸ 사이트 도메인"에 현재 도메인이 등록돼 있어야
 *   SDK가 동작한다(미등록 시 지도 미표시). 좌표계는 WGS84(위경도) — 변환 불필요.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

let kakaoLoading: Promise<void> | null = null;

const DUMMY_KEYS = new Set(["", "your-kakao-map-key", "changeme", "dummy"]);

export function kakaoMapKey(): string {
  return (process.env.NEXT_PUBLIC_KAKAO_MAP_KEY || "").trim();
}

export function loadKakaoMap(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  const w = window as any;
  if (w.kakao?.maps?.LatLng) return Promise.resolve();
  if (kakaoLoading) return kakaoLoading;

  const key = kakaoMapKey();
  kakaoLoading = new Promise<void>((resolve, reject) => {
    if (DUMMY_KEYS.has(key.toLowerCase())) {
      reject(new Error("카카오맵 키가 설정되지 않았습니다"));
      return;
    }
    const onReady = () => {
      const k = (window as any).kakao;
      if (k?.maps?.load) k.maps.load(() => resolve());
      else reject(new Error("카카오맵 SDK 초기화 실패"));
    };
    const existing = document.querySelector("script[data-kakao-map]") as HTMLScriptElement | null;
    if (existing) {
      if ((window as any).kakao?.maps) onReady();
      else existing.addEventListener("load", onReady);
      return;
    }
    const script = document.createElement("script");
    // autoload=false: 스크립트 로드 후 kakao.maps.load()로 명시 초기화.
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${key}&autoload=false`;
    script.async = true;
    script.setAttribute("data-kakao-map", "1");
    script.onload = onReady;
    script.onerror = () => {
      kakaoLoading = null; // 재시도 허용
      reject(new Error("카카오맵 SDK 로드 실패"));
    };
    document.head.appendChild(script);
  });
  return kakaoLoading;
}
