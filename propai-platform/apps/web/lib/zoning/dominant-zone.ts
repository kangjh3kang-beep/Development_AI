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
 */

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
}

/**
 * 표시 문자열을 만든다.
 *
 * @param fallback 값이 **없을 때**(null/빈문자) 쓸 문구. 센티널일 때는 쓰이지 않는다 —
 *                 보류는 "미상"과 다르기 때문이다(모른다 ≠ 단일화를 거부했다).
 */
export function formatDominantZone(
  dominantZone?: string | null,
  options?: { dominantBasis?: string | null; fallback?: string; mixedLabel?: string },
): DominantZoneDisplay {
  const { dominantBasis = null, fallback = "미확보", mixedLabel } = options ?? {};
  if (isMixedReviewRequired(dominantZone, dominantBasis)) {
    return {
      label: mixedLabel ?? "혼재(분리검토 필요) — 단일 용도지역으로 판정하지 않았습니다",
      withheld: true,
    };
  }
  const trimmed = (dominantZone ?? "").trim();
  if (!trimmed) return { label: fallback, withheld: true };
  return { label: trimmed, withheld: false };
}
