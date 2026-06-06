// apps/web/lib/formatters.ts

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
  if (isNaN(value)) return "0원";

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
  if (isNaN(value)) return "0";
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
 * Converts Square Meters (m²) to Pyeong (평) and formats cleanly.
 * 1 Pyeong = 3.305785 m²
 */
export function formatArea(m2: number): string {
  if (isNaN(m2) || m2 === 0) return "0 m²";

  const pyeong = m2 / 3.305785;
  return `${m2.toLocaleString("en-US", { maximumFractionDigits: 1 })} m² (약 ${pyeong.toLocaleString("en-US", { maximumFractionDigits: 0 })}평)`;
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
