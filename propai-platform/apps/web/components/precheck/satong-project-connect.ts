"use client";

import { addressRegionMismatch } from "@/store/useProjectContextStore";

/** 선택 필지 → 새 프로젝트 이름 파생. 대표(첫) 필지 주소의 마지막 두 토큰(동·지번)을 쓰고,
 *  2필지 이상이면 "외 N필지"를 붙인다. 예: "고기동 689 외 8필지".
 *  주소가 없으면 null(무날조 — 호출측이 생성 차단·안내). */
export function deriveProjectNameFromParcels(
  parcels: Array<{ address: string }>,
): string | null {
  const address = (parcels[0]?.address ?? "").trim();
  if (!address) return null;
  const tokens = address.split(/\s+/).filter(Boolean);
  const base = tokens.slice(-2).join(" ");
  return parcels.length > 1 ? `${base} 외 ${parcels.length - 1}필지` : base;
}

/** 기존 프로젝트 연결 상태에서 새로 추가되는 필지가 프로젝트 주소와 지역(시군구·법정동)
 *  단위로 불일치인지 — 번지 차이는 무시한다. addressRegionMismatch(공용, store/
 *  useProjectContextStore export)를 그대로 재사용해 산식을 단일화한다. 번지까지 엄격한
 *  addressTokenMismatch를 쓰면 지도에서 인접 필지(같은 동, 다른 번지)를 추가하는 정상
 *  워크플로우가 '불일치'로 오판돼 가드가 과발화한다 — 그래서 지역 단위 비교만 쓴다.
 *  둘 중 하나라도 주소가 없으면 false(보수적). */
export function selectionMismatchesProject(
  projectAddress: string | null | undefined,
  incomingAddress: string | null | undefined,
): boolean {
  if (!projectAddress?.trim() || !incomingAddress?.trim()) return false;
  return addressRegionMismatch(projectAddress, incomingAddress);
}
