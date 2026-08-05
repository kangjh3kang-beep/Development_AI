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
/**
 * 좌표가 **무엇을 가리키는가**. `"masked"` 는 원천이 지번을 가려 질의조차 만들지 못해
 * **좌표가 아예 없는** 상태다 — `"dong"`(동 대표점은 받았다)과 뭉뚱그리면 그 사실이
 * 관측에서 사라진다.
 */
export type CoordPrecision = "parcel" | "building" | "dong" | "masked";

export interface ComparableGroup {
  name?: string;
  /** 지번. 원천(MOLIT)이 가려서 주면 `"5*"`·`"1**"` 형태로 온다. */
  jibun?: string | null;
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
  /**
   * 원천(MOLIT)이 지번을 가려서 준 **거래 건수**(`"5*"`·`"1**"`). 이 물건들은 질의를
   * 만들 수 없어 좌표가 없고, `located_count` 에 들어오지 못한다.
   * ★단위는 이 raw 블록의 다른 카운트와 같은 **거래 건수**다. 물건 수는 아래 별도 키.
   */
  masked_jibun_count?: number;
  masked_jibun_group_count?: number;
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
  /** 원천이 지번을 가려 위치를 확인할 수 없는 **거래 건수**(백엔드와 같은 단위). */
  maskedJibunCount: number;
  /** 같은 축의 **물건 수**(단위 혼입 방지 — 이름으로 가른다). */
  maskedJibunGroupCount: number;
}

/** 이 표본이 실제로 무엇인지. 반경을 적용하지 않았으면 **반경을 말하지 않는다**. */
/**
 * 반경(m) → 표기용 km 문자열. **백엔드 `f"{km:g}"` 와 등가**여야 한다.
 *
 * ★R2 리뷰(M-3) — 종전엔 한 파일 안에서 두 표기가 공존했다: `sampleLabel` 은
 * `Number(km.toFixed(2))`, `noSampleHead` 는 `toFixed(1)`. 1250m 이면 각각
 * "1.25km" / "1.3km" 이고 백엔드는 "1.25km" 다 — **같은 값에 세 표기**.
 * 현재 호출부가 전부 라운드 값이라 잠복 상태였을 뿐이다. 한 헬퍼로 모은다.
 */
export function kmText(radiusM: number): string {
  const km = radiusM / 1000;
  // Python `%g` 는 유효숫자 6자리로 자르고 뒤따르는 0 을 제거한다.
  return String(parseFloat(km.toPrecision(6)));
}

export function sampleLabel(b: SampleBasis): string {
  if (b.scope === "radius" && b.radiusM) {
    // ★표기는 `kmText` 한 곳에서만 만든다(R2 리뷰 M-3 — 한 파일 안에 세 표기가 공존했다).
    return `반경 ${kmText(b.radiusM)}km 내 위치 확인 거래`;
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
  if (b.unlocatedCount > 0) parts.push(`위치 미확인 ${b.unlocatedCount.toLocaleString("ko-KR")}건`);
  if (b.approximateCount > 0) parts.push(`위치 개략(동 단위) ${b.approximateCount.toLocaleString("ko-KR")}건`);
  if (b.cappedCount > 0) parts.push(`표시 상한 초과 ${b.cappedCount.toLocaleString("ko-KR")}건`);
  if (parts.length === 0) return null;
  return `${parts.join(" · ")} 집계 제외`;
}

/**
 * 표본 0 사유의 **서두**. `sampleLabel()` 은 명사구라 "~가 없습니다"를 붙이면 비문이 된다
 * ("시군구 전체(반경 미적용)가 없습니다"). 범위별로 문장을 통째로 만든다.
 */
function noSampleHead(b: SampleBasis): string {
  if (b.scope === "radius" && b.radiusM) {
    return `반경 ${kmText(b.radiusM)}km 내에서 위치가 확인된 거래가 없습니다`;
  }
  if (b.scope === "sigungu") return "시군구 전체에서 위치가 확인된 거래가 없습니다";
  return "위치가 확인된 거래가 없습니다";
}

/**
 * 표본 0일 때의 사유. 왜 없는지에 따라 문장이 달라야 한다.
 *
 * ★백엔드 `comparable_sample.no_sample_reason` 과 **같은 계약·같은 문구**다.
 *   원천(MOLIT)이 지번을 가려서 주는 경우(`"5*"`·`"1**"`)를 종전엔 이 미러가 몰랐다 —
 *   백엔드만 고치고 미러를 두면 "같은 문구" 약속이 거짓이 된다(R1 리뷰 m-7).
 * ★배타 분기가 아니라 **누적 서술**이다. 마스킹 1건이 위치 미확인 80건을 가리면
 *   사용자에게 **틀린 이유**를 말하는 것이고, 틀린 이유는 침묵보다 나쁠 수 있다.
 */
export function noSampleReason(b: SampleBasis): string {
  // ★★백엔드 `comparable_sample.no_sample_reason` 과 **같은 값**을 내야 한다.
  //   공유 골든 `__tests__/fixtures/no-sample-reason.cases.json` 이 그것을 값으로 잠근다
  //   (R2 리뷰 M-3: 종전 "문구 일치 불변식"은 소스에 조각이 있는지 grep 할 뿐이라
  //   실제로는 반경 표기가 갈려 있었다 — 1250m 에서 백엔드 1.25km / 미러 1.3km).
  const why =
    "공개 실거래 자료가 지번을 가려서 제공해(예: 5*, 1**) 위치를 확인할 수 없습니다";
  const masked = b.maskedJibunCount ?? 0;

  const bits: string[] = [];
  if (b.unlocatedCount > 0) bits.push(`위치 미확인 ${b.unlocatedCount.toLocaleString("ko-KR")}건`);
  if (b.approximateCount > 0) {
    bits.push(`동 단위까지만 확인 ${b.approximateCount.toLocaleString("ko-KR")}건`);
  }

  // 마스킹은 위치 미확인의 **부분집합이자 그 원인**이다 — 카운트를 항으로 더하면
  // 같은 거래를 두 번 세는 것이다. 스큐로 어긋나면 포함 관계를 주장하지 않는다.
  let tail = "";
  if (masked > 0) {
    // ★R4 리뷰(C-1) — 이 문구는 백엔드와 **글자까지 같아야** 한다. R3 에서 백엔드만
    //   고치고 여기를 놓쳐 공유 골든 13건 중 3건이 어긋났다(전역 전파방지 미이행).
    //   ★M-1·M-2 — "위 건수"는 앞에 건수가 없으면 가리킬 것이 없고, 동 단위 확인분만
    //   있으면 **틀린 대상**을 가리킨다. 대상을 명시하고, 없으면 괄호를 생략한다.
    const rel =
      b.unlocatedCount > 0
        ? "(위 '위치 미확인' 건수에 포함되는지는 확인할 수 없습니다)"
        : "";
    tail =
      masked <= b.unlocatedCount
        ? ` 위치 미확인 중 ${masked.toLocaleString("ko-KR")}건은 ${why}.`
        : ` 지번이 가려진 거래는 ${masked.toLocaleString("ko-KR")}건으로 집계됐습니다${rel} — ${why}.`;
  }

  if (bits.length === 0) {
    if (tail) return `${noSampleHead(b)}.${tail}`;
    return `${noSampleHead(b)}(해당 기간·범위에 수집된 거래가 없습니다).`;
  }
  return `${noSampleHead(b)} — ${bits.join(" · ")}은 단가 산정에 쓰지 않습니다.${tail}`;
}

function basisFromCategory(cat: ComparableCategory | null | undefined): SampleBasis {
  const raw = cat?.sample_basis;
  // ★R3 리뷰(F-8) — 백엔드 L-5(중복 순회 제거)를 미러에도 전파한다(전역 전파방지).
  const fromGroups = maskedFromGroups(cat);
  if (raw) {
    return {
      scope: raw.scope === "radius" ? "radius" : "sigungu",
      radiusApplied: !!raw.radius_applied,
      radiusM: raw.radius_m ?? null,
      locatedCount: raw.located_count ?? 0,
      approximateCount: raw.approximate_count ?? 0,
      unlocatedCount: raw.unlocated_count ?? 0,
      cappedCount: raw.capped_count ?? 0,
      // ★키 **부재**와 값 **0** 을 구분한다(백엔드 M-5 와 같은 규율). 실제 배포 스큐는
      //   "sample_basis 는 있고 마스킹 키만 없는" 형태이고, 거기서 0 으로 단정하면
      //   그 구간 내내 마스킹 사유가 조용히 사라진다.
      maskedJibunCount: raw.masked_jibun_count ?? fromGroups.deals,
      maskedJibunGroupCount: raw.masked_jibun_group_count ?? fromGroups.groups,
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
    maskedJibunCount: fromGroups.deals,
    maskedJibunGroupCount: fromGroups.groups,
  };
}

/** 한국 지번 표기에 `*` 는 쓰이지 않는다 — 문자 존재만으로 마스킹을 판정한다. */
export function isMaskedJibun(jibun: string | null | undefined): boolean {
  return (jibun ?? "").includes("*");
}

/** `groups` 에서 마스킹 (거래 건수, 물건 수) 를 센다 — 신형 키가 없을 때의 복원 경로. */
function maskedFromGroups(
  cat: ComparableCategory | null | undefined,
): { deals: number; groups: number } {
  let deals = 0;
  let groups = 0;
  for (const g of cat?.groups ?? []) {
    if (isMaskedJibun(g.jibun)) {
      groups += 1;
      deals += g.count ?? 0;
    }
  }
  return { deals, groups };
}

function statusOf(g: ComparableGroup): LocationStatus {
  if (g.location_status) return g.location_status;
  // 구버전 페이로드 폴백 — 정밀도 필드가 있으면 그것까지 본다.
  if (g.lat === null || g.lat === undefined) return "unlocated";
  // ★R3 리뷰(F-9) — 마스킹은 좌표가 **없다**는 뜻이다. 백엔드 레거시 폴백과 같은 답을 낸다
  //   (종전엔 백엔드 approximate / 프론트 located 로 두 미러가 갈렸다 — 도달 불가였으나
  //   enum 을 늘리면서 양쪽을 안 맞추면 조용히 갈라지는 전형 경로다).
  if (g.coord_precision === "masked") return "unlocated";
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
