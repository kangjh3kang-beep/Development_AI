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
