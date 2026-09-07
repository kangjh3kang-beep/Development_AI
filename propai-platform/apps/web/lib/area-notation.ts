/**
 * 면적 표기 SSOT — **전용은 ㎡, 공급은 평형**.
 *
 * ## 왜 이 모듈이 필요한가 (라이브 실해 · 2026-09-06 사용자 신고)
 *
 * 같은 화면에 **전용 기준 실거래 마커**(「1,840만/평」)와 **공급 기준 분양가**
 * (「1,200만원/평」)가 **같은 단위 표기로 나란히** 있었다. 사용자가 *«왜 분양가가
 * 주변 시세보다 낮나»* 로 신고했고, 재 보니 **둘 다 맞는 값인데 눈금이 달랐다.**
 *
 * > ★**표기 통일은 미관이 아니라 오독을 만드는 결함이다.**
 *
 * ## ★대응은 공식이 아니라 **관례표**다 (실측)
 *
 * 사용자가 지정한 셋을 역산하면 전용률이 **일정하지 않다**:
 *
 *     전용 59㎡ → 25평형   역산 전용률 71.4%
 *     전용 74㎡ → 30평형              74.6%
 *     전용 84㎡ → 34평형              74.7%
 *
 * **소형일수록 공용 비중이 커서 전용률이 낮다.** 그래서 공식 하나로 덮을 수 없고,
 * **관례 앵커표 + 공식 폴백**으로 간다. ★폴백일 때는 **폴백이라고 말한다** —
 * 지어낸 값과 관례값이 같은 얼굴을 하면 안 된다.
 *
 * ## ★평당 상수는 여기서 만들지 않는다
 *
 * `formatters.PYEONG_SQM` 을 **재수출**한다. 오늘 내가 `construction-cost-params.ts` 에
 * `3.3058` 을 새로 두어 **두 벌**을 만들었고(정본은 `3.305785`), 내 SSOT 락이
 * **한쪽 표기만 감시**해서 못 잡았다. 같은 실수를 여기서 반복하지 않는다.
 */
import { PYEONG_SQM } from "@/lib/formatters";

export { PYEONG_SQM };

/**
 * 전용면적(㎡) → 평형(공급 기준 통칭) **관례 앵커표**.
 *
 * ★실측 뒷받침: 남양주 8개월 469건의 최빈 전용면적이 **60·85·75·73·135㎡** 로
 *   아래 59/84/74/73/134 계열과 일치한다(2026-09-06).
 * ★사용자 지정 셋(59→25 · 74→30 · 84→34)이 이 표의 계약이며 락이 지킨다.
 */
export const EXCLUSIVE_TO_PYEONGHYEONG: ReadonlyArray<readonly [number, number]> = [
  [39, 17], [49, 21], [59, 25], [64, 27], [72, 29], [74, 30],
  [79, 32], [84, 34], [91, 37], [101, 40], [114, 46], [134, 53], [154, 61],
] as const;

/** 앵커 매칭 허용오차(㎡). 실거래는 59.97·84.93 처럼 소수가 붙는다. */
const ANCHOR_TOLERANCE_SQM = 2.0;

/**
 * 국민평형(전용 84㎡)의 **표준 공급면적(㎡)** — 프론트 전용률의 **유일 정본**.
 *
 * ★백엔드 `suggest._REF_SUPPLY_SQM = 112.4`("84타입 표준 공급면적")의 미러다.
 *   `84 / 112.4 = 0.747` 이고 공급 **34.0평** — 사용자 확인(*"전용 84㎡는 공급 34평형"*)과
 *   일치하며, 이 표의 `[84, 34]` 앵커와도 정합한다.
 */
export const REF_SUPPLY_SQM = 112.4;
/** 국민평형 전용면적(㎡) — 전용률의 분자. */
export const REF_EXCLUSIVE_SQM = 84;

/**
 * 표준 전용률(전용/공급). ★**리터럴을 쓰지 않고 파생**한다.
 *
 * ★★2026-09-07 실측 — 이 저장소에 전용률 사본이 **여섯 벌**이었고 값이 갈렸다:
 *   `suggest._JEONYULRYUL` 0.747 · 여기 **0.75** · `PricingBandPanel` 0.747 …
 *   프론트 안에서만 84㎡ 기준 공급면적이 **112.0㎡(33.88평) ↔ 112.4㎡(34.02평)** 로
 *   갈렸다. 사본은 **값이 어긋날 때 아무 소리도 내지 않는다.**
 *   → 정본 하나(`REF_SUPPLY_SQM`)에서 나눠 얻고, **다른 파일은 이것을 import 한다.**
 */
export const EXCLUSIVE_TO_SUPPLY_RATIO =
  Math.round((REF_EXCLUSIVE_SQM / REF_SUPPLY_SQM) * 1000) / 1000;

/** 앵커 밖에서 쓰는 표준 전용률(= 위 파생값). ★관례값이지 정밀값이 아니다. */
const FALLBACK_EXCLUSIVE_RATIO = EXCLUSIVE_TO_SUPPLY_RATIO;

export interface Pyeonghyeong {
  /** 평형 수치(공급 기준 통칭). */
  pyeong: number;
  /** 관례 앵커표에서 나왔는가. false 면 공식 폴백이다. */
  fromAnchor: boolean;
}

/** 전용면적(㎡) → 평형. 앵커 우선, 없으면 공식 폴백(그 사실을 함께 돌려준다). */
export function toPyeonghyeong(exclusiveSqm: number): Pyeonghyeong | null {
  if (!Number.isFinite(exclusiveSqm) || exclusiveSqm <= 0) return null;
  let best: readonly [number, number] | null = null;
  let bestDiff = Infinity;
  for (const pair of EXCLUSIVE_TO_PYEONGHYEONG) {
    const diff = Math.abs(pair[0] - exclusiveSqm);
    if (diff <= ANCHOR_TOLERANCE_SQM && diff < bestDiff) {
      best = pair;
      bestDiff = diff;
    }
  }
  if (best) return { pyeong: best[1], fromAnchor: true };
  // ★폴백 — 전용 ÷ 표준전용률 = 공급㎡ → 평
  return {
    pyeong: Math.round(exclusiveSqm / FALLBACK_EXCLUSIVE_RATIO / PYEONG_SQM),
    fromAnchor: false,
  };
}

/** 전용면적 표기 — **㎡로만**. */
export function formatExclusive(exclusiveSqm: number | null | undefined): string {
  if (exclusiveSqm == null || !Number.isFinite(exclusiveSqm) || exclusiveSqm <= 0) return "—";
  return `${Math.round(exclusiveSqm * 10) / 10}㎡`;
}

/** 평형 표기 — **평형으로만**. 폴백이면 `약` 을 붙여 관례값과 구별한다. */
export function formatPyeonghyeong(exclusiveSqm: number | null | undefined): string {
  if (exclusiveSqm == null) return "—";
  const p = toPyeonghyeong(exclusiveSqm);
  if (!p) return "—";
  return p.fromAnchor ? `${p.pyeong}평형` : `약 ${p.pyeong}평형`;
}

/**
 * 병행 표기 — `"전용 84㎡ (34평형)"`.
 *
 * ★**전용을 평으로, 공급을 ㎡로 쓰지 않는다.** 그 뒤바뀜이 이번 신고의 원인이다.
 */
export function formatAreaDual(exclusiveSqm: number | null | undefined): string {
  if (exclusiveSqm == null || !Number.isFinite(exclusiveSqm) || exclusiveSqm <= 0) return "—";
  // ★★2026-09-07 사용자 지적 — 종전 `"전용 84㎡ (34평형)"` 은 괄호 안 값에 **기준이
  //   없어** 「전용이 34평」으로 읽힌다. 실제 전용 84㎡ 는 **25.4평**이고, 34평형은
  //   **공급** 기준 통칭이다. → 두 값에 각각 기준을 붙이고, 전용의 평 환산도 함께 보인다.
  const excPyeong = Math.round((exclusiveSqm / PYEONG_SQM) * 10) / 10;
  return (
    `전용 ${formatExclusive(exclusiveSqm)}(${excPyeong}평)` +
    ` · 공급 ${formatPyeonghyeong(exclusiveSqm)}`
  );
}
