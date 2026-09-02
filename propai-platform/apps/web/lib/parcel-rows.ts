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
import { normalizePnu, parcelDisplayAddress } from "@/lib/pnu";

/**
 * 필지 대표 주소 정규화(공용) — 지오코딩 성공률↑ + **PNU 로 지번 파생**.
 *
 * jibunAddress 가 법정동 빠진 바레 번지("56-1"·"211-443", 엑셀 소재지·지번 분리 양식)일 때
 * fullAddress("용인시 수지구 신봉동 56-1")가 그 번지를 포함하고 더 길면 fullAddress 를 쓴다.
 * (검색분 도로명 fullAddress 는 지번을 포함하지 않으므로 이 경우 jibunAddress 유지.)
 * ★기존 `jibunAddress || fullAddress || roadAddress` 산재 로직을 대체하는 단일 규칙.
 *
 * ## ★★2026-08-21 — 지번 표시의 **세 번째 구현**이었다(사용자 재신고)
 *
 * `/ko/permits` 좌측 목록 77행이 전부 `"경기도 오산시 내삼미동"`(동 단위)으로만 보였다.
 * 같은 데이터가 메인 대시보드에서는 `"내삼미동 467-1"` 로 **정상 표시**됐다 —
 * 면적(53·684·876·843㎡)이 양쪽에서 같은 순서로 일치해 **같은 필지**임이 확증됐다.
 * 즉 데이터는 **진짜 PNU 를 갖고 있었고**, 갈린 것은 **표시 구현**이었다:
 *
 *   · 대시보드 계열 → `parcelDisplayAddress(address, pnu)`  … PNU 로 지번 파생 ○
 *   · 사통맵 계열   → `joinAddressJibun(addr, jibun, …)`     … 결합 ○
 *   · **이 함수**   → `pnu` 를 **매개변수로 받지도 않았다**   … 파생 ✗
 *
 * `#719` 는 유입부의 `||` 를 고치면서 주석에 *"구현 두 벌 금지"* 라고 적었는데,
 * 정작 **세 번째 구현이 이 파일에 있었다.** 그래서 표시층 수정이 여섯 번 반복된 것이다 —
 * 매번 **자기가 보고 있던 표면**만 고쳤기 때문이다.
 *
 * → `pnu` 를 받아 `parcelDisplayAddress` 에 위임한다. 파생 규칙은 `lib/pnu.ts` 한 곳에만 둔다
 *   (주소에 이미 지번이 있으면 그대로 두는 판정도 그쪽이 갖고 있다 — 이중 부착 없음).
 */
export function preferredEntryAddress(
  e: {
    jibunAddress?: string | null;
    fullAddress?: string | null;
    roadAddress?: string | null;
    pnu?: string | null;
  },
): string {
  const jb = (e.jibunAddress || "").trim();
  const full = (e.fullAddress || "").trim();
  const base = (full && jb && full.includes(jb) && full.length > jb.length)
    ? full
    : (jb || full || (e.roadAddress || "").trim());
  // ★PNU 가 있으면 지번을 파생한다. 주소가 이미 필지를 특정하면 그대로 둔다(파생 규칙 SSOT).
  return parcelDisplayAddress(base, e.pnu ?? null);
}

export interface ParcelRow {
  address: string;
  area_sqm?: number | null;
  zone_type?: string | null;
  farPct?: number | null;
  bcrPct?: number | null;
  farLegalPct?: number | null;
  bcrLegalPct?: number | null;
  /** 필지 경계(GeoJSON geometry) — 서버 통합집계의 인접성(contiguous) 판정용(P1 감사). */
  geometry?: unknown;
  /** 필지고유번호 — 서버 특이부지(detect_special_parcel)·통합게이트 정밀판정용(있으면 전달). */
  pnu?: string | null;
  /** 지목(land_category) — 구거·하천·학교용지 등 특이부지 감지에 필수(있으면 전달). */
  land_category?: string | null;
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
    | ReadonlyArray<{
        address?: string;
        areaSqm?: number | null;
        zoneCode?: string | null;
        pnu?: string | null;
        landCategory?: string | null;
        geometry?: unknown;
      }>
    | undefined
    | null,
): ParcelRow[] {
  if (!parcels) return [];
  return parcels
    .filter((p) => (p.areaSqm ?? 0) > 0)
    .map((p) => ({
      // ★형제 누락 봉합(2026-08-21) — 위 `entriesToParcelRows` 만 PNU 인지로 고치고
      //   **같은 파일의 이 빌더를 놓쳤다**. 이쪽은 store 경유(피커 숨김 화면)의 통합분석
      //   payload 를 만든다 — 여기서 지번이 빠지면 백엔드가 같은 동의 필지를 구분하지 못한다.
      address: parcelDisplayAddress(p.address, p.pnu ?? null),
      area_sqm: p.areaSqm ?? null,
      // store 필지가 용도지역을 보유하면 면적가중 우세용도 산정에 사용(없으면 null=면적만 통합).
      zone_type: p.zoneCode ?? null,
      farPct: null, // 실효 용적/건폐는 store ParcelData에 없음(피커 경로에서만 풀데이터)
      bcrPct: null,
      // 특이부지 감지(지목)·인접성 판정(geometry)·정밀판정(pnu)용 — 보유 시에만 전달(무날조).
      // ★유효한 것만 보낸다 — 가짜를 보내면 서버가 echo 하며 필지 보강이 조용히 죽는다.
      ...(normalizePnu(p.pnu) ? { pnu: normalizePnu(p.pnu) as string } : {}),
      ...(p.landCategory ? { land_category: p.landCategory } : {}),
      ...(p.geometry ? { geometry: p.geometry } : {}),
    }));
}

/**
 * 필지 **정체성** 주소 목록 — PNU 로 지번을 파생해 **서로 구분되는** 주소를 만든다.
 * 면적 필터는 **걸지 않는다**(표시·렌더 게이트용 = 사용자가 «고른» 모집단).
 *
 * ★2026-08-28 사용자 신고의 근원 — 여러 화면이 `parcels.map((p) => p.address)` 를 손수 썼고,
 *   스토어 주소에 지번이 없으면(예: "경기도 오산시 내삼미동") **77필지가 한 문자열로 붕괴**해
 *   백엔드 `scenario_simulator._merge`(주소 중복제거)가 **1필지 44㎡** 로 시뮬레이션했다.
 *   개발방식 19건이 거짓 '불가'로 막혔다(«도시개발사업: 44m² < 1만m²»).
 *
 * ★★`parcelAddressList` 와 **다르다** — 그쪽은 `parcelDataToRows` 의 **면적>0** 의미론을
 *   상속한다(전송용). 표시 모집단에 그걸 쓰면 «외 N필지 선택됨» 이 **줄어드는 회귀**가 된다.
 *   두 모집단은 뜻이 다르므로 함수도 둘이다.
 *
 * ★PNU 가 없으면 **구분을 지어내지 않는다**(무날조) — 그때는 백엔드가 붕괴를 고지한다.
 */
export function parcelIdentityAddresses(
  parcels:
    | ReadonlyArray<{ address?: string | null; pnu?: string | null }>
    | undefined
    | null,
): string[] {
  if (!parcels) return [];
  return parcels
    .map((p) => parcelDisplayAddress(p.address ?? "", p.pnu ?? null))
    .filter((a): a is string => Boolean(a && a.trim()));
}

/**
 * 다필지 통합을 보낼 가치가 있는지 — 2필지 이상일 때만 parcels를 첨부한다.
 * (1필지면 백엔드가 단일 경로로 처리 = 무회귀. 호출부에서 `...(parcels.length>1 ? {parcels} : {})`.)
 */
export function shouldSendParcels(rows: ParcelRow[]): boolean {
  return rows.length > 1;
}

/**
 * 주소 문자열 목록 계약(list[str])용 공용 헬퍼 — /permits/ai-analysis·의사결정브리프처럼
 * parcels를 '주소 리스트'로 받는 엔드포인트에 쓴다. parcelDataToRows의 면적>0 필터 의미론을
 * 그대로 상속(별도 필터 재구현 금지)하고, 주소가 비면 제외한다.
 */
export function parcelAddressList(
  parcels: Parameters<typeof parcelDataToRows>[0],
): string[] {
  return parcelDataToRows(parcels)
    .map((r) => r.address)
    .filter((a): a is string => Boolean(a));
}

/**
 * 분석 대상 필지 주소 목록(SSOT) — 분석 호출과 지도/등기/시뮬 렌더가 **동일 목록**을 쓰도록 공용화.
 *
 * ★배선 절단 방지(2026-07-19): 종전 permits 페이지는 분석 호출엔 store 다필지를 포함하고
 *   렌더 자식엔 대표주소만 넘겨, 12필지 선택 시 구획도·개발방식·등기가 1필지만 표시했다.
 *   규칙: (1)수동 재검색(extra)이 있으면 그것을 다필지로 (2)없으면 store 다필지(siteAnalysis.parcels)로
 *   폴백 — 컨텍스트 진입만으로 무수동 다필지 분석이 되도록. target(대표)은 항상 선두, 중복 제거·순서 보존.
 */
export function buildAnalysisParcelAddrs(
  target: string,
  extra: string[],
  storeParcels: Parameters<typeof parcelDataToRows>[0],
): string[] {
  const t = (target || "").trim();
  if (!t) return [];
  const extraTrimmed = extra.map((s) => s.trim()).filter(Boolean);
  const storeAddrs = extraTrimmed.length > 0 ? [] : parcelAddressList(storeParcels);
  // 중복 제거(target·extra 간, store와의 중첩 모두) — 순서 보존.
  const seen = new Set<string>();
  const out: string[] = [];
  for (const a of [t, ...extraTrimmed, ...storeAddrs]) {
    if (!seen.has(a)) { seen.add(a); out.push(a); }
  }
  return out;
}
