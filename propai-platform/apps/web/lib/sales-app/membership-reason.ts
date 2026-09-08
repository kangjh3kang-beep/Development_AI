/**
 * 채용 승인 시 **조직도 멤버십이 왜 안 붙었는지** 를 사람 말로 옮긴다.
 *
 * ## 왜 별도 모듈인가 (2026-09-08 · 적대 리뷰 M2)
 *
 * 서버는 종전에 `membership_linked: boolean` 하나만 줬고, **그 여섯 가지 상황이 같은 `false`** 였다:
 * 적용대상 아님 · 권한 없음 · 조직도 미시드 · 조직 테이블 미존재 · 멱등 무변경.
 * 그런데 조치가 **전부 다르다** — 특히 `ORG_NOT_SEEDED` 는 *"조직도를 시드하고 다시 승인하라"* 는
 * **해결 가능한** 상태인데, 라이브 현장 대부분이 여기에 해당해 **그것이 기본 경로**였다.
 *
 * ★게다가 화면은 그 `false` 마저 **읽지 않고 버렸다**(`.then(() => loadApps())`).
 *   승인자는 «승인은 됐는데 조직도엔 아무도 없다» 를 원인 없이 마주쳤다.
 *
 * 판정을 여기 순수 함수로 꺼내 둔 이유는 **문구가 아니라 매핑을 태우기 위해서**다 —
 * 컴포넌트 안에 삼항식으로 두면 렌더 없이는 못 재고, 그러면 락이 문자열 grep 이 된다.
 */

/** 서버 `membership_reason` 의 전체 집합 — 백엔드 `market.py` 와 1:1. */
export const MEMBERSHIP_REASONS = [
  "LINKED",
  "ALREADY_MEMBER",
  "NOT_APPLICABLE",
  "NOT_AUTHORIZED",
  "ORG_NOT_SEEDED",
  "ORG_TABLE_MISSING",
  "IDEMPOTENT_NO_CHANGE",
] as const;

export type MembershipReason = (typeof MEMBERSHIP_REASONS)[number];

/** 연결된 것으로 치는 사유 — 백엔드 `_LINKED_REASONS` 와 같아야 한다. */
export const LINKED_REASONS: readonly MembershipReason[] = ["LINKED", "ALREADY_MEMBER"];

const NOTES: Record<MembershipReason, string> = {
  LINKED: "",
  ALREADY_MEMBER: "",
  NOT_APPLICABLE: "이 공고는 현장 연계 채용이 아니라 조직도 멤버십은 만들지 않았습니다.",
  NOT_AUTHORIZED: "승인은 되었지만 회원님이 이 현장의 관리자가 아니어서 조직도에는 추가되지 않았습니다.",
  ORG_NOT_SEEDED:
    "승인은 되었지만 이 현장에 조직도가 아직 없어 배치를 보류했습니다 — 조직도를 만든 뒤 다시 승인해 주세요.",
  ORG_TABLE_MISSING: "이 현장은 조직도를 사용하지 않아 멤버십 배치는 건너뛰었습니다.",
  IDEMPOTENT_NO_CHANGE: "이미 처리된 신청이라 변경된 것이 없습니다.",
};

/**
 * ★알 수 없는 사유도 **말을 한다.** 빈 문자열로 떨어뜨리면 그 순간 이 모듈이 존재하기 전과 같아진다
 *   («아무 말도 없다» = 종전 결함). 서버가 사유를 새로 추가했는데 여기만 안 고친 경우가 그것이다.
 */
export function membershipNote(reason: string | undefined): string {
  if (reason && reason in NOTES) {
    return NOTES[reason as MembershipReason];
  }
  return `승인은 되었지만 조직도 배치 결과를 알 수 없습니다(사유: ${reason ?? "응답에 없음"}).`;
}
