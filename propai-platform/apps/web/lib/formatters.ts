// apps/web/lib/formatters.ts

/** 평↔㎡ 환산 SSOT — 1평 = 3.305785㎡ (백엔드 PYEONG_TO_SQM와 동일값. 3.3058 근사값 혼용 금지). */
export const PYEONG_SQM = 3.305785;

/** 천단위 쉼표 표시(정수부만). null/빈값→"". 소수 허용(keepDecimal). */
export function withCommas(value: number | string | null | undefined, keepDecimal = false): string {
  if (value == null || value === "") return "";
  const s = String(value);
  const neg = s.trim().startsWith("-");
  const cleaned = s.replace(/[^0-9.]/g, "");
  if (cleaned === "" || cleaned === ".") return neg ? "-" : "";
  const [intPart, ...rest] = cleaned.split(".");
  const intFmt = intPart.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ",") || "0";
  const dec = keepDecimal && rest.length ? "." + rest.join("") : "";
  return `${neg ? "-" : ""}${intFmt}${dec}`;
}

/** 쉼표 포함 문자열 → number|null. 빈값→null. */
export function parseCommaNumber(s: string, allowDecimal = false): number | null {
  if (s == null) return null;
  const cleaned = String(s).replace(allowDecimal ? /[^0-9.\-]/g : /[^0-9\-]/g, "");
  if (cleaned === "" || cleaned === "-" || cleaned === ".") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/**
 * Formats a number into native Korean currency units (만원, 억원, 조원).
 * Example: 1250000000 -> "12억 5,000만 원"
 * Example: 565000000 -> "5억 6,500만 원"
 */
export function formatCurrencyKRW(value: number): string {
  // 무효 입력은 "0원"으로 날조하지 않는다 — 값 부재를 정직하게 표기.
  if (isNaN(value)) return "-";

  const num = Math.abs(value);
  const sign = value < 0 ? "-" : "";

  if (num < 10000) {
    return `${sign}${num.toLocaleString("ko-KR")}원`;
  }

  const units = ["", "만", "억", "조", "경"];
  let res = "";
  let temp = num;

  // Split by 10,000
  const parts: number[] = [];
  while (temp > 0) {
    parts.push(temp % 10000);
    temp = Math.floor(temp / 10000);
  }

  // We typically only show the top two significant units for readability
  // e.g., 1조 2,500억
  const topIndex = parts.length - 1;
  const topValue = parts[topIndex];
  
  if (topIndex === 1) {
    // Only "만"
    res = `${topValue.toLocaleString("ko-KR")}만 원`;
  } else if (topIndex >= 2) {
    // "억" or "조"
    const currentUnit = units[topIndex];
    const secondValue = parts[topIndex - 1];

    if (secondValue > 0) {
      res = `${topValue.toLocaleString("ko-KR")}${currentUnit} ${secondValue.toLocaleString("ko-KR")}만 원`;
    } else {
      res = `${topValue.toLocaleString("ko-KR")}${currentUnit} 원`;
    }
  }

  return `${sign}${res}`;
}

/**
 * Formats a number into a shorter version for dense charts (e.g. 1.25B KRW -> 12.5억).
 */
export function formatCurrencyCompact(value: number): string {
  // 무효 입력은 "0"으로 날조하지 않는다 — 값 부재를 정직하게 표기.
  if (isNaN(value)) return "-";
  const num = Math.abs(value);
  const sign = value < 0 ? "-" : "";

  if (num >= 1000000000000) {
    return `${sign}${(num / 1000000000000).toFixed(1)}조`;
  } else if (num >= 100000000) {
    return `${sign}${(num / 100000000).toFixed(1)}억`;
  } else if (num >= 10000) {
    return `${sign}${(num / 10000).toFixed(0)}만`;
  }
  return `${sign}${num.toLocaleString("ko-KR")}`;
}

/**
 * 면적 표시 SSOT(UX 트랙 A2) — ㎡+평 병기, ko-KR 로케일, "약" 접두 없음(값 자체가 이미
 * 반올림 근사이므로 접두가 군더더기). SatongMapShell 로컬 formatArea·satong-measure의
 * satong-measure 이외 자리(ComprehensiveAnalysisPanel·SiteAnalysisDetail) 로컬 중복분을
 * 이 함수로 흡수한다(㎡ vs m²·"약" 유무·en-US/ko-KR 5중 분기 통일).
 * 무효(null/NaN)·비양수(≤0)는 "-" — 가짜 "0㎡" 날조 금지(formatCurrencyKRW 등과 동일 원칙).
 * fractionDigits: 주 수치(㎡) 소수 자릿수 상한. 미지정 시 toLocaleString 기본(최대 3자리)으로
 * 기존 호출부 표기를 그대로 보존 — 정수 반올림이 필요한 호출부(예: SatongMapShell)는 0을 넘긴다.
 * 평 환산은 모든 기존 호출부와 동일하게 항상 소수 1자리(toFixed(1), 천단위 콤마 없음).
 */
export function formatArea(value?: number | null, fractionDigits?: number): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return "-";
  const pyeong = value / PYEONG_SQM;
  const mainOpts = fractionDigits == null ? undefined : { maximumFractionDigits: fractionDigits };
  return `${value.toLocaleString("ko-KR", mainOpts)}㎡ (${pyeong.toFixed(1)}평)`;
}

/**
 * 분석값 단일 표기 헬퍼 — 빈/null/NaN은 "분석 전"으로 통일한다.
 * 숫자면 천단위 쉼표 + (선택)단위, 문자열이면 그대로 사용한다.
 * (프로젝트 전반의 "—"/빈칸 혼용을 "분석 전"으로 일원화하기 위한 단일 출처)
 */
export function formatAnalysisValue(
  value: number | string | null | undefined,
  suffix = "",
): string {
  if (value == null) return "분석 전";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "분석 전";
    return `${Math.round(value).toLocaleString()}${suffix}`;
  }
  const trimmed = String(value).trim();
  if (trimmed === "") return "분석 전";
  return `${trimmed}${suffix}`;
}

/**
 * 만원 단위 금액 → "N억 N,NNN만원"(예: 12500 → "1억 2,500만원", 500 → "500만원").
 * 시장분석(시장인사이트) 화면 여러 곳에 흩어져 있던 동일 로직(formatPrice·formatMan·man 등
 * 4중복)의 단일 출처(SSOT). 무효/0 이하 입력은 "-"(가짜 0원 표기 금지).
 */
export function formatManwon(man?: number | null): string {
  if (!man || man <= 0) return "-";
  if (man >= 10000) {
    const uk = Math.floor(man / 10000);
    const rest = man % 10000;
    return rest > 0 ? `${uk}억 ${rest.toLocaleString()}만원` : `${uk}억원`;
  }
  return `${man.toLocaleString()}만원`;
}

/**
 * "YYYYMM" 연월 문자열 → "YY.MM" 축약 표기(차트 축 라벨·표 셀 등 좁은 공간용).
 * 형식이 다르면(YYYYMM 6자리가 아니면) 원본 값을 그대로 반환(날조 금지).
 */
export function formatYm(ym?: string | null): string {
  if (!ym) return "-";
  const m = String(ym).match(/^(\d{4})(\d{2})$/);
  if (!m) return String(ym);
  return `${m[1].slice(2)}.${m[2]}`;
}
