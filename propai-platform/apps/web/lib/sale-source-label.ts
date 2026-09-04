/**
 * 분양가 산정근거 코드 → 한글. **백엔드 어휘와 짝**이다.
 *
 * ★`components/` 가 아니라 `lib/` 에 둔다 — 어휘 매핑은 **렌더와 무관**하고,
 *   컴포넌트에 두면 미러 락이 JSX 런타임을 끌어와야 해서 잠그기 어려워진다.
 *   (실제로 그래서 첫 락이 `react/jsx-dev-runtime` 해석 실패로 못 돌았다.)
 *
 * 짝: `market_revaluation_service._blend_label` · `project_pipeline` 의 `sale_price_source`.
 * 실측(2026-09-05): 백엔드 8종 중 **`avm_blended`·`national_default_fallback` 이 빠져
 * 있었고**(선재), 거기에 `single_source:<key>` **접두 계열**이 추가됐다.
 * ★손 목록은 곧 상한이 된다 — 계열은 **접두로** 처리하고 나머지는 락이 전수 대조한다.
 */
export const SALE_SOURCE_LABEL: Record<string, string> = {
  market_blended: "시장 블렌딩(실거래+표준)",
  avm_blended: "시장 블렌딩(AI 추정 포함)",
  regional_market_table: "지역 시장 표준단가",
  national_default_fallback: "전국 기본값(폴백)",
  national_default_no_address: "전국 기본값(주소 미상)",
  molit_realtx: "국토부 실거래",
  nearby_map: "주변 실거래",
  avm: "AI 추정시세",
  cost_based_fallback: "공사비 기반(폴백)",
  user: "사용자 입력",
  user_override: "사용자 입력(직접 지정)",
  unavailable: "산출 불가",
};

/** `single_source:<key>` 계열의 하위 출처 → 한글. */
const SINGLE_SOURCE_LABEL: Record<string, string> = {
  regional: "지역 표준단가",
  molit_real: "국토부 실거래",
  avm: "AI 추정시세",
};

/**
 * 산정근거 코드를 한글로. **정말 모르는 코드는 코드 그대로**(거짓 라벨보다 낫다).
 *
 * ★`single_source:` 접두가 이 함수의 존재 이유다 — 그 계열은 **출처가 하나만 남았다**는
 *   뜻이고, «블렌딩이 안 됐는데 됐다고 말하던» 결함을 드러내려 만든 값이다.
 *   그 값이 화면에 **raw 토큰**으로 나오면 사용자는 여전히 원인을 못 본다.
 */
export function saleSourceLabel(code: string): string {
  if (SALE_SOURCE_LABEL[code]) return SALE_SOURCE_LABEL[code];
  if (code.startsWith("single_source:")) {
    const key = code.slice("single_source:".length);
    return `단일 출처(${SINGLE_SOURCE_LABEL[key] ?? key})`;
  }
  return code;
}
