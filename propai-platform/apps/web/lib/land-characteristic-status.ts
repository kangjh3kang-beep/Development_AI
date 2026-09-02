/**
 * 필지 특성 칩의 status → 색 매핑 (순수·컴포넌트 밖).
 *
 * ## 종전 결함 (2026-08-27 실측)
 *
 * `statusColors[c.status] || statusColors.safe` 였다. 폴백이 `safe` = **초록**이라
 * 미지 status 가 **안전하다고 관측된 것처럼** 보였고, 같은 표에 실재하는 `danger`(빨강)가
 * 가려졌다.
 *
 * 생산자는 **검증 0의 LLM JSON** 이다:
 *   `lib/ai-analyze-client.ts:83` → `JSON.parse(_stripFences(text)) as T`
 * 그리고 소비부에 `c.status as "safe" | "warning" | "danger"` 라는 **거짓 캐스트**가 있어
 * 타입은 닫힌 것처럼 보이는데 런타임은 열려 있었다.
 *
 * ★이 칩은 **색 단독 신호**다(렌더가 label + value 뿐). 그래서 미지일 때는 색을 중립으로
 *   바꾸는 것만으로 부족하고 **글자로도** 말해야 한다 — 색을 못 보는 사용자에게 신호가 0이 된다.
 */

import { resolveKnown } from "@/lib/unknown-value";

/**
 * ★표를 **닫힌 유니온에 결속**한다(선례: `LegacyLedgerTable.tsx:100`).
 * 등급을 추가하면 tsc 가 표를 채우라고 강제한다 — 종전 `Record<string, …>` 은 안 그랬다.
 * ★단 이것은 **화면 표기의 오라클일 뿐 생산자의 오라클이 아니다** — 생산자가 LLM 자유 JSON
 *   이라 「네 번째 값」은 여전히 온다. 그래서 tsc 가 아니라 `resolveKnown` 이 런타임을 막는다.
 */
export type KnownCharacteristicStatus = "safe" | "warning" | "danger";

export const CHARACTERISTIC_STATUS_COLORS: Record<KnownCharacteristicStatus, string> = {
  safe: "text-[var(--status-success)] bg-[var(--status-success)]/10 border-[var(--status-success)]/20",
  warning: "text-[var(--status-warning)] bg-[var(--status-warning)]/10 border-[var(--status-warning)]/20",
  danger: "text-red-400 bg-red-500/10 border-red-500/20",
};

/** 미지 status 의 표기 — 중립 회색. ★`safe`(초록)로 접던 자리다. */
/**
 * ★대비: `--text-tertiary` 는 라이트에서 3.18:1 로 AA(4.5:1) 미달이다(9px 글자라
 *   AA-large 요건에도 못 든다). 이 수정의 명분이 「색을 못 보는 사용자」인 만큼
 *   본문 대비를 쓴다 — `--text-secondary` = #555B6E on #FFFFFF **6.76:1**(토큰 주석 실측).
 */
export const UNKNOWN_CHARACTERISTIC_CLS =
  "text-[var(--text-secondary)] bg-[var(--surface-strong)] border-[var(--line-strong)]";

/** 색을 못 보는 사용자에게도 「모른다」가 전달되게 하는 글자. */
export const UNKNOWN_CHARACTERISTIC_LABEL = "확인 불가";

export type CharacteristicStatus = {
  /** 칩에 적용할 클래스 */
  readonly cls: string;
  /** 표에 없는 값이었는가 — 호출부가 글자 표기를 결정하는 근거 */
  readonly unknown: boolean;
};

/** status → 칩 표기. 미지면 **표의 어떤 색도 쓰지 않는다**. */
export function resolveCharacteristicStatus(raw: unknown): CharacteristicStatus {
  const found = resolveKnown(CHARACTERISTIC_STATUS_COLORS, raw);
  return found.known
    ? { cls: found.value, unknown: false }
    : { cls: UNKNOWN_CHARACTERISTIC_CLS, unknown: true };
}
