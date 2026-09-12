import { describe, it } from "vitest";

/**
 * ★부채를 **초록 안에 보이게** 남긴다(2026-09-12 독립 적대 리뷰 MAJOR-3).
 *
 * `GET /growth/insights` 가 `open_blockers` · `open_blocker_reason` 을 싣기 시작했는데
 * **읽는 화면이 0곳**이다. ★그 PR 의 논거가 정확히 *「`HEAL_UNHANDLED_REASONS` 에 사유가
 * 있는데 **프로덕션 소비처 0**」* 이었으므로, ***소비처 0 을 한 층 위로 옮긴 것***이다 —
 * 같은 형태의 재발이고, PR 이 선언한 원칙을 그 PR 의 신규 코드에 적용하지 못한 자리다.
 *
 * ★산문(계획서 §3)에만 적으면 기계가 아무것도 묻지 않는다 — 그래서 `it.todo` 로 남긴다.
 *   형제 선례가 같은 날 같은 이유로 이 형식을 썼다:
 *   `components/settings/__tests__/heal-log-blocked-consumer.todo.test.ts`
 *
 * ★타입 미러(`GrowthDashboard.tsx` 의 `GrowthInsight`)는 **이번에 맞췄다** — 렌더는 별건이다.
 */
describe("growth insights open_blockers 소비처(부채)", () => {
  it.todo("대시보드가 open 인사이트의 open_blocker_reason 을 렌더한다");
  it.todo("빈 배열(후보)과 null(열려 있지 않음)을 **다르게** 보여 준다 — 같은 칸으로 뭉치지 않는다");
});
