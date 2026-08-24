import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import { getZoningSpec } from "@/lib/kr-building-regulations";

/**
 * 유효면적 계산에 필요한 최소 구조 — SiteAnalysisData 의 부분집합.
 *
 * effectiveLandAreaSqm 을 store 전체 타입을 갖지 못한 좁은 컨텍스트(예: 매핑 함수의
 * 인라인 입력 타입)에서도 재사용할 수 있게 한다. 이게 없으면 그런 곳에서 raw landAreaSqm 을
 * 직접 읽는 유혹이 생겨 SSOT 우회가 재발한다(실측: workspace-extended-panels.ts 유출).
 */
export type AreaResolvable = {
  landAreaSqm?: number | null;
  landAreaSqmTotal?: number | null;
  parcelCount?: number | null;
  /** 필지 목록 — 길이가 두 번째 모집단이다(parcelCount 와 어긋날 수 있다). 면적 필드는 보지 않는다. */
  parcels?: ReadonlyArray<unknown> | null;
};

/**
 * 필지 집합의 기준(basis) — 면적 값이 **무엇을 근거로 한 값인지**.
 *
 * 왜 값만으로는 부족한가(쉬운 설명):
 * 같은 "대지면적 3,836㎡"라도 그것이 *한 필지짜리 부지의 전부*인지, *여러 필지 부지의 대표 한 필지*인지에
 * 따라 뜻이 완전히 다르다. 값만 던지면 두 화면이 **서로 다른 면적을 같은 이름("대지면적")으로**
 * 보여 줄 수 있고, 사용자는 어느 쪽도 믿을 수 없게 된다.
 * 값에 기준을 동봉하면 화면이 그 차이를 **숨기지 않고 말할 수 있다**.
 *
 * ※ 출처 라벨 — 아래 주석의 수치는 **이 저장소 코드를 vitest 로 직접 태워 얻은 동작**이다
 *   (`site-area.test.ts` 의 같은 픽스처). **특정 사용자 화면의 관측 기록이 아니다** —
 *   그 구분을 흐리면 다음 사람이 인계 서술을 실측으로 오독한다.
 */
export type LandAreaBasis =
  /** 다필지 통합면적(landAreaSqmTotal) — 진짜 사업 면적. */
  | "integrated"
  /** 다필지인데 통합면적이 아직 없어 대표필지 면적으로 **강등**된 상태. ★화면은 이를 고지해야 한다. */
  | "representative"
  /** 단일필지 — 그 필지의 면적이 곧 전부. */
  | "single"
  /** 면적 미확보 — 0 으로 채우지 않는다(무날조). */
  | "none";

/** 면적 + 그 면적의 기준. 소비처는 값만 꺼내 쓰지 말고 기준도 함께 읽는다. */
export interface ResolvedLandArea {
  /** 유효 대지면적(㎡). 미확보면 null — 0 강제 금지. */
  valueSqm: number | null;
  /** 이 값이 무엇을 근거로 하는가. */
  basis: LandAreaBasis;
  /** 판정에 쓴 필지 수(두 모집단의 최대). 0 이면 필지 정보 자체가 없음. */
  parcelCount: number;
  /**
   * 두 모집단(parcelCount · parcels.length)이 **서로 다른 수를 말한다**.
   * 헤더는 parcelCount 로 "N필지"라 하는데 본문은 parcels 가 비어 "단일 필지"라 단언하는 형태로
   * 드러난다(#772·#773 이 보고·봉합한 계열). 그 침묵을 되살리지 않도록 사실로 실어 보낸다.
   */
  populationsDisagree: boolean;
}

/**
 * ★필지 수 SSOT — "이 부지는 몇 필지인가"에 답하는 **단 하나의 판정**.
 *
 * 왜 필요한가(쉬운 설명):
 * 필지 수를 말해 주는 곳이 store 에 둘 있다 — `parcelCount`(숫자)와 `parcels`(목록의 길이).
 * 둘은 서로 다른 시점에 채워지므로 잠깐씩 어긋난다. 그런데 코드마다 어느 쪽을 볼지 제각각이라
 * (실측 8벌: `parcelCount ?? 1 > 1` · `parcels.length >= 2` · 둘의 AND · mapAddresses.length …)
 * **같은 화면이 같은 부지를 두고 "7필지"와 "단일 필지"를 동시에 말했다.**
 *
 * 규칙: **둘 중 큰 쪽**을 믿는다. 어느 한쪽이라도 "여러 필지"라고 말하면 다필지로 본다.
 * 근거(실측 — `site-area.test.ts` [B] 케이스): `parcelCount` 만 보던 종전 규칙은 필지 목록과
 * 통합면적을 **둘 다 쥐고 있는데도** 대표면적으로 축약했다. 즉 피해는 언제나
 * *다필지를 단필지로 줄이는* 방향이었다. 반대 방향(단필지를 다필지로 봄)은 통합면적이 없으면
 * 대표면적으로 되돌아가므로 값이 틀어지지 않는다 — 이 규칙은 **틀렸을 때 덜 해로운 쪽**으로 기운다.
 */
export function resolveParcelCount(sa: AreaResolvable | null | undefined): number {
  if (!sa) return 0;
  const declared = typeof sa.parcelCount === "number" && sa.parcelCount > 0 ? sa.parcelCount : 0;
  const listed = Array.isArray(sa.parcels) ? sa.parcels.length : 0;
  return Math.max(declared, listed);
}

/**
 * ★다필지 여부 SSOT — **사실 판정**("이 부지가 다필지인가").
 *
 * ※ 아래 `hasParcelRows` 와 혼동하지 말 것. 이 둘은 **서로 다른 질문**이고, 이 둘을 뒤섞은 것이
 *   R1 이 고치는 근본이다:
 *     - `isMultiParcel`  : 부지가 다필지인가 (표시·라벨·기준 판정에 쓴다)
 *     - `hasParcelRows`  : 필지 **목록을 실제로 손에 쥐고 있는가** (필지별 요청 바디 조립에 쓴다)
 *   목록이 아직 안 왔다고 해서 "단일 필지입니다"라고 **단언하면 안 된다** — 그게 #773 이 고친 결함이다.
 */
export function isMultiParcel(sa: AreaResolvable | null | undefined): boolean {
  return resolveParcelCount(sa) >= 2;
}

/**
 * 필지별 행(주소·면적·용도지역)을 실제로 보유하는가 — **데이터 가용성 판정**.
 *
 * 필지 목록을 그대로 백엔드에 실어 보내는 경로(통합분석·필지별 조회 등)는 목록이 있어야만
 * 다필지 요청을 만들 수 있다. 그런 곳은 이 판정을 쓴다(사실 판정인 `isMultiParcel` 을 쓰면
 * 빈 배열로 다필지 요청을 보내게 된다).
 */
export function hasParcelRows(sa: AreaResolvable | null | undefined): boolean {
  return (Array.isArray(sa?.parcels) ? sa.parcels.length : 0) >= 2;
}

/**
 * ★면적 기준 SSOT — 유효 대지면적을 **기준과 함께** 해석한다.
 *
 * 왜 필요한가(쉬운 설명):
 * 다필지(여러 필지를 합친 부지)를 분석하면 "통합 면적"이 진짜 사업 면적이다.
 * 그런데 한 필지(대표 번지)만 다시 조회하는 분석이 나중에 실행되면 대표 면적(작은 값)이
 * 통합 면적을 덮어써서, 설계·수지가 부지를 너무 작게 보는 버그가 생긴다. 통합 면적
 * (landAreaSqmTotal)은 한 곳에서만 기록되어 안정적으로 보존되므로, 읽는 쪽에서 "다필지면
 * 통합 우선"으로 읽으면 덮어쓰기 경합과 무관하게 항상 정확한 면적을 얻는다(경합 면역).
 *
 * ★기준을 함께 돌려주는 이유: 다필지인데 통합면적이 아직 없으면 대표면적으로 **강등**되는데,
 *   종전엔 그 강등이 **소리 없이** 일어나 화면이 대표면적을 통합면적인 양 보여 줬다.
 *   이제 `basis="representative"` 로 사실을 실어 보내 화면이 고지할 수 있게 한다.
 *
 * 다운스트림(설계·수지·적산·금융·심의·법률 등)은 반드시 이 헬퍼로 면적을 읽어
 * 단일 PNU 분석이 landAreaSqm을 대표값으로 덮어써도 통합면적이 보존되게 한다.
 * 무목업: 둘 다 없으면 null(0 강제 금지).
 */
export function resolveLandArea(
  sa: AreaResolvable | null | undefined,
): ResolvedLandArea {
  const parcelCount = resolveParcelCount(sa);
  const declared = typeof sa?.parcelCount === "number" ? sa.parcelCount : null;
  const listed = Array.isArray(sa?.parcels) ? sa.parcels.length : null;
  // 둘 다 값을 말할 때만 '갈렸다'고 한다. 한쪽이 아직 없는 것은 불일치가 아니라 미완이다.
  const populationsDisagree =
    declared != null && listed != null && declared > 0 && declared !== listed;

  const total = sa?.landAreaSqmTotal;
  const raw = typeof sa?.landAreaSqm === "number" ? sa.landAreaSqm : null;

  if (parcelCount >= 2) {
    if (typeof total === "number" && total > 0) {
      return { valueSqm: total, basis: "integrated", parcelCount, populationsDisagree };
    }
    // 다필지인데 통합면적 미확보 — 값은 대표면적을 그대로 쓰되(무회귀) 강등을 사실로 알린다.
    return {
      valueSqm: raw,
      basis: raw != null ? "representative" : "none",
      parcelCount,
      populationsDisagree,
    };
  }
  return {
    valueSqm: raw,
    basis: raw != null ? "single" : "none",
    parcelCount,
    populationsDisagree,
  };
}

/**
 * ★면적 기준 고지문 — 화면이 값 옆에 붙일 한 줄. 파생을 여기 두어 **문구가 표면마다 갈리지 않게** 한다.
 *
 * 왜 공용함수인가(쉬운 설명):
 * "통합 7필지 기준" 같은 안내를 화면마다 손으로 쓰면, 한 화면만 고치고 형제 화면은 옛 문구로 남는다
 * (이 저장소가 반복해서 데인 형태다 — 한 곳을 고치면 전역이 따라오게 공용화한다).
 *
 * 반환 규칙
 *  - `integrated`      → 몇 필지 통합인지 말한다. 필지 **목록**이 아직 없으면 그 사실도 함께 고지한다.
 *  - `representative`  → ★가장 중요한 경우. 다필지인데 통합면적이 없어 **대표 1필지 면적**을 보여 주는
 *                        상태다. 종전엔 이 강등이 **소리 없이** 일어나, 화면이 대표면적을 사업 면적인
 *                        양 보여 줄 수 있었다(강등 사실이 값에 실리지 않았다).
 *  - `single`·`none`   → 덧붙일 말이 없다(군더더기 금지) → null.
 */
export function landAreaBasisNote(
  sa: AreaResolvable | null | undefined,
): string | null {
  const r = resolveLandArea(sa);
  if (r.valueSqm == null) return null;
  if (r.basis === "integrated") {
    const rowsMissing = !hasParcelRows(sa);
    return (
      `통합 ${r.parcelCount}필지 기준` +
      (rowsMissing
        ? " · 필지 목록은 아직 수신되지 않아 필지별 상세가 비어 있을 수 있습니다"
        : "")
    );
  }
  if (r.basis === "representative") {
    return `대표필지 1곳의 면적입니다 — ${r.parcelCount}필지 통합면적은 아직 확보되지 않았습니다`;
  }
  return null;
}

/**
 * 유효 대지면적(㎡) — `resolveLandArea` 의 값만 꺼내는 얇은 래퍼(기존 소비처 무회귀).
 *
 * ★새 코드는 되도록 `resolveLandArea` 를 써서 **기준까지 함께** 읽어라. 값만 읽으면
 *   "다필지인데 대표면적으로 강등된 상태"를 화면이 다시 침묵하게 된다.
 */
export function effectiveLandAreaSqm(
  sa: AreaResolvable | null | undefined,
): number | null {
  return resolveLandArea(sa).valueSqm;
}

/**
 * 유효 용적률 상한(%) — 다필지면 필지별 용도지역의 **면적가중평균**, 단일이면 대표 용도지역값.
 *
 * 왜 필요한가(쉬운 설명):
 * 면적에는 effectiveLandAreaSqm 이라는 짝이 있는데 용적률에는 없었다. 그래서 소비처가
 * "면적은 통합(Σ), 용적률은 대표필지 1개"를 곱하는 **혼종 계산**을 하게 된다. 용도지역이 섞인
 * 부지(zoneMixed)에서 이건 연면적을 통째로 틀리게 만든다 — 예컨대 1종일반주거(200%)가 대표인데
 * 상업지역(800%)이 섞여 있으면, 통합면적 전체에 200%를 곱해 연면적을 과소산출하고(반대면 과대),
 * 그 연면적이 공사비·수지로 흘러 금액이 통째로 어긋난다.
 *
 * ★주의 — siteAnalysis.zoneCode 와 dominantZoneCode 는 둘 다 '대표(첫) 필지' 값이다
 *   (satong-map-selection.ts:221-222 가 first.zoneType 을 그대로 넣는다 — 이름과 달리 면적가중이 아님).
 *   따라서 다필지 계산은 반드시 parcels[] 를 직접 가중해야 한다.
 *
 * 계약(백엔드 정답 기준선 미러):
 *   apps/api/app/services/permit/permit_analysis_service.py:326 `_blended_far`
 *   — 면적가중평균(국토계획법 시행령 제84조), 면적 누락 시 단순평균 폴백, 소수 1자리 반올림.
 * 무목업: 용도지역을 하나도 해석 못하면 null(0 강제 금지 — 호출자가 정직하게 분기).
 */
export function blendedFarPct(
  sa: SiteAnalysisData | null | undefined,
): number | null {
  const parcels = sa?.parcels;
  // ★판정 SSOT: 여기서 묻는 것은 "다필지인가"(isMultiParcel)가 아니라 **"필지별 행을 손에 쥐고
  //   있는가"**(hasParcelRows)다 — 필지마다 용도지역을 읽어 면적가중해야 하므로 목록이 없으면
  //   가중 자체가 불가능하다. 두 질문을 구분하지 않으면 빈 배열로 가중평균을 시도하게 된다.
  const multi = hasParcelRows(sa);

  // 필지목록 미보유(단일 또는 아직 미수신) — 대표 용도지역의 상한을 쓴다.
  if (!multi) {
    const far = sa?.zoneCode ? getZoningSpec(sa.zoneCode)?.floorAreaRatioMax : null;
    return typeof far === "number" && far > 0 ? far : null;
  }

  // 다필지 — 필지별 (면적, 용적률상한) 수집. 용도지역을 못 읽는 필지는 제외(무날조).
  const weighted: Array<[number, number]> = [];
  // hasParcelRows 가 길이 2 이상을 보장하지만 타입 좁히기는 전파되지 않으므로 빈배열 폴백을 둔다.
  for (const p of parcels ?? []) {
    const far = p?.zoneCode ? getZoningSpec(p.zoneCode)?.floorAreaRatioMax : null;
    if (typeof far !== "number" || far <= 0) continue;
    const area = typeof p.areaSqm === "number" && Number.isFinite(p.areaSqm) && p.areaSqm > 0
      ? p.areaSqm
      : 0;
    weighted.push([area, far]);
  }
  if (weighted.length === 0) {
    // 필지에서 하나도 못 읽으면 대표값으로 폴백(그마저 없으면 null).
    const far = sa?.zoneCode ? getZoningSpec(sa.zoneCode)?.floorAreaRatioMax : null;
    return typeof far === "number" && far > 0 ? far : null;
  }

  // 전 필지 면적 확보 → 면적가중평균. 하나라도 면적 미확보 → 단순평균(근사, 백엔드와 동일).
  const allHaveArea = weighted.every(([a]) => a > 0);
  if (allHaveArea) {
    const tot = weighted.reduce((s, [a]) => s + a, 0);
    if (tot <= 0) return null;
    return Math.round((weighted.reduce((s, [a, f]) => s + a * f, 0) / tot) * 10) / 10;
  }
  const fars = weighted.map(([, f]) => f);
  return Math.round((fars.reduce((s, f) => s + f, 0) / fars.length) * 10) / 10;
}

/**
 * 분석 입력 시그니처(address + 유효면적) — 같은 입력으로의 중복 분석 방지·stale 판별용 SSOT.
 *
 * 왜 필요한가(쉬운 설명):
 * 의사결정 브리프처럼 무거운 종합분석은 같은 입력이면 다시 부르지 않으려고 "마지막에 분석한 입력"을
 * 기억해 둔다(dedup 가드). 그런데 주소만 기억하면, 다필지 보강으로 "통합 면적"이 커져도 주소는 그대로라
 * 옛 대표면적으로 만든 낡은 브리프를 그대로 재사용하는 버그가 생긴다(다필지 대표값 덮어쓰기 클래스).
 * 그래서 가드 키를 "주소 + 유효면적(effectiveLandAreaSqm)"으로 만들어, 면적이 바뀌면 다른 시그니처가
 * 되어 자동으로 재분석되게 한다. 면적의존 캐시(decisionBrief 등)는 모두 이 헬퍼로 시그니처를 만들어
 * 동일한 staleness 규칙을 따르게 한다(한 곳을 고치면 전역이 따라옴).
 *
 * 면적 미확보(null)는 "면적 없음"을 뜻하는 빈 토큰으로 두 입력을 동일 취급한다(가짜 면적 생성 금지).
 */
export function analysisInputSignature(
  sa: SiteAnalysisData | null | undefined,
): string | null {
  const address = sa?.address ?? null;
  if (!address) return null; // 주소 없으면 분석 자체가 불가 — 시그니처 없음(가드는 호출 안 함).
  const area = effectiveLandAreaSqm(sa);
  // 면적은 정밀도 흔들림(부동소수)으로 시그니처가 진동하지 않게 정수 ㎡로 정규화.
  const areaToken =
    typeof area === "number" && area > 0 ? String(Math.round(area)) : "";
  return `${address}|${areaToken}`;
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
  // ★판정 SSOT: 필지 수는 resolveParcelCount 하나로 센다(종전엔 이 함수만 `parcelCount ?? parcels.length`
  //   라는 제3의 규칙을 써서, 같은 파일 안에서 면적·용적률과 다른 답을 냈다).
  const count = resolveParcelCount(sa);
  const parcelsLen = sa.parcels?.length ?? 0;
  // 단일필지(≤1): parcels 배열이 비어있어도(미기록) 일관 — 통합 메타가 없는 정상 단일 상태.
  if (count <= 1) return true;
  // 다필지: 필지목록 길이가 count와 일치하고 통합면적이 양수여야 완전한 통합 상태.
  const total = sa.landAreaSqmTotal;
  return parcelsLen === count && typeof total === "number" && total > 0;
}
