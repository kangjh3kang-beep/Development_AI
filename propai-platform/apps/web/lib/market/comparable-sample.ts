/**
 * 주변 실거래 표본 선별 — 집계·라벨의 단일 통로(SSOT).
 *
 * 백엔드 미러: `apps/api/app/services/market/comparable_sample.py` (같은 계약·같은 문구).
 * 두 층이 각자 판정하면 화면과 보고서가 서로 다른 말을 하게 된다.
 *
 * ## 왜 필요한가
 *
 * `/zoning/nearby-map` 의 `categories[*].groups` 는 성격이 다른 셋이 섞인 리스트다:
 *
 * - `location_status="located"`      좌표가 **그 물건**을 가리키고(지번·건물명 질의), 반경
 *                                    필터가 적용됐다면 통과한 그룹
 * - `location_status="approximate"`  좌표는 있으나 **법정동 대표점**이거나 동명 물건이 여러
 *                                    동에 걸쳐 병합된 그룹 — 반경 안팎을 단정할 수 없다
 * - `location_status="unlocated"`    지오코딩 실패로 어디인지 모르는 그룹(반경 밖으로 단정하지
 *                                    않기 위해 버리지 않고 보존 — 무날조 계약)
 *
 * 이걸 그냥 순회해 평균을 내고 "반경 1km" 라벨을 붙이면 **거짓 진술**이 된다.
 * 2026-08-02 라이브 실측에서 표시 표본의 60~100%가 located 가 아니었다
 * (호미곶 0/67 · 역삼동 아파트 18/105 · 역삼동 토지 0/47 · 암사동 2,264/5,601).
 *
 * ★`approximate` 를 따로 둔 이유: `lat != null` 검사만으로는 절대 안 걸리기 때문이다.
 * 좌표가 멀쩡히 있어서 반경 판정을 "통과"하지만, 그 좌표가 그룹을 대표하지 않는다.
 *
 * ## 계약
 *
 * 1. 집계(평균·중앙값·합계·단가)는 `selectLocatedGroups()` 결과로만 한다.
 * 2. 표면 라벨은 `sampleLabel()` 로만 만든다. 요청 `radius_m` 을 문자열에 직접 넣지 않는다.
 * 3. 표본이 0이면 값을 만들지 않고 `noSampleReason()` 으로 사유를 고지한다.
 *    "거래가 없다"와 "반경 안에서 위치가 확인된 거래가 없다"는 다른 상태다.
 */

export type LocationStatus = "located" | "approximate" | "unlocated";
export type CoordPrecision = "parcel" | "building" | "dong";

export interface ComparableGroup {
  name?: string;
  lat?: number | null;
  lon?: number | null;
  count?: number;
  avg_price_10k?: number;
  avg_area_m2?: number;
  avg_deposit_10k?: number;
  avg_monthly_10k?: number;
  deals?: Array<Record<string, unknown>>;
  location_status?: LocationStatus;
  coord_precision?: CoordPrecision;
}

export interface SampleBasisRaw {
  scope?: "radius" | "sigungu";
  radius_applied?: boolean;
  radius_m?: number | null;
  located_count?: number;
  approximate_count?: number;
  unlocated_count?: number;
  capped_count?: number;
}

export interface ComparableCategory {
  label?: string;
  type?: string;
  kind?: string;
  count?: number;
  groups?: ComparableGroup[];
  sample_basis?: SampleBasisRaw;
  /** @deprecated `sample_basis` 사용. 구버전 페이로드 복원용. */
  count_in_radius?: number;
  /** @deprecated `sample_basis` 사용. */
  count_approximate?: number;
  /** @deprecated `sample_basis` 사용. */
  count_unresolved?: number;
  /** @deprecated `sample_basis` 사용. */
  capped_count?: number;
}

export interface SampleBasis {
  /** ★"sigungu"(반경 미적용임을 **안다**)와 "unknown"(알 수 없다)은 다른 상태다. */
  scope: "radius" | "sigungu" | "unknown";
  radiusApplied: boolean;
  radiusM: number | null;
  locatedCount: number;
  approximateCount: number;
  unlocatedCount: number;
  cappedCount: number;
}

/** 이 표본이 실제로 무엇인지. 반경을 적용하지 않았으면 **반경을 말하지 않는다**. */
export function sampleLabel(b: SampleBasis): string {
  if (b.scope === "radius" && b.radiusM) {
    const km = b.radiusM / 1000;
    // 1000 → "1km", 1500 → "1.5km"
    const kmTxt = `${Number(km.toFixed(2))}km`;
    return `반경 ${kmTxt} 내 위치 확인 거래`;
  }
  if (b.scope === "sigungu") return "시군구 전체(반경 미적용)";
  // ★W1-b 리뷰(M-1) — 구버전 페이로드(배포 스큐·캐시)에는 `sample_basis` 가 없어 반경 적용
  //   여부를 **알 수 없다**. 종전엔 이때도 "시군구 전체(반경 미적용)"이라 단정했는데, 실제로는
  //   구 백엔드도 반경을 적용하고 있었다(라이브 픽스처 최상위 radius_applied=true).
  //   이 PR 의 존재 이유가 "모르는 것을 단정하지 마라"인데 그 원칙을 스스로 어기는 자리였다.
  return "표본 범위 확인 불가";
}

/** 집계에서 빠진 것을 밝힌다. 빠진 게 없으면 null(없는 말을 지어내지 않는다). */
export function exclusionNote(b: SampleBasis): string | null {
  const parts: string[] = [];
  if (b.unlocatedCount > 0) parts.push(`위치 미확인 ${b.unlocatedCount.toLocaleString()}건`);
  if (b.approximateCount > 0) parts.push(`위치 개략(동 단위) ${b.approximateCount.toLocaleString()}건`);
  if (b.cappedCount > 0) parts.push(`표시 상한 초과 ${b.cappedCount.toLocaleString()}건`);
  if (parts.length === 0) return null;
  return `${parts.join(" · ")} 집계 제외`;
}

/** 표본 0일 때의 사유. 왜 없는지에 따라 문장이 달라야 한다. */
export function noSampleReason(b: SampleBasis): string {
  const bits: string[] = [];
  if (b.unlocatedCount > 0) bits.push(`위치 미확인 ${b.unlocatedCount.toLocaleString()}건`);
  if (b.approximateCount > 0) bits.push(`동 단위까지만 확인된 ${b.approximateCount.toLocaleString()}건`);
  if (bits.length > 0) {
    return `${sampleLabel(b)}를 찾지 못했습니다(${bits.join(" · ")}은 집계에 쓰지 않습니다).`;
  }
  return "해당 조건에서 수집된 실거래가 없습니다.";
}

function basisFromCategory(cat: ComparableCategory | null | undefined): SampleBasis {
  const raw = cat?.sample_basis;
  if (raw) {
    return {
      scope: raw.scope === "radius" ? "radius" : "sigungu",
      radiusApplied: !!raw.radius_applied,
      radiusM: raw.radius_m ?? null,
      locatedCount: raw.located_count ?? 0,
      approximateCount: raw.approximate_count ?? 0,
      unlocatedCount: raw.unlocated_count ?? 0,
      cappedCount: raw.capped_count ?? 0,
    };
  }
  // ★구버전 페이로드(캐시·배포 스큐) 폴백 — 카운트에서 복원하고, 알 수 없으면 보수적으로
  //   "반경 미적용"으로 본다(모르면 반경을 주장하지 않는다 = 이 모듈의 존재 이유와 같은 방향).
  return {
    // ★단정하지 않는다 — 반경을 적용했는지 **모르는** 상태다(위 라벨 주석 참조).
    scope: "unknown",
    radiusApplied: false,
    radiusM: null,
    locatedCount: cat?.count_in_radius ?? 0,
    approximateCount: cat?.count_approximate ?? 0,
    unlocatedCount: cat?.count_unresolved ?? 0,
    cappedCount: cat?.capped_count ?? 0,
  };
}

function statusOf(g: ComparableGroup): LocationStatus {
  if (g.location_status) return g.location_status;
  // 구버전 페이로드 폴백 — 정밀도 필드가 있으면 그것까지 본다.
  if (g.lat === null || g.lat === undefined) return "unlocated";
  if (g.coord_precision && g.coord_precision === "dong") return "approximate";
  return "located";
}

/**
 * 카테고리에서 **위치가 확인된** 그룹만 골라 근거와 함께 돌려준다.
 *
 * 집계하려는 모든 코드는 이 함수를 통과해야 한다. `cat.groups` 를 직접 순회하면
 * 위치 미확인·개략 그룹이 섞인다.
 */
export function selectLocatedGroups(
  cat: ComparableCategory | null | undefined,
): { groups: ComparableGroup[]; basis: SampleBasis } {
  const groups = (cat?.groups ?? []).filter((g) => statusOf(g) === "located");
  return { groups, basis: basisFromCategory(cat) };
}

/** 지도 마커용 — 좌표가 있으면 찍을 수 있다(개략 좌표도 점으로는 유효). 집계와 기준이 다르다. */
export function selectMappableGroups(cat: ComparableCategory | null | undefined): ComparableGroup[] {
  return (cat?.groups ?? []).filter(
    (g) => g.lat !== null && g.lat !== undefined && g.lon !== null && g.lon !== undefined,
  );
}

/** 거래건수 가중 평균가(만원)와 **그 평균을 실제로 만든 건수**.
 *
 * ★W1-b 리뷰(M-6) — 평균은 `avg_price_10k` 가 있는 그룹만으로 만들어지는데, 화면은
 * `basis.locatedCount`(위치확인 **전체** 건수)를 "N건 기준"으로 표시했다. 가격 결측 그룹이
 * 있으면 "18건 평균"이라 써놓고 실제로는 12건으로 만든 값이 된다 — 이 PR 이 봉합하려는
 * "라벨과 모집단 불일치"가 봉합 코드 안에 그대로 남아 있던 자리다.
 * 표시 건수로 쓸 수 있도록 가중치 합을 **함께** 돌려준다.
 */
export function weightedAvgPrice10kWithCount(
  groups: ComparableGroup[],
): { avg: number | null; count: number } {
  let totalW = 0;
  let acc = 0;
  for (const g of groups) {
    const price = g.avg_price_10k ?? 0;
    if (price <= 0) continue;
    const w = Math.max(1, g.count ?? 0);
    acc += price * w;
    totalW += w;
  }
  if (totalW <= 0) return { avg: null, count: 0 };
  return { avg: Math.round(acc / totalW), count: totalW };
}

/** 값만 필요한 소비처용 얇은 래퍼(계산은 위 함수 한 곳에서만 한다). */
export function weightedAvgPrice10k(groups: ComparableGroup[]): number | null {
  return weightedAvgPrice10kWithCount(groups).avg;
}
