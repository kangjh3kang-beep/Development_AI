/**
 * "적용 건축개요" 소스 혼입 방지(단일 파생점 — 백로그②, R1 리뷰로 원자화) — 순수 코어.
 *
 * 연면적·건폐율·용적률을 항상 "같은 소스"로 함께 뽑는다(부분 채택 금지). 라이브 실측
 * (2026-07-22): CadBimIntegrationPanel의 "적용 건축개요" 패널이 연면적은 designData
 * (선택한 개요·목표값)로, 건폐율/용적률은 백엔드 /mass 응답(매스엔진 실현값)으로 따로
 * 조회해 "연면적 1,216㎡(304㎡×4F) vs 그 옆 건폐율/용적률을 역산하면 670.32㎡
 * (13.3×12.6m×4F)"처럼 한 패널 안에서 서로 다른 소스가 섞이는 결함이 있었다.
 *
 * ★R1 리뷰 MEDIUM-1: 처음엔 필드별 독립 `??` 폴백으로 고쳤으나, 백엔드 명시치수·최종폴백
 * 분기(design_v61.py _resolve_mass_uncached)는 total_floor_area_sqm만 채우고 bcr_pct/
 * far_pct는 None이라 "연면적=m·비율=designData"라는 거울상 혼입이 실재 경로로 재발한다.
 * 그래서 세 필드가 "모두 m에 있을 때만" m을 통째로 채택하고, 하나라도 없으면 셋 다
 * designData로 통째로 폴백하는 원자적(all-or-nothing) 판정으로 교체했다(부분 혼입 구조 불가).
 * m이 없는 호출(massGeom 재사용·완전폴백 분기)은 m=null로 넘겨 항상 designData로 통일한다.
 */

/** 백엔드 /mass·/bim/generate 응답에서 필요한 필드만(느슨한 구조 타입). */
export interface MassOverviewSource {
  total_floor_area_sqm?: number | null;
  bcr_pct?: number | null;
  far_pct?: number | null;
}

/** designData(선택한 건축개요·목표값)에서 필요한 필드만. */
export interface DesignDataOverviewSource {
  totalGfaSqm?: number | null;
  bcr?: number | null;
  far?: number | null;
}

export interface AppliedOverview {
  gfa: number | null;
  bcr: number | null;
  far: number | null;
}

/** m(백엔드 매스 응답)에 연면적·건폐율·용적률 세 값이 모두 있을 때만 m을 통째로 채택하고,
 *  하나라도 없으면(null/undefined) 셋 다 designData로 통째로 폴백한다(원자적 — 부분 혼입 불가). */
export function resolveAppliedOverview(
  m: MassOverviewSource | null | undefined,
  designData: DesignDataOverviewSource | null | undefined,
): AppliedOverview {
  const hasMass =
    !!m && m.total_floor_area_sqm != null && m.bcr_pct != null && m.far_pct != null;
  if (hasMass) {
    return { gfa: m!.total_floor_area_sqm ?? null, bcr: m!.bcr_pct ?? null, far: m!.far_pct ?? null };
  }
  return {
    gfa: designData?.totalGfaSqm ?? null,
    bcr: designData?.bcr ?? null,
    far: designData?.far ?? null,
  };
}
