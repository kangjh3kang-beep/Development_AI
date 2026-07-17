/**
 * 기성(billing) 청구 기간 파생 공용 헬퍼.
 *
 * 백엔드 계약(정답 기준선): POST /cost/{pid}/billing 의 요청 모델
 * `BillingRegisterRequest`(apps/api/app/routers/cost.py)는 `period_from`/`period_to`
 * 두 필드를 받고, progress_billings 테이블의 DATE 컬럼에 저장한다
 * (cost_tables_bootstrap.py — `period_from date, period_to date`).
 * → 반드시 완전한 날짜(YYYY-MM-DD)로 보내야 하며, "2026-06" 같은 월 문자열은
 *   DATE 캐스트가 실패하고, 모델에 없는 `period` 필드는 Pydantic이 조용히 버린다.
 *
 * 이 헬퍼는 사용자가 폼에 입력한 기간 문자열을 백엔드 계약에 맞는
 * 날짜 범위로 바꿔 준다. 허용 입력:
 *  - "2026-06"                     → 해당 월 전체 (2026-06-01 ~ 2026-06-30)
 *  - "2026-06-15"                  → 하루 (2026-06-15 ~ 2026-06-15)
 *  - "2026-06-01 ~ 2026-06-30"    → 명시 범위 (목록 표시 형식 재입력 지원)
 * 형식이 아니면 null 을 돌려주고, 호출부가 검증 에러를 표시한다.
 */

export interface BillingPeriodRange {
  /** 기간 시작일 (YYYY-MM-DD) */
  period_from: string;
  /** 기간 종료일 (YYYY-MM-DD) */
  period_to: string;
}

/** 두 자리 0채움 (6 → "06"). */
function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** 해당 연·월의 마지막 날짜(28~31). 윤년도 Date 가 알아서 처리한다. */
function lastDayOfMonth(year: number, month1based: number): number {
  // month 는 1-based → new Date(y, m, 0) = 해당 월의 말일
  return new Date(year, month1based, 0).getDate();
}

/** "YYYY-MM" 또는 "YYYY-MM-DD" 한 조각을 {from, to}로 해석. 실패 시 null. */
function parseOnePart(part: string): BillingPeriodRange | null {
  const month = /^(\d{4})-(\d{1,2})$/.exec(part);
  if (month) {
    const y = Number(month[1]);
    const m = Number(month[2]);
    if (m < 1 || m > 12) return null;
    const mm = pad2(m);
    return {
      period_from: `${y}-${mm}-01`,
      period_to: `${y}-${mm}-${pad2(lastDayOfMonth(y, m))}`,
    };
  }
  const day = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(part);
  if (day) {
    const y = Number(day[1]);
    const m = Number(day[2]);
    const d = Number(day[3]);
    if (m < 1 || m > 12) return null;
    if (d < 1 || d > lastDayOfMonth(y, m)) return null;
    const iso = `${y}-${pad2(m)}-${pad2(d)}`;
    return { period_from: iso, period_to: iso };
  }
  return null;
}

/**
 * 기간 입력 문자열 → 백엔드 계약(period_from/period_to, YYYY-MM-DD) 파생.
 * 형식 오류·역순 범위(from > to)는 null.
 */
export function deriveBillingPeriod(raw: string): BillingPeriodRange | null {
  const input = raw.trim();
  if (!input) return null;

  // "A ~ B" 명시 범위 (목록 표시 형식을 그대로 복사해 넣는 경우 지원)
  if (input.includes("~")) {
    const parts = input.split("~").map((s) => s.trim());
    if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
    const left = parseOnePart(parts[0]);
    const right = parseOnePart(parts[1]);
    if (!left || !right) return null;
    if (left.period_from > right.period_to) return null; // 역순 범위 금지
    return { period_from: left.period_from, period_to: right.period_to };
  }

  return parseOnePart(input);
}
