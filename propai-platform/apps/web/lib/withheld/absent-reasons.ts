/**
 * 보류 사유 **닫힌 어휘** — 백엔드 `apps/api/app/utils/withheld.py` 의 거울.
 *
 * ## 왜 거울이 필요한가 (프론트는 파이썬을 임포트할 수 없다)
 *
 * 계약은 `X: 값|None` · `X_basis|X_reason: 문구` · `X_absent: 닫힌 코드` 다.
 * **코드는 기계가 세고, 문구는 사람이 읽는다.** 그런데 `X_basis` 가 **문구가 아니라 코드**인
 * 필드가 실재한다(실측: `primary_zone_basis` ∈ `area_weighted`·`first_parcel_no_area`·`none`…).
 * 그런 필드에서는 *"basis 문구를 그대로 렌더"* 라는 관용이 **이식 불가**하고,
 * 화면이 **코드 → 한국어**를 스스로 알아야 한다. 그것이 이 파일이다.
 *
 * ## ★왜 화면마다 자기 목록을 두면 안 되나 (실측 결함)
 *
 * 2026-09-04 실측 — 실거래 단가 열:
 *
 *     생산자 realtx_report_service.py  → not_applicable · insufficient_coverage · masked_by_source
 *     소비자 RealtxReportPanel.tsx     → not_applicable · masked_by_source · source_unavailable
 *     소비자 realtx_adapter.py(PDF)    → (같은 3종)
 *
 * `insufficient_coverage` 가 **화면·PDF 양쪽에서 `"—"` 로 떨어져 사유가 소실**됐고,
 * `source_unavailable` 은 그 필드에서 **죽은 라벨**이었다. **목록은 곧 상한이 된다** —
 * 생산자에 코드가 하나 늘면 소비자는 **조용히** 침묵한다(빨개지지 않는다).
 *
 * ★그래서 처방은 *"목록을 늘려라"* 가 아니라 **"덮지 않은 코드에도 말할 것이 있게 하라"** 다.
 *   열별 짧은 문구는 `overrides` 로 계속 존중하되, 덮이지 않으면 **공용 문구로 떨어진다.**
 *
 * ★기존 락(`tests/test_withheld_value_contract.py`)은 **생산자 축**만 잠갔다 —
 *   *"코드가 어휘 안인가"*. **소비자가 그 코드를 이름 붙일 수 있는가**는 안 봤다(한쪽만 건 단언).
 *   그 반대편은 `tests/test_absent_reason_consumer_coverage.py` 가 잠근다.
 */

/** 닫힌 어휘 — 백엔드 `ABSENT_REASONS` 의 키와 **정확히 같아야 한다**(양방향 락). */
export const ABSENT_CODES = [
  "insufficient_coverage",
  "single_source",
  "source_unavailable",
  "masked_by_source",
  "ambiguous",
  "not_applicable",
  "awaiting_input",
] as const;

export type AbsentCode = (typeof ABSENT_CODES)[number];

/**
 * 코드 → **사람이 읽는 뜻**. 백엔드 `ABSENT_REASONS` 와 **문구까지 동일**하다.
 *
 * ★문구를 여기서 다르게 쓰면 **같은 코드가 화면과 PDF 에서 다른 뜻**이 된다 —
 *   이 저장소에 *"한 화면이 두 기준으로 말한다"* 는 사고 기록이 있다. 락이 문구를 대조한다.
 */
export const ABSENT_REASONS: Record<AbsentCode, string> = {
  insufficient_coverage: "판정에 필요한 지표·표본이 하한에 미치지 못했습니다",
  single_source: "독립 추정이 하나뿐이라 교차검증이 성립하지 않습니다",
  source_unavailable: "외부 원천을 조회하지 못했습니다(응답 없음·오류)",
  masked_by_source: "원천이 값을 가려 제공하지 않습니다",
  ambiguous: "판정이 갈려 하나로 단일화하지 않았습니다",
  not_applicable: "이 대상에는 해당하지 않는 항목입니다",
  awaiting_input: "판정에 필요한 입력을 아직 받지 못했습니다",
};

/**
 * 표 **칸**에 들어갈 짧은 라벨. 백엔드 `ABSENT_SHORT` 와 키·문구가 같다.
 *
 * ★긴 문구와 **별개 축**이다 — 칩·툴팁은 긴 것을, 표 칸은 짧은 것을 쓴다.
 *   한 벌로 뭉치면 표가 줄바꿈으로 무너지거나 칩이 뜻을 못 전한다.
 */
export const ABSENT_SHORT: Record<AbsentCode, string> = {
  insufficient_coverage: "표본부족",
  single_source: "교차검증불가",
  source_unavailable: "조회실패",
  masked_by_source: "원천미제공",
  ambiguous: "판정보류",
  not_applicable: "해당없음",
  awaiting_input: "입력대기",
};

/** 닫힌 어휘 안인가. ★런타임 JSON 은 타입을 지키지 않으므로 값을 직접 본다. */
export function isAbsentCode(code: unknown): code is AbsentCode {
  return typeof code === "string" && (ABSENT_CODES as readonly string[]).includes(code);
}

/**
 * 코드를 화면 문구로 바꾼다.
 *
 * @param code      백엔드가 실은 `X_absent` 값(무엇이 와도 안전하다).
 * @param overrides 열·화면 고유의 짧은 문구. **덮은 코드만** 이것을 쓰고,
 *                  덮지 않은 코드는 `table` 이면 `ABSENT_SHORT`, 아니면 `ABSENT_REASONS` 로 떨어진다.
 *                  ★그래서 **생산자에 코드가 늘어도 `"—"` 가 나오지 않는다.**
 * @returns 문구, 또는 **어휘 밖·빈 값이면 `null`**.
 *          ★`null` 을 문구로 뭉개지 않는다 — 「사유가 없다」와 「모르는 사유다」는 다른 사실이고,
 *            호출부가 그 둘을 다르게 그릴 수 있어야 한다.
 */
export function resolveAbsentLabel(
  code: unknown,
  options?: { overrides?: Partial<Record<AbsentCode, string>>; variant?: "short" | "long" },
): string | null {
  if (!isAbsentCode(code)) return null;
  const { overrides, variant = "long" } = options ?? {};
  const override = overrides?.[code];
  if (override) return override;
  return variant === "short" ? ABSENT_SHORT[code] : ABSENT_REASONS[code];
}
