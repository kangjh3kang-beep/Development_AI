import type { SiteAnalysisData } from "@/store/useProjectContextStore";

/**
 * `siteAnalysis` 의 **불변식**과 그 자가치유.
 *
 * 왜 필요한가(쉬운 설명):
 * 여러 필지를 고르면 시스템은 "합계 면적"·"대표 면적"·"필지 수"·"필지 목록"을 **함께** 적는다.
 * 이 값들은 같은 목록에서 나온 한 묶음이라, 목록이 없어졌는데 합계만 남는 상태는 **있을 수 없다**.
 * 그런데 실제로 그런 저장본이 생겼다 — 목록은 0건인데 합계는 164,823㎡ 라고 적혀 있었다.
 * 그러면 화면이 "단일 필지입니다"라고 하면서 동시에 그 면적을 보여 주고, 그 면적이 설계·수지로
 * 흘러 연면적·공사비·총사업비를 통째로 부풀린다.
 *
 * ★라이브 실측(2026-08-23): 프로젝트 스냅샷 54건 중 **2건**이 이 형상이었다.
 *     `1dad85f0` "모산동 123-1 외 6필지" — `parcels=[] · parcelCount=0` 인데
 *     `landAreaSqm=landAreaSqmTotal=164823 · repLandAreaSqm=3836`(대표필지의 **43배**).
 *   사용자 신고 *"다필지를 넣었는데 단필지로 분석된다"* 가 이 형상에서 나왔다.
 *
 * ★근본은 쓰기/지우기 **비대칭**이었고 그것은 별도로 고쳤다
 *   (`satong-map-selection.ts` 의 `emptySelectionSiteAnalysisPatch`).
 *   이 파일은 **두 번째 방어선**이다 — 이미 저장된 오염본이 다시 흘러들거나,
 *   앞으로 다른 경로가 같은 형상을 만들어도 화면·계산에 닿지 않게 한다.
 */

/**
 * 면적 집계는 **필지 목록에서만** 만들어진다 — 목록 없이 집계만 있으면 그 집계는 유령이다.
 *
 * 근거(전수 확인): `landAreaSqmTotal`·`repLandAreaSqm` 을 쓰는 곳은 두 군데뿐이고
 * (`GlobalAddressSearch` 의 `enrichParcels`, `satong-map-selection` 의 `selectionToSiteAnalysisPatch`),
 * **둘 다 `parcels` 를 같은 객체에서 함께 쓴다**. 따라서
 *   "`landAreaSqmTotal` 또는 `repLandAreaSqm` 이 있다" ⟹ "`parcels` 가 있다"
 * 가 구성상 성립한다. 이 함의가 깨진 상태 = 오염.
 *
 * ★단일필지 분석은 `landAreaSqm` **만** 쓰고 `Total`/`rep` 은 쓰지 않는다 —
 *   그래서 이 판정은 정상 단일필지를 건드리지 않는다(위양성 없음).
 */
export function hasPhantomAreaAggregates(
  sa: Partial<SiteAnalysisData> | null | undefined,
): boolean {
  if (!sa) return false;
  const parcels = (sa as { parcels?: unknown }).parcels;
  const parcelN = Array.isArray(parcels) ? parcels.length : 0;
  if (parcelN > 0) return false;

  const parcelCount = (sa as { parcelCount?: number | null }).parcelCount;
  if (typeof parcelCount === "number" && parcelCount > 0) return false;

  const total = (sa as { landAreaSqmTotal?: number | null }).landAreaSqmTotal;
  const rep = (sa as { repLandAreaSqm?: number | null }).repLandAreaSqm;
  const positive = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v > 0;
  return positive(total) || positive(rep);
}

/**
 * 유령 집계를 걷어낸 사본을 돌려준다(정상이면 **같은 참조** 그대로).
 *
 * ★같은 참조를 유지하는 이유: 이 함수는 store 갱신·스냅샷 하이드레이션처럼 **모든 쓰기**가
 *   지나는 자리에 놓인다. 정상 경로에서 매번 새 객체를 만들면 참조 동등성으로 리렌더를
 *   가르는 구독자들이 전부 다시 그려진다(이 저장소는 그 연쇄로 React #185 크래시를 겪었다).
 *
 * ★무목업: 0 이 아니라 `null`. 0 은 "면적이 0㎡"라는 **거짓 사실**이 되어 나눗셈·비율을
 *   조용히 오염시킨다. 소비처는 `null` 을 "미확보"로 정직하게 분기한다.
 *
 * ★`landAreaSqm` 도 함께 지운다 — 이 형상에서 그 값은 **통합 합계가 흘러든 것**이고
 *   (`effectiveLandAreaSqm` 은 `parcelCount<=1` 이면 `landAreaSqm` 을 그대로 반환하므로
 *   여기를 안 지우면 유령이 그대로 화면에 닿는다), 대표필지 면적으로 **대체하지도 않는다**
 *   (없는 값을 지어내지 않는다 — 사용자가 필지를 다시 고르면 정상 경로가 채운다).
 */
export function healPhantomAreaAggregates<T extends Partial<SiteAnalysisData>>(
  sa: T | null | undefined,
): T | null | undefined {
  if (!hasPhantomAreaAggregates(sa)) return sa;
  return {
    ...(sa as T),
    landAreaSqm: null,
    landAreaSqmTotal: null,
    repLandAreaSqm: null,
    zoneMixed: false,
  };
}
