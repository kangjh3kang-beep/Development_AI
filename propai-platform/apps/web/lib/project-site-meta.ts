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
export function buildSiteMetaPatch(
  site: SiteAnalysisData | null | undefined,
  meta: ProjectSiteMeta,
): Partial<SiteAnalysisData> {
  const patch: Partial<SiteAnalysisData> = {};
  if ((site?.landAreaSqm ?? null) == null && meta.total_area_sqm != null && meta.total_area_sqm > 0) {
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
