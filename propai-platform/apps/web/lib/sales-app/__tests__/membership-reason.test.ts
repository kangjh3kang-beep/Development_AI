/**
 * ★멤버십 연결 «사유» 가 사람 말로 **구별되게** 도달하는가 — 행위 락.
 *
 * 종전 결함(2026-09-08 적대 리뷰 M2): 서버가 `membership_linked: boolean` 하나만 줬고
 * 여섯 상황이 같은 `false` 였으며, **화면은 그 boolean 마저 읽지 않고 버렸다.**
 *
 * 그래서 이 파일은 두 가지를 각각 태운다:
 *   ① 사유마다 **서로 다른** 문구가 나온다(같은 문구면 나눈 의미가 없다)
 *   ② 프론트 목록이 백엔드 SSOT(`market.py:_MEMBERSHIP_REASONS`)와 **일치**한다 — 파생형
 *
 * ★①이 없으면 «전부 같은 한 문장» 으로 되돌려도 초록이다(= 종전 상태와 구별 불가).
 * ★②가 없으면 백엔드가 사유를 늘렸을 때 프론트만 조용히 낡는다.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  LINKED_REASONS,
  MEMBERSHIP_REASONS,
  SILENT_REASONS,
  membershipNote,
  type MembershipReason,
} from "../membership-reason";

/** 백엔드 SSOT 튜플을 **소스에서 파생**한다(손으로 옮겨 적으면 그 사본이 다음 결함이다). */
function backendReasons(): string[] {
  const market = path.resolve(
    __dirname,
    "../../../../api/app/api/endpoints/sales/market.py",
  );
  const src = readFileSync(market, "utf8");
  const m = src.match(/^_MEMBERSHIP_REASONS = \(([\s\S]*?)^\)/m);
  if (!m) throw new Error("백엔드 `_MEMBERSHIP_REASONS` 튜플을 찾지 못했다 — 조회기가 죽었다");
  return [...m[1].matchAll(/"([A-Z_]+)"/g)].map((x) => x[1]);
}

describe("membership-reason — 백엔드 SSOT 와의 파생 관계", () => {
  it("조회기가 살아 있다(대조군) — 백엔드에서 사유를 실제로 읽어 온다", () => {
    const back = backendReasons();
    // ★공허 진리 가드. 이게 없으면 아래 «일치» 가 «양쪽 다 빈 배열» 과 구별되지 않는다.
    expect(back.length).toBeGreaterThanOrEqual(5);
    expect(back).toContain("ORG_NOT_SEEDED");
  });

  it("프론트 목록이 백엔드 목록과 같다(순서 무관)", () => {
    expect([...MEMBERSHIP_REASONS].sort()).toEqual(backendReasons().sort());
  });

  it("연결로 치는 사유가 목록의 부분집합이다", () => {
    for (const r of LINKED_REASONS) expect(MEMBERSHIP_REASONS).toContain(r);
  });
});

describe("membershipNote — 사유마다 다른 말을 하는가", () => {
  /** 사람에게 문구를 **보여야 하는** 사유 = 전체 − 의도적으로 조용한 것. */
  const SPEAKING = MEMBERSHIP_REASONS.filter(
    (r) => !(SILENT_REASONS as readonly string[]).includes(r),
  );

  it("침묵 목록이 «빠뜨림» 을 위장하지 않는다 — 두 집합이 전체를 정확히 덮는다", () => {
    // ★`SILENT_REASONS` 를 늘리면 그만큼 SPEAKING 이 줄어든다.
    //   그 자체가 검토를 강제한다 — 침묵은 **선언해야** 얻는다.
    expect(SPEAKING.length + SILENT_REASONS.length).toBe(MEMBERSHIP_REASONS.length);
    expect(SPEAKING.length).toBeGreaterThanOrEqual(4); // 공허 방지
    // 연결 성공 사유는 반드시 침묵 쪽에 있다.
    for (const r of LINKED_REASONS) expect(SILENT_REASONS).toContain(r);
  });

  it("말해야 하는 사유는 **전부** 비어 있지 않은 문구를 낸다", () => {
    for (const r of SPEAKING) {
      expect(membershipNote(r), `사유 ${r} 가 아무 말도 하지 않는다`).not.toBe("");
    }
  });

  it("★그 문구들이 서로 **다르다** — 하나로 뭉치면 나눈 의미가 없다", () => {
    const notes = SPEAKING.map((r) => membershipNote(r));
    expect(new Set(notes).size).toBe(notes.length);
  });

  it("조용한 사유는 **정말로** 조용하다(문구를 붙였다가 잊는 것도 결함)", () => {
    for (const r of SILENT_REASONS) expect(membershipNote(r)).toBe("");
  });

  it("★★조직도 미시드는 «다시 승인하면 된다» 는 **조치**를 말한다", () => {
    // 이 사유만 해결 가능한 보류다 — 다른 사유와 같은 급으로 읽히면 승인자가 포기한다.
    const note = membershipNote("ORG_NOT_SEEDED" satisfies MembershipReason);
    expect(note).toContain("조직도");
    expect(note).toContain("다시 승인");
    // 반대편: 조직도를 안 쓰는 현장은 **조치를 권하지 않는다**(할 일이 없다).
    expect(membershipNote("ORG_TABLE_MISSING")).not.toContain("다시 승인");
  });

  it("★모르는 사유도 **말을 한다** — 침묵은 종전 결함 그 자체다", () => {
    expect(membershipNote("SOMETHING_NEW")).toContain("SOMETHING_NEW");
    expect(membershipNote(undefined)).not.toBe("");
  });
});
