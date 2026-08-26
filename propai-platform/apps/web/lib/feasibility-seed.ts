/**
 * 부지분석에서 파생되는 **수지 입력 시드** — 세 경로가 같은 것을 쓰게 한다.
 *
 * ## 무엇이 있었나 (2026-08-26 실측)
 *
 * 같은 값을 세 곳이 각자 만들었고 **한 곳이 빠졌다**:
 *
 *  · `ModuleInputForm.tsx` 자동시드   — 공시지가·시도명 **보냄** ✔
 *  · `ModuleInputForm.tsx` 수동버튼   — 같은 로직 **복제** ✔
 *  · `node-body-builders.ts` 오케스트레이션 — 주석에 계약으로 적어 놓고 **안 보냄** ✘
 *
 * `node-body-builders.ts:259` 는 `official_price_per_sqm?` 를 계약으로 **선언**하는데
 * 그 파일에서 `body.official_price_per_sqm` 대입은 **0건**이다(대조군: `body.` 대입 31건).
 * 결과: 오케스트레이션으로 돌린 수지는 **공시지가 0** 으로 토지비를 잡는다.
 * ★CLAUDE.md §G30 — *"…한다"는 동작 주장은 그 자체가 검증 대상이다.*
 *
 * ## 왜 공용으로 빼나
 *
 * 세 곳을 각자 고치면 **네 번째가 또 빠진다**. 한 곳을 고치면 전역이 따라오게 한다
 * (버그수정 기본정책 — 전역 전파방지).
 *
 * ★**정상 입력에서는 동작이 같다. 「안 바꿨다」는 거짓이다**(적대 리뷰가 차분 실측으로 반증).
 *   360 조합 차분에서 정상 입력(양수 면적·공시지가, 정규 주소)은 **차이 0** 이었다.
 *   차이가 나는 것은 **퇴화 입력 3종**이고 전부 **더 보수적인** 방향이다:
 *     · 주소 **선행공백**(`" 울산광역시 …"`) — 종전 `sido_name=""`/미기록 → 이제 `"울산광역시"` (`trim()` **신설**)
 *     · 음수·`Infinity` 면적/공시지가 — 종전 그대로 전달 → 이제 **미기록** (`Number()`+`>0` **신설**)
 *     · 공백뿐인 주소 — 종전 `sido_name=""` → 이제 미기록
 *   ★`trim()` 과 `Number()` 강제변환은 **형제에 없던 새 규칙**이다. 회귀는 아니지만
 *     *"그대로 옮겼다"* 고 적으면 후임이 재검증하지 않고 신뢰한다(증거 규율 §1).
 */
import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";

/** 부지분석에서 파생되는 수지 입력. 확보 못 한 것은 **null** — 0 으로 만들지 않는다(무목업). */
export type SiteDerivedFeasibilityFields = {
  /** 통합 대지면적(㎡). 다필지는 `effectiveLandAreaSqm` 이 합산한다. */
  totalLandAreaSqm: number | null;
  /**
   * 공시지가(원/㎡).
   *
   * ★**알려진 한계 — 이 커밋이 만든 것이 아니라 옮겨 온 것이다.**
   *   면적은 다필지를 **합산**하는데 단가는 **대표 1필지**(`officialPrices[0]`)를 쓴다.
   *   두 값의 기준이 갈릴 수 있다. **값 차이는 미측정**이고, 여기서 고치면 배선 수정과
   *   값 변경이 한 커밋에 섞인다 → `__tests__/feasibility-seed.test.ts` 에 `it.todo` 로 남긴다.
   */
  officialPricePerSqm: number | null;
  /** 시도명. 주소 첫 토큰(형제와 동일 규칙). */
  sidoName: string | null;
};

/** 양수만 통과. `NaN`·음수·0 은 **미확보**로 본다(0 은 "공시지가 0원"이 아니라 "모름"이다). */
function positive(v: unknown): number | null {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/**
 * 부지분석 → 수지 입력 시드.
 *
 * ★이 함수가 **유일한 산출처**다. 새 소비처가 생기면 여기를 쓰고, 규칙이 바뀌면 여기만 고친다.
 */
export function siteDerivedFeasibilityFields(
  site: SiteAnalysisData | null | undefined,
): SiteDerivedFeasibilityFields {
  const addr = typeof site?.address === "string" ? site.address.trim() : "";
  const sido = addr ? (addr.split(" ")[0] || "") : "";
  return {
    totalLandAreaSqm: positive(effectiveLandAreaSqm(site)),
    officialPricePerSqm: positive(site?.officialPrices?.[0]?.pricePerSqm),
    sidoName: sido || null,
  };
}

/**
 * 백엔드 `FeasibilityCalculateRequest` 의 **부지 파생 필드 이름** — 계약 SSOT.
 *
 * ★파생형 락이 이 목록과 각 경로가 실제로 보내는 집합을 대조한다. 손으로 센 목록이 아니라
 *   **한 곳에서 파생**시켜야 새 필드가 자동으로 감시망에 든다.
 */
export const SITE_DERIVED_REQUEST_FIELDS = [
  "total_land_area_sqm",
  "official_price_per_sqm",
  "sido_name",
] as const;
