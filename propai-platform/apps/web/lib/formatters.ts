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
 * ## 0의 의미 — 이 함수는 **원장량(stock)** 전용이다
 *
 * 대지면적·연면적·필지면적은 **0이 물리적으로 불가능**하다. 출처가 0을 줬다면 그건 측정값이
 * 아니라 수집 실패다. 그래서 `null/NaN`과 `≤0`을 **같은 뜻(미확보)** 으로 묶는다 — 비율에서
 * 0과 미확보를 갈라놓은 것과 반대 방향이지만, 이유는 같다: **그 필드에서 0이 무엇을 뜻하는가.**
 *
 * ★`"-"`가 아니라 `"미확보"`라고 적는다(2026-08-05). `"-"`는 0으로도 '해당없음'으로도 읽혀,
 *   정작 하고 싶은 말("아직 못 구했다")을 안 한다. 값 판정은 종전과 **완전히 동일**하고
 *   문구만 정직해진다.
 *
 * ★증분·부분량(면적 증가분·제외 면적처럼 0이 유효한 측정 결과인 필드)에는 이 함수를 쓰지 마라.
 *   그런 필드는 0을 "없음"으로 **보여줘야** 한다. 소비처가 생기면 그때 전용 함수를 만든다
 *   (지금 만들면 쓰는 곳 없는 추측성 코드가 된다).
 * fractionDigits: 주 수치(㎡) 소수 자릿수 상한. 미지정 시 toLocaleString 기본(최대 3자리)으로
 * 기존 호출부 표기를 그대로 보존 — 정수 반올림이 필요한 호출부(예: SatongMapShell)는 0을 넘긴다.
 * 평 환산은 모든 기존 호출부와 동일하게 항상 소수 1자리(toFixed(1), 천단위 콤마 없음).
 */
export function formatArea(value?: number | null, fractionDigits?: number): string {
  if (value == null || !Number.isFinite(value) || value <= 0) return "미확보";
  const pyeong = value / PYEONG_SQM;
  const mainOpts = fractionDigits == null ? undefined : { maximumFractionDigits: fractionDigits };
  return `${value.toLocaleString("ko-KR", mainOpts)}㎡ (${pyeong.toFixed(1)}평)`;
}

/**
 * 비율(%) 표시 SSOT — 법정·조례·실효를 **나란히 비교하는** 표면 전용.
 *
 * ## 왜 필요한가
 *
 * 보고서의 핵심 서사 중 하나가 "법정 한도는 200%인데 실효는 왜 79.6%인가"다. 그런데 이 값들이
 * 포매터 없이 `${x ?? "-"}%` 로 그대로 렌더되고 있어 두 가지 문제가 있었다.
 *
 * ① **원시 float가 새어나올 수 있다.** 다필지 면적가중 실효치는 나눗셈 결과라
 *    `152.83333333333334%` 같은 값이 그대로 화면에 찍힐 수 있다.
 * ② **자릿수가 값마다 달라 비교가 안 된다.** 법정 `80%` 옆에 실효 `79.6%` 가 놓이면 눈으로
 *    견주기 어렵다. 소수 1자리로 **고정**해 나란히 읽히게 한다.
 *
 * ## 0과 '미확보'를 구분한다 (★이 파일의 다른 함수와 정책이 다른 이유)
 *
 * `formatArea`·`formatManwon`은 `≤0 → "-"` 다. 금액·면적은 0이면 사실상 값이 없다는 뜻이라
 * 그 정책이 맞다. 그러나 **비율은 0이 유효한 측정값**이다(경사도 0%·건폐율 0% 등). 0을 "-"로
 * 바꾸면 '측정했더니 0'과 '못 구했음'이 같아진다 — 백엔드 자가검증 규칙도 같은 이유로
 * "0은 유효 수집값"을 명시한다. 그래서 `null/NaN`만 "미확보", `0`은 "0.0%"로 적는다.
 *
 * ★반올림을 정수로 두지 않는 이유: 정수 반올림이면 실효 79.6%가 "80%"가 되어 법정 80%와
 *   **같아 보인다.** 격차가 사라지면 이 보고서가 설명하려는 것 자체가 사라진다.
 */
export function formatPercent(value?: number | null, digits = 1): string {
  if (value == null || typeof value !== "number" || !Number.isFinite(value)) return "미확보";
  return `${value.toFixed(digits)}%`;
}

/**
 * 비율 구간 표기 — `80.0~120.0%`. 한쪽이라도 없으면 구간이 성립하지 않으므로 "미확보".
 *
 * ★`{min}~{max}%` 직접 보간을 대체한다 — 그 형태는 값이 없을 때 `"~%"` 를 만들고,
 *   두 끝의 자릿수가 서로 달라 구간이 눈으로 안 읽힌다.
 */
export function formatPercentRange(
  min?: number | null, max?: number | null, digits = 1,
): string {
  const lo = formatPercent(min, digits);
  const hi = formatPercent(max, digits);
  if (lo === "미확보" || hi === "미확보") return "미확보";
  return `${lo.replace("%", "")}~${hi}`;
}

/**
 * 증감분 비율 표기 — `formatPercent`와 같은 정책에 **부호**만 얹는다.
 *
 * ★왜 별도 함수인가: 증감 칸을 `+{value}%` 로 직접 보간하면 값이 없을 때 `"+%"` 라는
 *   깨진 문자열이 나온다(실측). 그렇다고 `+${formatPercent(v)}` 로 감싸면 `"+미확보"` 가
 *   된다. 부호는 **값이 있을 때만** 붙어야 하므로 판정을 한 곳에 둔다.
 *
 * 0은 유효값이라 `"+0.0%"` 가 아니라 `"0.0%"` 로 적는다 — 늘지 않았다는 사실을 그대로.
 */
/**
 * 퍼센트 **포인트** 표기 — 단위가 `%`가 아니라 `%p`다(비율끼리의 차이).
 *
 * ★`%`와 `%p`를 섞으면 초과분이 절반으로 읽히는 오독이 난다(200/260을 "30%p"로 읽는 식).
 *   규칙은 formatPercent와 같다 — 정수 반올림 금지, 0과 미확보 구분.
 */
export function formatPercentPoint(value?: number | null, digits = 1): string {
  if (value == null || typeof value !== "number" || !Number.isFinite(value)) return "미확보";
  return `${value.toFixed(digits)}%p`;
}

export function formatPercentDelta(value?: number | null, digits = 1): string {
  if (value == null || typeof value !== "number" || !Number.isFinite(value)) return "미확보";
  // ★부호는 **표시될 값** 기준으로 정한다. 원값 기준으로 정하면 0.04가 "+0.0%"가 되어
  //   "증가했다"고 말하면서 "변화 없음"을 보여준다(-0.04는 "-0.0%" — 음의 0까지 나온다).
  const shown = Number(value.toFixed(digits));
  const body = (shown === 0 ? 0 : value).toFixed(digits);
  return `${shown > 0 ? "+" : ""}${shown === 0 ? Math.abs(Number(body)).toFixed(digits) : body}%`;
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
  // ★원장량(거래가·감정가) 전용 — 0원은 물리적으로 불가능하므로 미확보와 같은 뜻이다.
  //   증감분은 이 함수를 거치기 전에 호출부가 `±0`으로 처리한다(AnalysisDiffTable.computeDelta).
  if (!man || man <= 0) return "미확보";
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

/**
 * 종상향 잠재 용적률 범위(백엔드 `potential_far_range`) — 표기 SSOT.
 *
 * ★왜 이 함수가 필요한가(실측 결함):
 *   대표 목표 용도지역 선정이 보수적이라 여러 종상향 경로가 **같은 목표**를 가리키면
 *   `min_pct`와 `max_pct`가 같아진다(자연녹지 서울 실측: 150·150). 그때 화면이
 *   `예상 상한 150.0~150.0%`라고 적으면 개발사는 **"그 위는 안 된다"**로 읽는다.
 *   실제 의미는 "우리가 한 경로만 봤다"인데 그 한정이 화면 어디에도 없었다.
 *   그래서 **범위가 붕괴하면 범위인 척하지 않는다**를 한 곳에서 결정한다.
 *
 * ★판정은 백엔드 계약(`is_collapsed`)이 1순위다. 프론트가 `min===max`를 혼자 눈치채는 것은
 *   계약이 아니라 우연이라, 값이 우연히 같아진 경우와 구조적으로 같은 경우를 못 가른다.
 *   계약 필드가 **없는 구(舊) 캐시 페이로드**일 때만 동값 폴백으로 "범위인 척"만 막는다
 *   (고지 문구는 절대 만들어내지 않는다 — 그건 근거를 아는 백엔드만 만든다).
 */
export type UpzoningFarRange = {
  min_pct?: number | null;
  max_pct?: number | null;
  note?: string | null;
  /** 상·하한이 같은 한 값 — '범위'가 아님(백엔드 판정). */
  is_collapsed?: boolean | null;
  /** 붕괴 시 왜 한 값인지 + 이 값이 상향 최댓값이 아님을 밝히는 정직 고지(백엔드 생성). */
  honest_disclosure?: string | null;
} | null | undefined;

export type UpzoningFarRangeDisplay = {
  /** 화면에 그대로 쓰는 문자열. 미확보는 "미확보", 붕괴는 범위 표기를 쓰지 않는다. */
  text: string;
  /** 범위가 붕괴했는가(범위 미산출). */
  collapsed: boolean;
  /** 백엔드가 실어보낸 정직 고지(없으면 null — 프론트가 지어내지 않는다). */
  disclosure: string | null;
};

export function formatUpzoningFarRange(
  range: UpzoningFarRange, digits = 1,
): UpzoningFarRangeDisplay {
  const lo = range && typeof range === "object" ? range.min_pct : null;
  const hi = range && typeof range === "object" ? range.max_pct : null;
  const loOk = typeof lo === "number" && Number.isFinite(lo);
  const hiOk = typeof hi === "number" && Number.isFinite(hi);
  if (!loOk || !hiOk) {
    return { text: "미확보", collapsed: false, disclosure: null };
  }
  const contract = range?.is_collapsed;
  // 계약 우선 — 계약이 없을 때만(구 페이로드) 동값 폴백.
  const collapsed = typeof contract === "boolean" ? contract : lo === hi;
  const disclosure =
    typeof range?.honest_disclosure === "string" && range.honest_disclosure.trim()
      ? range.honest_disclosure.trim()
      : null;
  if (collapsed) {
    // 범위 기호(~)를 쓰지 않는다 — 한 값임을 그대로 적는다.
    // ★"단일 경로 기준"이라 쓰지 않는다: 붕괴 사유는 "경로가 하나"가 아니라 "경로는 여럿인데
    //   목표 용도지역이 하나"다(자연녹지 = 3경로/1목표). 그렇게 쓰면 바로 아래 고지의
    //   "검토한 경로 3건…"과 같은 카드에서 1과 3이 싸운다. 어떤 붕괴 사유에도 참인
    //   "단일 값(범위 미산출)"만 적고, 왜 그런지는 고지가 말한다.
    //   ★계약 필드가 없는 구 캐시에서는 고지가 없어 이 문구만 남으므로 더욱 참이어야 한다.
    return {
      text: `${formatPercent(hi, digits)} · 단일 값(범위 미산출)`,
      collapsed: true,
      disclosure,
    };
  }
  return { text: formatPercentRange(lo, hi, digits), collapsed: false, disclosure };
}

// ── 종상향 "범위 붕괴" 문구 SSOT ────────────────────────────────────────────
//
// ★왜 여기로 모으나: `#709` 가 붕괴 **판정**은 `formatUpzoningFarRange` 로 모았는데,
//   그 판정을 받아 쓰는 **문구**는 표면마다 인라인 삼항으로 흩어져 있었다
//   (`ProjectAnalysisSummary` 라벨 · `AutoRecommendPanel` 조사). 같은 규칙이 두 벌이면
//   한쪽만 고쳐지고 다른 쪽이 남는다 — 이 저장소가 지번 표시에서 **세 벌**까지 갔던 그 경로다.
//
// ★문구의 요지: 붕괴값은 **도달 가능한 상한이 아니라 한 경로의 예상치**다.
//   "상한"·"까지"는 도달 가능성을 함의하므로 붕괴 시 쓰면 거짓이 된다.

/** 종상향 잠재 용적 라벨 — 붕괴면 "상한"이라고 부르지 않는다. */
export function upzoningPotentialLabel(collapsed: boolean): string {
  return collapsed ? "종상향 잠재(용적·단일 값)" : "종상향 잠재 상한(용적)";
}

/**
 * 종상향 문장의 **조사 분기** — 붕괴면 "까지 가능하며"가 거짓이 된다.
 * (문장이 숫자보다 오래 기억된다 — 조사까지 판정에 맞춘다.)
 */
export function upzoningReachClause(collapsed: boolean): string {
  return collapsed
    ? "이며, 이 경우 더 고밀·고수익 건축유형이 추천될 수 있습니다."
    : "까지 가능하며, 이 경우 더 고밀·고수익 건축유형이 추천될 수 있습니다.";
}

