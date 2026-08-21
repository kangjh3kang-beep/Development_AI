/**
 * 분석 필드 라벨·단위 SSOT — 원시 점경로 키를 비전문가가 읽을 수 있는 말로 바꾼다.
 *
 * ## 왜 필요한가 (쉬운 설명)
 *
 * 지금까지 화면에 `effective_far.zone_mix[*].area_sqm` 같은 **개발자용 키**가 그대로 보였다.
 * 이건 데이터가 저장된 자리 이름이지 사용자가 알아야 할 정보가 아니다. 여기 한 곳에서
 * "자리 이름 → 사람 말 + 단위"를 정의하고 모든 화면이 이걸 쓰면, 한 번 고칠 때 전역이 따라온다.
 *
 * ## 정직 원칙
 *
 * 표에 등재되지 않은 키는 **그럴듯한 이름을 지어내지 않는다.** 마지막 경로 조각을 한국어처럼
 * 보이게 가공하면(예: `sd_gate_ratio` → "에스디 게이트 비율") 없는 의미를 만들어낸다.
 * 대신 소비처가 "기타 항목"으로 접어서 원본 키를 그대로 보여주도록 `null`을 돌려준다
 * (숨기지도, 날조하지도 않는다).
 */

/** 배열 인덱스를 [*]로 정규화 — 백엔드 contradiction._normalize_key와 동일 규칙. */
const ARRAY_INDEX_RE = /\[\d+\]/g;

export function normalizeFieldKey(key: string): string {
  return key.replace(ARRAY_INDEX_RE, "[*]");
}

/** 단위 표기. count 계열은 한국어 수량사(개/곳)를 쓰므로 필드별로 지정한다. */
export type FieldMeta = { label: string; unit?: string; decimals?: number };

/**
 * 등재된 필드만 사람 말로 바꾼다. 키는 **정규화된 점경로**.
 * ★새 필드를 화면에 노출하려면 여기에 추가한다(소비처를 고치지 말 것 — 여기가 SSOT).
 */
const FIELD_LABELS: Record<string, FieldMeta> = {
  // 부지·면적
  "land_area_sqm": { label: "대지면적", unit: "㎡" },
  "effective_far.parcel_count": { label: "선택 필지 수", unit: "개" },
  "effective_far.zone_mix[*].area_sqm": { label: "용도지역별 면적", unit: "㎡" },
  "effective_far.total_area_sqm": { label: "통합 면적", unit: "㎡" },

  // 용적률·건폐율
  "effective_far.effective_far_pct": { label: "실효 용적률", unit: "%", decimals: 1 },
  "effective_far.effective_bcr_pct": { label: "실효 건폐율", unit: "%", decimals: 1 },
  "effective_far.legal_far_pct": { label: "법정 용적률", unit: "%", decimals: 1 },
  "potential_far_range.min_pct": { label: "상향 가능 용적률(하한)", unit: "%", decimals: 1 },
  "potential_far_range.max_pct": { label: "상향 잠재 용적률(범위 상단)", unit: "%", decimals: 1 },

  // 입지
  "location.education.school_count": { label: "반경 내 학교", unit: "곳" },
  "location.score": { label: "입지 점수", unit: "점" },

  // 시세
  "official_price_per_sqm": { label: "공시지가(㎡당)", unit: "원" },
};

/** 등재 필드면 메타를, 아니면 null(=소비처가 '기타 항목'으로 처리). */
export function fieldMeta(rawKey: string): FieldMeta | null {
  return FIELD_LABELS[normalizeFieldKey(rawKey)] ?? null;
}

/**
 * 수치를 사람이 읽는 문자열로. 천단위 구분 + 단위. 값이 수치가 아니면 그대로 문자열화.
 *
 * ★소수 자리수는 필드 메타의 decimals를 따른다(면적·개수는 정수, 비율은 소수 1자리).
 *   지정이 없으면 정수부만 — 화면에 152826.00000001 같은 부동소수 지터를 내보내지 않는다.
 */
export function formatFieldValue(value: unknown, meta: FieldMeta | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value ?? "-");
  const decimals = meta?.decimals ?? 0;
  const num = value.toLocaleString("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return meta?.unit ? `${num}${meta.unit}` : num;
}

/**
 * 증감 표기 — "얼마나" 달라졌는지를 **실제 단위**로 준다(변화율 % 대신).
 *
 * 사용자 지적의 핵심: "변화율 33%"는 무엇이 얼마나 변했는지 알려주지 않는다.
 * 3개→2개는 "-1개"가, 176,458㎡→152,826㎡는 "-23,632㎡"가 이해 가능한 정보다.
 * 이전값이 0이거나 수치가 아니면 증감을 만들지 않는다(0으로 나눈 비율 날조 금지).
 */
export function formatDelta(prev: unknown, now: unknown, meta: FieldMeta | null): string | null {
  if (typeof prev !== "number" || typeof now !== "number") return null;
  if (!Number.isFinite(prev) || !Number.isFinite(now)) return null;
  const diff = now - prev;
  if (diff === 0) return null;
  const sign = diff > 0 ? "+" : "−"; // U+2212(마이너스) — 하이픈과 시각적으로 구분
  return `${sign}${formatFieldValue(Math.abs(diff), meta)}`;
}
