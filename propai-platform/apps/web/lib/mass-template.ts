/**
 * 매스 백본 템플릿 선택 유틸 — BuildableMassPreview의 건축물종류 선택 로직(순수·테스트가능).
 *
 * GET /api/v1/mass-templates 응답(표본수 내림차순)에서 건폐·용적이 모두 유효한 종류만 골라
 * 드롭다운 후보로 쓰고, 선택 종류(없으면 대표=첫)를 고른다. 가짜 규모 방지(결측 종류 제외).
 */

export type MassTemplate = {
  building_type: string;
  sample_count: number;
  median_bcr_pct: number | null;
  median_far_pct: number | null;
  median_floors: number | null;
};

/** 건폐·용적 중앙값이 모두 유효(>0)한 템플릿만(가짜 규모 방지). 서버 정렬(표본수 내림차순)을 보존. */
export function validMassTemplates(templates: MassTemplate[] | null | undefined): MassTemplate[] {
  return (templates ?? []).filter(
    (t) => (t.median_bcr_pct ?? 0) > 0 && (t.median_far_pct ?? 0) > 0,
  );
}

/** 선택 종류의 템플릿(미선택/미존재 시 대표=첫). 유효 템플릿이 없으면 null. */
export function selectMassTemplate(
  valid: MassTemplate[],
  buildingType: string | null,
): MassTemplate | null {
  if (valid.length === 0) return null;
  if (buildingType) {
    const matched = valid.find((t) => t.building_type === buildingType);
    if (matched) return matched;
  }
  return valid[0];
}
