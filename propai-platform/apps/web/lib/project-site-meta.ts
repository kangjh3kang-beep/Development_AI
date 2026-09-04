import type { SiteAnalysisData } from "@/store/useProjectContextStore";

/** 프로젝트 백엔드 meta 중 siteAnalysis 보강에 쓰는 부분(ProjectContextBinder). */
export interface ProjectSiteMeta {
  address?: string;
  total_area_sqm?: number | null;
  zone_type?: string | null;
  pnu_codes?: string[] | null;
}

/**
 * 프로젝트 meta → siteAnalysis 보강 패치(빈 필드만 채움, 사용자/분석 값은 보존).
 *
 * ★U1: 기존엔 landAreaSqm·zoneCode·pnu만 채우고 **address를 누락**해, 스냅샷 복원이
 * address 없는 siteAnalysis로 덮은 경우 siteAnalysis.address가 비어 통합분석 게이트
 * (hasContext = address||pnu)가 "부지 필요"로 막혔다(상단 주소바는 레코드 출처라 보임).
 * meta.address를 빈 경우에만 보강해 SSOT와 표시를 일치시키고 실분석을 가능케 한다.
 *
 * 빈 판정만 채우므로 updateSiteAnalysis(merge·provenance)와 함께 사용자 수정값을 덮지 않는다.
 */
export interface SiteMetaPatchOptions {
  /** 이 프로젝트에 **저장된 분석**(analysis_snapshot.siteAnalysis)이 있었는가.
   *  ★면적 보강의 유일한 판별자다 — 아래 주석 참조. 미지정(구 호출부)은 종전 동작. */
  hasStoredAnalysis?: boolean;
}

export function buildSiteMetaPatch(
  site: SiteAnalysisData | null | undefined,
  meta: ProjectSiteMeta,
  opts?: SiteMetaPatchOptions,
): Partial<SiteAnalysisData> {
  const patch: Partial<SiteAnalysisData> = {};
  // ★유령 면적 부활 차단 — 자가치유가 **세 줄 뒤에서** 되돌려지고 있었다.
  //
  //   ProjectContextBinder 의 같은 useEffect 안에서:
  //     applyRemoteSnapshot(...)  → healPhantomAreaAggregates 가 landAreaSqm 을 null 로 치운다
  //     buildSiteMetaPatch(...)   → 여기서 레코드 total_area_sqm 으로 **되살렸다**
  //   게다가 치유기가 landAreaSqmTotal·repLandAreaSqm 까지 비우므로
  //   hasPhantomAreaAggregates 가 **재검출하지 못한다**(2차 방어선이 눈이 먼다).
  //   실물: 필지 0건인데 레코드 면적 164,823㎡ 인 프로젝트가 열 때마다 유령을 되찾았다.
  //
  //   ★판별자: **저장된 분석이 있는데 면적이 비어 있다면, 아직 못 채운 게 아니라 "치워진 것"이다.**
  //     - 저장된 분석 없음(갓 만든 프로젝트) → 종전대로 보강한다. 안 그러면 정상 신규
  //       프로젝트가 면적을 잃는다(이 처방의 첫 설계는 그 회귀를 만들어 기각했다).
  //     - 저장된 분석 있음 + 면적 비어 있음 → **보강하지 않는다.** 치유기의 결정을 존중한다.
  //   ★address·zoneCode·pnu 보강은 건드리지 않는다 — U1(부지 게이트) 계약 불변.
  const areaWasCleared = opts?.hasStoredAnalysis === true;
  if (
    (site?.landAreaSqm ?? null) == null &&
    meta.total_area_sqm != null &&
    meta.total_area_sqm > 0 &&
    !areaWasCleared
  ) {
    patch.landAreaSqm = meta.total_area_sqm;
  }
  if (!site?.zoneCode && meta.zone_type) {
    patch.zoneCode = meta.zone_type;
  }
  if (!site?.pnu && meta.pnu_codes && meta.pnu_codes.length > 0) {
    patch.pnu = meta.pnu_codes[0];
  }
  if (!site?.address && meta.address) {
    patch.address = meta.address; // U1: 부지 게이트 통과 위해 address 보강
  }
  return patch;
}
