import { describe, it } from "vitest";

/**
 * ★부채를 **초록 안에 보이게** 남긴다(2026-09-12 독립 리뷰 MAJOR-3).
 *
 * `GET /growth/heal-log` 가 `blocked` · `blocked_total` · `blocked_by_reason` 을 싣기 시작했는데
 * **읽는 화면이 0곳**이다. 그 PR 이 고치려던 결함이 정확히 «발행되는데 읽는 경로 0» 이었으므로,
 * 소비처 0 은 **같은 형태의 재발**이다.
 *
 * ★산문(계획서 §3)에만 적으면 기계가 아무것도 묻지 않는다 — 그래서 `it.todo` 로 남긴다.
 *   이 파일이 초록 목록에 «todo» 로 뜨는 동안, 그 부채는 **보이는 상태**다.
 *
 * ★UI 구현은 이 PR 의 범위가 아니다(리뷰어도 요구하지 않았다).
 *   첫 소비자는 당분간 **사람(통합자)** 이고, 그것은 소비처 0 의 변명이 아니라 현재 사실이다.
 */
describe("heal-log blocked 소비처(부채)", () => {
  it.todo("대시보드가 heal-log 의 blocked / blocked_total / blocked_by_reason 을 렌더한다");
  it.todo("blocked_by_reason 이 global_cap 과 trigger_cap 을 **따로** 보여 준다(합산 금지)");
});
