"use client";

/**
 * ParcelPickerMap compatibility wrapper.
 *
 * 새 지도 구현은 SatongMultiMap 하나로 모읍니다. 기존 화면과 타입 import를
 * 깨지 않기 위해 예전 컴포넌트명은 그대로 export하되 내부는 단일 엔진을 사용합니다.
 */

export {
  SatongMultiMap as ParcelPickerMap,
  type ParcelAtPointResult,
  type SatongMultiMapProps as ParcelPickerMapProps,
} from "@/components/map/SatongMultiMap";

export { SatongMultiMap as default } from "@/components/map/SatongMultiMap";
