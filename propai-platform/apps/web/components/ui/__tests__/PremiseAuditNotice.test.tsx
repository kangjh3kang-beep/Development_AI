/**
 * 전제 감사 고지 락 — **침묵과 무결을 구분한다**.
 *
 * ★감사 모듈(`app/services/zoning/premise_audit.py`)이 명문으로 요구한 축이다:
 *   *"`checked == 0` 이면 «위반 없음»이 **공허**하다 — 호출부가 그 사실을 알 수 있어야 한다."*
 *   형제 `IntegrityWarnings` 는 그 정보가 없어 **그 축을 포기한다고 선언**했다. 여기는 갖는다.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  PremiseAuditNotice,
  premiseAuditPower,
  premiseAuditState,
  type PremiseAudit,
} from "@/components/ui/PremiseAuditNotice";

const VIOLATION = {
  relation: "dominant_argmax",
  title: "우세 정합 — dominant_zone == 면적 최대 용도지역",
  detail: "우세 용도지역(자연녹지지역)이 면적 최대 용도지역(제2종일반주거지역)과 다릅니다.",
};

/** 백엔드가 내는 네 모양. ★픽스처가 **두 모집단을 실제로 가른다**(차가 0인 픽스처는 잠금이 아니다). */
const FIXTURES: Record<string, PremiseAudit> = {
  violations: { violations: [VIOLATION], checked: 6, registered: 6 },
  failed: { violations: [], checked: 0, registered: null, reason: "audit_failed", detail: "top3 가 list 라 .get() 이 터졌습니다" },
  vacuous: { violations: [], checked: 1, registered: 6, structurally_vacuous: ["path_invariance_zone"] },
  partial: { violations: [], checked: 4, registered: 6, structurally_vacuous: ["path_invariance_zone"] },
  clean: { violations: [], checked: 6, registered: 6 },
};

describe("premiseAuditState — 다섯 상태가 **서로 다른 판정**이다", () => {
  it("★파티션형 — 각 픽스처가 자기 상태로만 판정된다(두 갈래가 겹치면 실패)", () => {
    for (const [expected, fx] of Object.entries(FIXTURES)) {
      expect(premiseAuditState(fx), `${expected} 픽스처가 다른 상태로 판정됐다`).toBe(expected);
    }
    // ★공허 진리 방지 — 픽스처가 실제로 5종인가(줄어들면 위 루프가 조용히 약해진다).
    expect(Object.keys(FIXTURES)).toHaveLength(5);
  });

  it("★실패를 **공허보다 먼저** 본다 — 순서가 뒤집히면 「왜 못 했는지」를 잃는다", () => {
    // 실패 경로는 violations:[] · checked:0 이라, 뒤로 미루면 «공허»로 오분류된다.
    expect(premiseAuditState(FIXTURES.failed)).toBe("failed");
    expect(premiseAuditState(FIXTURES.failed)).not.toBe("vacuous");
  });

  it("입력이 없거나 형태가 아니면 **아무 말도 하지 않는다**(지어내지 않는다)", () => {
    // ★`checked` 가 없으면 **해석할 수 없는 형태**다 — 그때 「공허」라 외치면 그것이 위양성이다.
    for (const bad of [null, undefined, 42, "x", [], {}, { violations: [] }]) {
      expect(premiseAuditState(bad as never), `${JSON.stringify(bad)} 에 주장을 만들었다`).toBe("clean");
    }
    // ★음성 대조군 — 그렇다고 **모든 입력에 clean** 을 주는 것은 아니다(그러면 이 단언이 공허하다).
    expect(premiseAuditState({ violations: [], checked: 0, registered: 6 })).toBe("vacuous");
  });
});

describe("premiseAuditPower — ★`structurally_vacuous` 를 판정력에서 뺀다", () => {
  it("실효 판정력과 원래 checked 를 **둘 다** 낸다(한 수로 뭉개면 오독된다)", () => {
    const p = premiseAuditPower(FIXTURES.partial);
    expect(p).toEqual({ effective: 3, checked: 4, vacuous: 1, registered: 6 });
    // ★두 수가 실제로 **다르다** — 같으면 이 단언이 원리적으로 아무것도 안 잠근다.
    expect(p.effective).not.toBe(p.checked);
  });

  it("★구조상 공허한 관계만 판정됐으면 실효 판정력은 0 이다", () => {
    expect(premiseAuditPower(FIXTURES.vacuous).effective).toBe(0);
    // 그런데 원래 checked 는 0 이 아니다 — 그 차이가 「공허」의 정의다.
    expect(premiseAuditPower(FIXTURES.vacuous).checked).toBe(1);
  });

  it("음수로 내려가지 않는다(경계 양방향)", () => {
    expect(premiseAuditPower({ checked: 1, structurally_vacuous: ["a", "b", "c"] }).effective).toBe(0);
  });
});

describe("PremiseAuditNotice — 렌더", () => {
  it("★깨끗하면 **아무것도 그리지 않는다**(정상 화면에 배지를 늘리지 않는다)", () => {
    const { container } = render(<PremiseAuditNotice audit={FIXTURES.clean} />);
    expect(container.firstChild).toBeNull();
    const { container: nil } = render(<PremiseAuditNotice audit={null} />);
    expect(nil.firstChild).toBeNull();
  });

  it("위반은 **백엔드 원문 그대로** 싣는다(화면이 문구를 지어내지 않는다)", () => {
    render(<PremiseAuditNotice audit={FIXTURES.violations} />);
    const box = screen.getByTestId("premise-audit-notice");
    // ★**정규식으로 조회하지 않는다.** 첫 판은 `new RegExp(detail.slice(0,20))` 을 썼는데
    //   문구의 `(자연녹지지역)` 괄호가 **정규식 그룹**으로 읽혀 매칭이 0건이 됐다 —
    //   이 저장소가 기록해 둔 바로 그 함정(`grep` 이 `[`·`(` 를 메타문자로 읽어 오보).
    //   원문 대조는 **평문 부분문자열**로 한다.
    expect(box.textContent ?? "").toContain(VIOLATION.title);
    expect(box.textContent ?? "").toContain(VIOLATION.detail);
    expect(box.dataset.state).toBe("violations");
  });

  it("★판정 불가는 **왜** 못 했는지를 싣는다(무언 실패 금지)", () => {
    render(<PremiseAuditNotice audit={FIXTURES.failed} />);
    expect(screen.getByText(/top3 가 list/)).toBeTruthy();
  });

  it("★공허는 「위반 없음」이라고 **말하지 않는다** — 감사 모듈이 요구한 축", () => {
    render(<PremiseAuditNotice audit={FIXTURES.vacuous} />);
    const box = screen.getByTestId("premise-audit-notice");
    expect(box.dataset.state).toBe("vacuous");
    expect(box.textContent ?? "").toContain("확인하지 못함");
    // ★금지어 검사는 **제목(=주장)에만** 건다. 본문은 「「이상 없음」이 아니라」처럼 그 낱말을
    //   **부정문 안에서 인용**하는데, 부분문자열 검사는 인용과 주장을 **원리적으로 못 가른다**
    //   — 첫 판이 정확히 그렇게 **내가 쓴 안내문에** 걸렸다(위양성도 결함이다).
    //   ★교훈: *"주석·안내문에 예시를 적으면 그 예시가 다음 검사의 위양성이 된다."*
    const heading = box.querySelector("p")?.textContent ?? "";
    expect(heading.length).toBeGreaterThan(0);
    for (const forbidden of ["위반 없음", "이상 없음", "정상", "통과"]) {
      expect(heading, `공허 상태의 **제목**이 «${forbidden}» 이라 말했다`).not.toContain(forbidden);
    }
  });

  it("★부분 판정은 **실효/등록** 을 말하고, 원 검사 수도 함께 밝힌다", () => {
    render(<PremiseAuditNotice audit={FIXTURES.partial} />);
    const t = screen.getByTestId("premise-audit-notice").textContent ?? "";
    expect(t).toContain("3");   // 실효 판정력(checked 4 - vacuous 1)
    expect(t).toContain("6");   // registered
    expect(t).toContain("4");   // ★원 checked 도 밝힌다 — 한 수로 뭉개지 않는다
    expect(t).toMatch(/보증하지 않습니다/);
  });

  it("★네 상태의 제목이 **서로 다르다**(두 갈래가 같은 말을 하면 정보가 0이다)", () => {
    const headings = (["violations", "failed", "vacuous", "partial"] as const).map((k) => {
      const { container, unmount } = render(<PremiseAuditNotice audit={FIXTURES[k]} />);
      const h = container.querySelector("p")?.textContent ?? "";
      unmount();
      return h;
    });
    expect(new Set(headings).size, `제목이 겹친다: ${JSON.stringify(headings)}`).toBe(4);
    expect(headings.every((h) => h.trim().length > 0)).toBe(true);
  });

  /**
   * ★**부채를 초록 안에 드러낸다**(커밋 메시지에만 적으면 안 드러난다).
   * `routers/auto_zoning.py` 도 `premise_audit` 를 응답에 싣는데, 그 경로는 위반이 **있을 때만**
   * `warnings`/`disclosure` 로 우회한다 — **공허 축은 그 경로도 못 본다.**
   * 두 표면을 한 PR 에서 건드리면 회귀 범위가 겹쳐서 별건으로 남긴다.
   */
  it.todo("통합분석(auto_zoning) 표면도 이 고지를 쓴다 — 지금은 warnings 우회뿐이라 공허 축이 없다");
});
