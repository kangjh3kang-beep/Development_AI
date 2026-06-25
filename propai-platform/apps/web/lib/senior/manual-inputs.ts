/**
 * manual-inputs — 시니어 평가기 입력 중 store 자동산출이 불가능한 '사용자 제공 사실'의
 * 수동 입력 surface(등기부 인수권리·조합 동의 현황·건물 감정가 등).
 *
 * ★무목업 원칙(사용자 지침): 없는 값을 0/가정으로 채우지 않는다. 대신 '미입력'으로 투명하게
 *   표시하고, 값이 입력되면 즉시 해당 정량 판정이 활성된다(생략 → 입력 시 활성). store가 향후
 *   해당 값을 보유하게 되면 build-inputs 자동매핑이 자연히 우선(merge에서 store 우선) → 코드
 *   변경 없이 활성. 평가기(백엔드)는 이미 이 입력들을 소비하도록 구현됨 — 여기서 흘려주기만 한다.
 */

export type SeniorInputValue = number | string | boolean;
export type ManualValueMap = Record<string, SeniorInputValue>;

export interface ManualInputField {
  key: string; // 평가기 input 키(백엔드 evaluator가 읽는 이름과 1:1)
  label: string; // 한국어 라벨
  kind: "number" | "select" | "boolean";
  unit?: string; // 원·%·㎡·명
  hint?: string; // 입력 설명(전문 용어 풀이·미입력 시 영향)
  options?: { value: string; label: string }[]; // select 전용
}

/** 에이전트 키 → 수동 입력 필드(없으면 키 부재). 백엔드 evaluator input과 1:1 정합. */
export const MANUAL_INPUTS: Record<string, ManualInputField[]> = {
  senior_appraiser: [
    {
      key: "building_appraised_total",
      label: "건물 감정가(원가법)",
      kind: "number",
      unit: "원",
      hint: "재조달원가 × 연면적 × 잔가율(하한 20%). 미입력 시 토지만 반영 → 종전평가 과소 경고",
    },
  ],
  senior_legal_scrivener: [
    {
      key: "senior_liens_total",
      label: "인수 선순위 권리 합",
      kind: "number",
      unit: "원",
      hint: "말소기준보다 선순위인 (근)저당 잔액·대항력 임차보증금 등 매수인 인수액. 미입력 시 인수율 산정 생략",
    },
    {
      key: "redevelopment_type",
      label: "정비사업 유형",
      kind: "select",
      options: [
        { value: "재개발", label: "재개발" },
        { value: "재건축", label: "재건축" },
      ],
      hint: "조합설립 동의 요건(도시정비법 35조): 공통 소유자 3/4 · 면적은 재개발 1/2·재건축 3/4 + 재건축은 각 동별 과반 추가",
    },
    { key: "consent_owner_count", label: "동의 토지등소유자 수", kind: "number", unit: "명" },
    { key: "total_owner_count", label: "전체 토지등소유자 수", kind: "number", unit: "명" },
    { key: "consent_area_sqm", label: "동의 토지면적", kind: "number", unit: "㎡" },
    { key: "total_area_sqm", label: "전체 토지면적", kind: "number", unit: "㎡" },
    {
      key: "building_consent_majority",
      label: "각 동별 구분소유자 과반 동의(재건축)",
      kind: "boolean",
      hint: "도시정비법 35조③ 재건축 추가 요건. 미입력 시 '동별 과반 미검증'으로 정직 표시(거짓 충족 방지)",
    },
  ],
  // 도시계획: 정비사업 비례율=(종후자산총평가−총사업비)/종전자산총평가×100. 분모(종전자산평가)는
  //   토지+건물 감정이라 store 미보유 → 수동입력(필수). 종후·총사업비는 수지 연동 시 자동(build-inputs)
  //   이며 ★store 우선(SSOT) — 수지 실행 시 이 수동값은 무시되고 자동값 적용(merge store-first).
  //   수지 미실행 시에만 이 수동값으로 비례율 활성. 권리가액·분담금은 개별 종전평가·조합원분양가 입력 시 동반.
  senior_urban_planner: [
    {
      key: "prior_appraisal_total",
      label: "종전자산총평가(토지+건물 감정)",
      kind: "number",
      unit: "원",
      hint: "감정평가사 종전자산 감정(토지 공시지가기준+건물 원가법) 합. 비례율 분모 — 미입력 시 비례율 산정 생략",
    },
    {
      key: "post_appraisal_total",
      label: "종후자산총평가(총 분양수입)",
      kind: "number",
      unit: "원",
      hint: "완공 후 분양예정자산 총 추산액(≈총 분양수입). 수지분석 연동 시 자동 적용(이 입력 무시) — 수지 미실행 시에만 사용",
    },
    {
      key: "total_project_cost",
      label: "총사업비",
      kind: "number",
      unit: "원",
      hint: "공사비+간접비+금융비 등 정비사업 총사업비. 수지분석 연동 시 자동 적용(이 입력 무시) — 수지 미실행 시에만 사용",
    },
    {
      key: "prior_appraisal_individual",
      label: "조합원 개별 종전자산평가",
      kind: "number",
      unit: "원",
      hint: "특정 조합원의 종전자산 감정가. 입력 시 권리가액(=개별 종전평가×비례율) 산정 — 미입력 시 권리가액 생략",
    },
    {
      key: "member_sale_price",
      label: "조합원분양가",
      kind: "number",
      unit: "원",
      hint: "해당 조합원 분양 예정가. 권리가액과 함께 분담금(=분양가−권리가액·음수는 환급) 산정 — 미입력 시 분담금 생략",
    },
  ],
};

/** 에이전트에 수동 입력 필드가 있는가. */
export function hasManualInputs(key: string): boolean {
  return (MANUAL_INPUTS[key]?.length ?? 0) > 0;
}

/**
 * raw(입력 폼 문자열) → 타입 변환. 빈값(미입력)은 키 생략(무목업 — 평가기가 해당 항목 생략).
 *   number: 유한수만(빈/비수치 생략). boolean: ""→생략·"true"→true·"false"→false. select: 문자열.
 */
export function coerceManualInputs(
  key: string,
  raw: Record<string, string> | undefined,
): ManualValueMap {
  const fields = MANUAL_INPUTS[key] ?? [];
  const out: ManualValueMap = {};
  for (const f of fields) {
    const v = raw?.[f.key];
    if (v === undefined || v === "") continue; // 미입력 → 생략
    if (f.kind === "number") {
      const n = Number(v);
      if (Number.isFinite(n)) out[f.key] = n;
    } else if (f.kind === "boolean") {
      if (v === "true") out[f.key] = true;
      else if (v === "false") out[f.key] = false;
    } else {
      out[f.key] = v; // select 문자열
    }
  }
  return out;
}

/**
 * store 자동매핑 + 수동 입력 병합. ★store 값 우선(SSOT) — 수동은 store 미보유 항목만 보완.
 *   따라서 store가 향후 값을 보유하면 자동매핑이 우선 적용되어 코드 변경 없이 활성된다.
 */
export function mergeSeniorInputs(
  storeInputs: Record<string, number> | undefined,
  manual: ManualValueMap,
): ManualValueMap | undefined {
  const merged: ManualValueMap = { ...manual, ...(storeInputs ?? {}) };
  return Object.keys(merged).length ? merged : undefined;
}
