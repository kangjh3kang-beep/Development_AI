/**
 * 다필지 → 백엔드 통합집계 입력행(공용 계약).
 *
 * 백엔드 `ComprehensiveAnalysisService._integrated_context`(면적가중 통합)가 읽는 키와 1:1로 맞춘
 * 단일 출처다. 시장보고서·규제·인허가·법규 등 '다필지 통합이 필요한 모든 요청'이 이 함수를 거쳐
 * parcels를 만들어 보내면, 한 곳만 고쳐도 전 페이지의 다필지 계약이 따라온다(전역 전파방지).
 *
 * 키 규약: area_sqm(면적), zone_type(용도지역), farPct/bcrPct(실효 용적/건폐 — 조례반영),
 *          farLegalPct/bcrLegalPct(법정상한 — 보조).
 */
import type { AddressEntry } from "@/components/common/GlobalAddressSearch";

/**
 * 필지 대표 주소 정규화(공용) — 지오코딩 성공률↑.
 *
 * jibunAddress 가 법정동 빠진 바레 번지("56-1"·"211-443", 엑셀 소재지·지번 분리 양식)일 때
 * fullAddress("용인시 수지구 신봉동 56-1")가 그 번지를 포함하고 더 길면 fullAddress 를 쓴다.
 * (검색분 도로명 fullAddress 는 지번을 포함하지 않으므로 이 경우 jibunAddress 유지.)
 * ★기존 `jibunAddress || fullAddress || roadAddress` 산재 로직을 대체하는 단일 규칙.
 */
export function preferredEntryAddress(
  e: { jibunAddress?: string | null; fullAddress?: string | null; roadAddress?: string | null },
): string {
  const jb = (e.jibunAddress || "").trim();
  const full = (e.fullAddress || "").trim();
  if (full && jb && full.includes(jb) && full.length > jb.length) return full;
  return jb || full || (e.roadAddress || "").trim();
}

export interface ParcelRow {
  address: string;
  area_sqm?: number | null;
  zone_type?: string | null;
  farPct?: number | null;
  bcrPct?: number | null;
  farLegalPct?: number | null;
  bcrLegalPct?: number | null;
}

/** 주소검색 결과(AddressEntry[])를 통합집계 입력행으로. 면적>0인 필지만 포함한다. */
export function entriesToParcelRows(entries: AddressEntry[]): ParcelRow[] {
  return entries
    .filter((e) => (e.areaSqm ?? 0) > 0)
    .map((e) => ({
      address: preferredEntryAddress(e),
      area_sqm: e.areaSqm,
      zone_type: e.zoneCode ?? null,
      farPct: e.farPct ?? null, // 실효(조례 반영)
      bcrPct: e.bcrPct ?? null,
      farLegalPct: e.farLegalPct ?? null, // 법정상한(보조)
      bcrLegalPct: e.bcrLegalPct ?? null,
    }));
}

/**
 * 프로젝트 컨텍스트의 다필지(siteAnalysis.parcels: 면적·주소만 보유)를 통합집계 입력행으로.
 * 피커를 거치지 않은 프로젝트 스코프 화면(피커 숨김)에서 통합 '면적'을 백엔드로 보내는 폴백.
 * zone/far/bcr는 없으므로 null — 백엔드는 면적만 통합하고 용도지역은 기존값을 보존한다(graceful).
 */
export function parcelDataToRows(
  parcels:
    | ReadonlyArray<{ address?: string; areaSqm?: number | null; zoneCode?: string | null }>
    | undefined
    | null,
): ParcelRow[] {
  if (!parcels) return [];
  return parcels
    .filter((p) => (p.areaSqm ?? 0) > 0)
    .map((p) => ({
      address: p.address || "",
      area_sqm: p.areaSqm ?? null,
      // store 필지가 용도지역을 보유하면 면적가중 우세용도 산정에 사용(없으면 null=면적만 통합).
      zone_type: p.zoneCode ?? null,
      farPct: null, // 실효 용적/건폐는 store ParcelData에 없음(피커 경로에서만 풀데이터)
      bcrPct: null,
    }));
}

/**
 * 다필지 통합을 보낼 가치가 있는지 — 2필지 이상일 때만 parcels를 첨부한다.
 * (1필지면 백엔드가 단일 경로로 처리 = 무회귀. 호출부에서 `...(parcels.length>1 ? {parcels} : {})`.)
 */
export function shouldSendParcels(rows: ParcelRow[]): boolean {
  return rows.length > 1;
}
