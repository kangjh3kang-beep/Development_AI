import type { SiteAnalysisData } from "@/store/useProjectContextStore";

/**
 * 유효 대지면적(㎡) — 다필지면 통합면적 우선, 아니면 단일/대표 면적.
 *
 * 왜 필요한가(쉬운 설명):
 * 다필지(여러 필지를 합친 부지)를 분석하면 "통합 면적"이 진짜 사업 면적이다.
 * 그런데 한 필지(대표 번지)만 다시 조회하는 분석이 나중에 실행되면
 * 대표 면적(작은 값)이 통합 면적을 덮어써서, 설계·수지가 부지를 너무 작게 보는
 * 버그가 생긴다. 통합 면적(landAreaSqmTotal)은 한 곳에서만 기록되어 안정적으로
 * 보존되므로, 읽는 쪽에서 "다필지면 통합 우선"으로 읽으면 덮어쓰기 경합과 무관하게
 * 항상 정확한 면적을 얻는다(경합 면역).
 *
 * 다운스트림(설계·수지·적산·금융·심의·법률 등)은 반드시 이 헬퍼로 면적을 읽어
 * 단일 PNU 분석이 landAreaSqm을 대표값으로 덮어써도 통합면적이 보존되게 한다.
 * 무목업: 둘 다 없으면 null(0 강제 금지).
 */
export function effectiveLandAreaSqm(
  sa: SiteAnalysisData | null | undefined,
): number | null {
  if (!sa) return null;
  const total = sa.landAreaSqmTotal;
  const isMulti = (sa.parcelCount ?? 1) > 1;
  if (isMulti && typeof total === "number" && total > 0) return total;
  return typeof sa.landAreaSqm === "number" ? sa.landAreaSqm : null;
}

/**
 * 필지 집합 일관성 — 다필지 통합 메타가 '완전하게' 채워졌는지 검사한다(effectiveLandAreaSqm의 짝).
 *
 * 왜 필요한가(쉬운 설명):
 * 다필지(여러 필지) 부지는 비동기 보강(enrichParcels)이 끝나야 통합값(필지목록 parcels[],
 * 통합면적 landAreaSqmTotal)이 모두 채워진다. 보강이 끝나기 전에 신규 프로젝트로 캡처되면
 * 대표 1필지(작은 면적)만 진실원천이 되는 회귀가 생긴다(12필지→1필지 107㎡ 버그).
 * 제출 완전성 게이트가 이 헬퍼로 "필지 수 = 필지목록 길이 && 다필지면 통합면적>0"을 확인해
 * 부분상태 캡처를 막는다(무목업: 미완이면 진행 차단, 가짜 통합값 생성 금지).
 *
 * 판정(spec): parcelCount === parcels.length && (parcelCount <= 1 || landAreaSqmTotal > 0)
 * - 단일/미검색(parcelCount 미설정·parcels 0~1) → 통합 메타가 애초에 없으므로 일관(true) → 즉시 제출 허용(무회귀).
 * - 다필지(parcelCount ≥ 2): 필지목록이 같은 길이로 채워지고 통합면적이 양수여야 일관(true).
 */
export function isParcelSetConsistent(
  sa: SiteAnalysisData | null | undefined,
): boolean {
  if (!sa) return true; // 부지분석 미시작 → 게이트는 다른 검증(주소·이름 필수)에 위임.
  const count = sa.parcelCount ?? (sa.parcels?.length ?? 1);
  const parcelsLen = sa.parcels?.length ?? 0;
  // 단일필지(≤1): parcels 배열이 비어있어도(미기록) 일관 — 통합 메타가 없는 정상 단일 상태.
  if (count <= 1) return true;
  // 다필지: 필지목록 길이가 count와 일치하고 통합면적이 양수여야 완전한 통합 상태.
  const total = sa.landAreaSqmTotal;
  return parcelsLen === count && typeof total === "number" && total > 0;
}
