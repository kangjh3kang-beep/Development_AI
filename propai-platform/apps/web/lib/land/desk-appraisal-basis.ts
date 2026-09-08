/**
 * §Ⅵ「시점수정·시장통계 근거」 줄 조립 — **순수 함수**.
 *
 * ## 왜 순수 함수로 뺐나 (독립 리뷰 R4 MEDIUM-2 · 2026-09-08)
 *
 * 종전 락은 **소스 grep** 이라, 렌더를 죽이는 변이를 통과시켰다(리뷰어 실측):
 *
 *     {ms.housing_time_adjust.basis ?  →  {false && ms.housing_time_adjust.basis ?
 *     → 10 passed  ::VERDICT=SURVIVED
 *
 * 토큰은 그대로 남아 있으니 문자열 검사는 초록이다. 저장소 §A-3 이 *"소스 grep 대신 렌더
 * 결과를 본다"* 라고 이미 적어 둔 자리다. 주석 스트립은 넣었지만 **죽은 표현식**은 열려 있었다.
 * ⇒ 판단을 순수 함수로 꺼내 **행위를 직접 태운다**(§D-14 처방 그대로).
 *
 * ## 겸사겸사 고친 비대칭 (R4 LOW-3)
 *
 * 같은 블록에서 `cap_rate` 와 `housing_time_adjust` 는 `basis` 를 렌더하는데
 * **전월세전환율만 `pct` 만** 찍고 있었다. 한 자리에서 조립하므로 그 비대칭이 구조적으로 불가능해진다.
 */
import type { DeskAppraisalResult } from "./desk-appraisal";

/** R-ONE 실측으로 표기해도 되는 출처 코드. 프론트·백엔드가 공유하는 계약 문자열이다. */
export const RONE_SOURCE = "R-ONE";

type Stat = { source?: string; pct?: number; basis?: string; rate?: number; factor?: number; scope?: string } | null;

/**
 * `basis`(백엔드 산문)와 `scope`(기계 판독 축)를 함께 덧붙인다.
 *
 * ★`scope` 를 여기서 **실제로 소비**한다(독립 리뷰 R4 MEDIUM-6). 종전에는 `Stat` 타입에
 *   선언만 있고 렌더가 **0건**이라, 그 선언을 단언하는 락이 «소비처 없는 선언»을 지키는
 *   장식이었다. 정직성 전체를 `basis` 산문이 나르고 있었고, 산문은 다듬을 때마다 흔들린다.
 * ★판정은 프론트가 스스로 한다 — 응답의 `market_stats.region`(해석된 지역)과 `scope`(그 값이
 *   실제로 나온 범위)가 다르면 **요청 지역 값이 아니다**. 백엔드 문구를 안 믿어도 성립한다.
 */
function withBasis(head: string, stat: Stat, region?: string): string {
  const parts: string[] = [head];
  if (stat?.basis) parts.push(stat.basis);
  if (stat?.scope && region && stat.scope !== region) {
    parts.push(`범위 ${stat.scope} — 요청 지역(${region}) 실데이터가 아닙니다`);
  }
  return parts.join(" — ");
}

/**
 * §Ⅵ 에 실제로 그릴 줄들을 만든다. **R-ONE 출처가 아닌 통계는 줄을 만들지 않는다**
 * (지어낸 «실측» 라벨 금지 — 이 PR 계열이 고쳐 온 결함 클래스).
 */
export function buildMarketBasisLines(res: DeskAppraisalResult): string[] {
  const ms = res.market_stats ?? {};
  const lines: string[] = [];

  if (res.time_adjust_basis) lines.push(`· 시점수정: ${res.time_adjust_basis}`);

  const cap = ms.cap_rate as Stat;
  if (cap?.source === RONE_SOURCE) {
    lines.push(withBasis(`· 자본환원율(R-ONE 실측): ${cap.pct}%`, cap, ms.region));
  }

  const conv = ms.jeonse_conversion_rate as Stat;
  if (conv?.source === RONE_SOURCE) {
    lines.push(withBasis(`· 전월세전환율(R-ONE 실측): ${conv.pct}%`, conv, ms.region));
  }

  const housing = ms.housing_time_adjust as Stat;
  if (housing?.source === RONE_SOURCE) {
    lines.push(withBasis(`· 주택가격지수 누적변동: ${housing.factor}`, housing, ms.region));
  }

  // ★주소에서 시·도를 해석하지 못했으면 그 사실을 말한다(독립 리뷰 R5 LOW-1).
  //   그때 `region` 은 "전국" 이지만 그것은 **해석 결과가 아니라 기본값**이라,
  //   위 `scope !== region` 판정이 «전국 == 전국» 으로 조용히 침묵한다.
  if (ms.region_resolved === false) {
    lines.push("· 지역 해석: 주소에서 시·도를 해석하지 못해 전국 값을 적용했습니다(이 지역 실데이터가 아닙니다).");
  }

  if (!ms.rone_available) {
    lines.push("· 시장통계: R-ONE 통계표 미설정 구간은 근사값 적용(관리자 설정 시 실데이터 전환).");
  }
  return lines;
}
