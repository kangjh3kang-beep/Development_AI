// apps/web/lib/formatters.ts

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
