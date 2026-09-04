/**
 * 우세 용도지역 표시 — **판정 보류를 값처럼 말하지 않는다**.
 *
 * 백엔드(`special_parcel.py`)는 다필지 집계에서 상위 두 zone 의 면적이 **±5% 이내**이거나
 * **규제성격이 다르면**(상업+주거 등) `dominant_zone` 에 `"mixed_review_required"` 를 넣는다.
 * 그건 **값이 아니라 "임의 단일화를 거부했다"는 신호**다(#787 이 확립).
 *
 * ★왜 공용 헬퍼인가 — 이 판정을 **화면마다 따로** 구현하다가 두 곳이 빠졌다(실측):
 *   · `ProjectAnalysisSummary` 자체 `MIXED_SENTINEL` 상수 — 가드 O
 *   · `ParcelBoundaryMap` 인라인 삼항식 — 가드 O
 *   · `IntegratedParcelsBadge` 인라인 비교 — 가드 O
 *   · `multi-parcel/page.tsx` → `dominant_zone || "혼재/미상"` — **가드 X**
 *   · `DesignGenPanel` → `dominant_zone || "—"` — **가드 X**
 *   `||` 는 **falsy 만** 걸러낸다. 센티널은 **비어 있지 않은 문자열**이라 그대로 통과해
 *   사용자에게 `mixed_review_required` 가 용도지역 이름 자리에 **맨몸으로** 나간다.
 *
 * ★센티널일 때 대표 필지 용도지역으로 **대체하지 않는다** — 그것이 #787 이 고친
 *   "대표를 우세라 부르는" 결함이다. **이름을 짓지 않고, 판정하지 않았다고 말한다.**
 *
 * ## ★이 모듈은 **두 계약**을 다룬다 (2026-09-04 추가)
 *
 * 백엔드에 보류 표기가 **두 갈래**로 살아 있고, 화면은 둘 다 만난다:
 *
 *   ① **센티널 계약**(구판 · `special_parcel.py`) — 값 자리에 `"mixed_review_required"`.
 *      위에 적은 그대로다. **새 코드가 이 길을 가서는 안 된다**(`withheld.py` 가 금지어로 등재).
 *   ② **보류값 계약**(정본 · `app/utils/withheld.py`) — `X: null` + `X_absent: 닫힌 코드`.
 *      `design/2026-08-25_보류값_계약_부재의_사유를_코드로.md` 가 확립했다.
 *
 * ★①만 다루면 ②에서 **「왜 보류인지」를 원리적으로 말할 수 없다** — 값이 `null` 이라
 *   화면은 `{zone || "용도미상"}` 폴백을 타고, 백엔드가 실어 보낸 사유 코드는 **버려진다.**
 *   그래서 `absent` 를 받는다. ★**사유를 버리는 것은 그 자체로 장애다**(진단 불가).
 *
 * ★**여기서 `X_basis` 를 문구로 렌더하지 않는다** — 이 필드계열의 `_basis` 는 **문구가 아니라
 *   코드**다(실측: `primary_zone_basis` ∈ `area_weighted`·`first_parcel_no_area`·`none`).
 *   형제 `DeveloperProjection.tsx` 가 쓰는 *"basis 문구를 그대로 렌더"* 관용은 **이식 불가**하다.
 */

import { resolveAbsentLabel } from "@/lib/withheld/absent-reasons";

export const MIXED_REVIEW_SENTINEL = "mixed_review_required";

/** 센티널인가 — `dominant_zone` 값과 `dominant_basis` 양쪽을 본다(백엔드가 둘 다 쓴다). */
export function isMixedReviewRequired(
  dominantZone?: string | null,
  dominantBasis?: string | null,
): boolean {
  return dominantZone === MIXED_REVIEW_SENTINEL || dominantBasis === MIXED_REVIEW_SENTINEL;
}

export interface DominantZoneDisplay {
  /** 화면에 그대로 쓸 수 있는 문자열. 센티널·미확보를 절대 raw 로 내보내지 않는다. */
  label: string;
  /** 보류 상태인가(칩·배지 스타일 분기용). */
  withheld: boolean;
  /**
   * **왜** 보류인지(닫힌 어휘 `X_absent` 를 사람 문구로). 사유를 모르면 **붙이지 않는다**.
   *
   * ★선택 필드인 이유: 이 값을 **항상** 실으면(`reason: null` 포함) 기존 소비처의
   *   `toEqual({label, withheld})` 계약이 깨진다. **기존 경로는 바이트 동일**해야 하고,
   *   바뀌는 것은 **종전에 아무 말도 못 하던 입력**뿐이다 — 그것이 회귀가 아니라는 근거다.
   * ★`label` 에 섞지 않고 **따로** 내보내는 이유: 칩은 짧아야 하고 사유는 길다.
   *   섞으면 호출부가 문자열을 다시 쪼개게 되고, 그 쪼개기가 다음 결함의 자리가 된다.
   */
  reason?: string;
  /**
   * 같은 사유의 **짧은 형태**(칩 안에 들어갈 크기). `reason` 과 **항상 짝**으로 나온다.
   *
   * ★왜 둘 다 필요한가(적대 리뷰 2026-09-04 · MEDIUM-1): 첫 봉합은 칩에 긴 문구를 넣고
   *   툴팁에는 **`ambiguous` 전용 산문**(*"용도지역을 하나로 판정하지 않았습니다…"*)을
   *   **조건 없이** 붙였다. 그런데 `reason` 은 **닫힌 어휘 7종 전부**에서 붙으므로,
   *   `source_unavailable`(원천 조회 실패)일 때 칩과 툴팁이 **서로 모순**됐다 —
   *   *"조회하지 못했습니다"* 옆에서 툴팁이 *"판정하지 않았습니다"* 라고 **단정**한다.
   *   ★내가 고친다고 선언한 결함 클래스(한 사유를 다른 사유의 이름으로 부름)를
   *     **내 신규 코드가 재발**시킨 것이다. → 두 형태를 **둘 다 코드에서 파생**시킨다.
   */
  reasonShort?: string;
}

/**
 * 표시 문자열을 만든다.
 *
 * @param fallback 값이 **없을 때**(null/빈문자) 쓸 문구. 센티널일 때는 쓰이지 않는다 —
 *                 보류는 "미상"과 다르기 때문이다(모른다 ≠ 단일화를 거부했다).
 */
export function formatDominantZone(
  dominantZone?: string | null,
  options?: {
    dominantBasis?: string | null;
    fallback?: string;
    mixedLabel?: string;
    /**
     * 보류값 계약(②)의 `X_absent` 코드. **어휘 밖·미지정이면 조용히 무시**한다 —
     * 모르는 코드를 화면에 raw 로 내보내는 것이 이 모듈이 막으려는 바로 그 결함이다.
     */
    absent?: unknown;
  },
): DominantZoneDisplay {
  const { dominantBasis = null, fallback = "미확보", mixedLabel, absent } = options ?? {};
  if (isMixedReviewRequired(dominantZone, dominantBasis)) {
    return {
      label: mixedLabel ?? "혼재(분리검토 필요) — 단일 용도지역으로 판정하지 않았습니다",
      withheld: true,
    };
  }
  const trimmed = (dominantZone ?? "").trim();
  if (!trimmed) {
    // ★값이 없을 때만 사유를 본다 — 계약이 **값과 사유를 배타**로 두기 때문이다(FHIR
    //   `dataAbsentReason` 과 같은 규율). 값이 있는데 사유가 붙어 있으면 그건 백엔드의
    //   계약 위반이고, `validate_withheld_pair` 가 **거기서** 잡을 일이지 화면이 덮을 일이 아니다.
    const reason = resolveAbsentLabel(absent);
    const reasonShort = resolveAbsentLabel(absent, { variant: "short" });
    // ★둘은 **같은 코드에서** 나오므로 함께 있거나 함께 없다. 한쪽만 붙는 상태를 만들지 않는다
    //   — 호출부가 «짧은 게 없으면 긴 걸 쓰자» 같은 폴백을 지어내기 시작하는 자리다.
    return reason && reasonShort
      ? { label: fallback, withheld: true, reason, reasonShort }
      : { label: fallback, withheld: true };
  }
  return { label: trimmed, withheld: false };
}
