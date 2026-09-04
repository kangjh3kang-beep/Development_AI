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

/**
 * ★**백엔드가 실제로 내는 페이로드**만 쓴다.
 *
 * 첫 판의 픽스처 다섯 중 **셋이 프로덕션에 존재하지 않는 모양**이었다(적대 리뷰 MAJOR-2).
 * `checked` 를 「판정한 수」로 오해해 `checked:1`·`checked:4` 를 지어냈는데, 실측하면
 * `audit()` 의 `checked` 는 **예외가 안 난 관계 수**라 **언제나 `registered` 와 같다**:
 *
 *     audit(정상ctx) → checked 6 / registered 6
 *     audit({})      → checked 6 / registered 6      ← 빈 입력에도 6
 *
 * 그리고 성공 경로는 **항상** `structurally_vacuous: ["path_invariance_zone"]` 를 덧씌운다.
 * ★그래서 「정상 부지」 픽스처가 프로덕션 모양이 아니었고, **«정상 화면이 깨끗하다»가 초록인데
 *   실제 정상 화면은 깨끗하지 않았다.** 픽스처가 그 축을 **원리적으로 못 태우고 있었다.**
 */
const FIXTURES: Record<string, PremiseAudit> = {
  violations: { violations: [VIOLATION], checked: 6, registered: 6, structurally_vacuous: ["path_invariance_zone"] },
  failed: { violations: [], checked: 0, registered: null, reason: "audit_failed", detail: "top3 가 list 라 .get() 이 터졌습니다" },
  // ★감사기가 **한 건도 실행되지 않았다**(전부 예외). 실패 표식 없이 이 모양이면 그 자체가 신호다.
  vacuous: { violations: [], checked: 0, registered: 6 },
  // ★관계 일부가 **실행 중 죽었다** — 「입력 부족」이 아니다(그 정보는 생산자에 없다).
  partial: { violations: [], checked: 4, registered: 6, structurally_vacuous: ["path_invariance_zone"] },
  // ★★**배선된 백엔드가 정상 부지에서 실제로 내는 바로 그 페이로드.**
  //   첫 판은 `structurally_vacuous` 키가 **없는** 모양을 「정상」이라 불렀고, 그래서
  //   프로덕션 정상 부지가 경고를 받는 것을 이 락이 못 봤다.
  clean: { violations: [], checked: 6, registered: 6, structurally_vacuous: ["path_invariance_zone"] },
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

describe("premiseAuditPower — ★두 축을 **분리**해 낸다(한 수로 뭉개면 오독된다)", () => {
  it("시도율과 판별력 없는 관계 수가 **다른 필드**로 나온다", () => {
    expect(premiseAuditPower(FIXTURES.partial)).toEqual({
      attempted: 4, registered: 6, vacuous: 1, vacuousKeys: ["path_invariance_zone"],
    });
  });

  it("★**섞지 않는다** — 정상 부지는 `attempted === registered` 이고 vacuous 가 있어도 그대로다", () => {
    const p = premiseAuditPower(FIXTURES.clean);
    expect(p.attempted).toBe(p.registered);
    expect(p.vacuous).toBe(1);
    // ★첫 판은 여기서 `4 - 1 = 3` 처럼 빼서 `registered` 와 비교했고, 그래서 **정상 부지가
    //   전부 경고**를 받았다. 두 축이 **서로를 깎지 않는다**는 것이 이 단언의 내용이다.
    expect(premiseAuditState(FIXTURES.clean)).toBe("clean");
  });

  it("★`checked` 가 없으면 0 으로 보되, 그것으로 **주장을 만들지는 않는다**", () => {
    expect(premiseAuditPower({}).attempted).toBe(0);
    expect(premiseAuditPower({}).registered).toBeNull();
    // 수가 없으면 상태는 clean(=무주장)이다 — 위 0 을 「공허」로 승격시키지 않는다.
    expect(premiseAuditState({})).toBe("clean");
  });

  it("어휘 밖 형태는 조용히 무시한다(문자열 아닌 키·null 배열)", () => {
    expect(premiseAuditPower({ checked: 6, structurally_vacuous: [null, "", 7, "ok"] as never }).vacuous).toBe(1);
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

  it("★사유가 비면 **기계 키를 사용자에게 내보내지 않는다**", () => {
    // ★백엔드는 `detail: str(e)[:200]` 인데 `str(e)` 는 **빈 문자열일 수 있다**
    //   (`raise ValueError()`). 그때 첫 판은 화면에 «audit_failed» 를 찍었다 —
    //   *"왜 못 했는지를 싣는다"* 는 이 상태의 존재 이유가 그 순간 무너진다.
    //   ★이 락이 없으면 봉합이 **초록 안에서 무잠금**이다(내 변이가 SURVIVED 로 잡았다).
    for (const detail of ["", "   ", undefined]) {
      const { container, unmount } = render(
        <PremiseAuditNotice audit={{ violations: [], checked: 0, registered: null, reason: "audit_failed", detail }} />,
      );
      const t = container.textContent ?? "";
      expect(t, `detail=${JSON.stringify(detail)} 에서 기계 키가 노출됐다`).not.toContain("audit_failed");
      expect(t).toContain("원인을 기록하지 못했습니다");
      unmount();
    }
    // ★음성 대조군 — 사유가 **있으면** 그것을 그대로 쓴다(대체 문구로 덮지 않는다).
    render(<PremiseAuditNotice audit={FIXTURES.failed} />);
    const box = screen.getByTestId("premise-audit-notice");
    expect(box.textContent ?? "").toContain("top3 가 list");
    expect(box.textContent ?? "").not.toContain("원인을 기록하지 못했습니다");
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

  it("★부분 **실행**은 시도/등록을 말하고, 사유를 **날조하지 않는다**", () => {
    render(<PremiseAuditNotice audit={FIXTURES.partial} />);
    const box = screen.getByTestId("premise-audit-notice");
    const heading = box.querySelector("p")?.textContent ?? "";
    // ★제목을 **완전 일치**로 못 박는다. 첫 판은 `toContain("3")` 식 자릿수 자루였고,
    //   제목이 다른 수로 되돌아가도 본문 어딘가에 그 숫자가 있어 **초록이었다**(리뷰 MEDIUM-3).
    expect(heading).toBe("전제 감사 부분 실행 · 4/6");
    // ★**날조 금지** — 백엔드는 「입력 부족」이라는 사유를 준 적이 없다. 그 정보는 생산자에 없다.
    expect(box.textContent ?? "").not.toContain("입력이 부족");
    expect(box.textContent ?? "").toContain("보증하지 않습니다");
  });

  it("★★위반 상태에서 「위 수에 포함」이라고 **말하지 않는다** — 검출된 위반을 부정하는 문장", () => {
    // ★2차 적대 리뷰 MAJOR-1. 첫 판은 이 문장을 **조건 없이** 모든 상태에 붙였고,
    //   위반 상태의 제목이 `전제 불일치 검출 · 1건` 이라 「위 수」가 **위반 개수**로 읽혔다.
    //   → *"검출된 1건 = 판별력 없는 그 1건"* 으로 읽혀 **진짜 위반이 기각된다.**
    //   ★락 22건이 전부 초록이었다: 이 픽스처가 그 문장을 **실제로 렌더하는데**
    //     단언이 title·detail·state 뿐이라 **아무도 그 줄을 안 봤다.**
    render(<PremiseAuditNotice audit={FIXTURES.violations} />);
    const t = screen.getByTestId("premise-audit-notice").textContent ?? "";
    expect(t, "위반 상태에서 「포함」을 주장했다").not.toContain("포함돼 있으나");
    // ★그렇다고 정보를 **버리지도 않는다** — 무관함을 명시한다(두 모집단이 갈린다).
    expect(t).toContain("path_invariance_zone");
    expect(t).toContain("무관합니다");
  });

  it("★공허 상태에서는 **아예 안 밝힌다** — 실행 0에 「포함」은 성립하지 않는다", () => {
    render(<PremiseAuditNotice audit={{ violations: [], checked: 0, registered: 6, structurally_vacuous: ["path_invariance_zone"] }} />);
    const t = screen.getByTestId("premise-audit-notice").textContent ?? "";
    expect(t).not.toContain("포함");
    expect(t).not.toContain("path_invariance_zone");
    expect(t).toContain("확인하지 못함");
  });

  it("★부분 실행에서만 「포함」이 참이다 — 판별력 없는 관계도 **실행은 됐다**", () => {
    render(<PremiseAuditNotice audit={FIXTURES.partial} />);
    const t = screen.getByTestId("premise-audit-notice").textContent ?? "";
    expect(t).toContain("위 실행 수에 포함돼 있으나");
  });

  it("★본문 수치도 잠근다 — 제목만 못 박으면 구멍이 **한 줄 아래로 이동**한다", () => {
    // ★2차 리뷰 MAJOR-2: 제목을 완전일치로 잠갔더니 본문이 같은 두 수를 **무잠금으로** 다시
    //   인쇄했다(`{attempted}` → `{registered}` 변이가 SURVIVED — 제목 4/6 과 본문 6개가
    //   **자기모순인데 22건 전부 초록**). ★산문을 못 박지 않고 **수만** 태운다.
    render(<PremiseAuditNotice audit={FIXTURES.partial} />);
    const ps = Array.from(screen.getByTestId("premise-audit-notice").querySelectorAll("p"));
    const body = ps[1]?.textContent ?? "";
    const nums = (body.match(/\d+/g) ?? []).map(Number);
    const { attempted, registered } = premiseAuditPower(FIXTURES.partial);
    // 본문이 인쇄하는 두 수가 **파생값과 같아야** 한다(자릿수 자루가 아니라 순서까지).
    expect(nums.slice(0, 2)).toEqual([registered, attempted]);
  });

  it("★판별력 없는 관계는 **맥락으로만** 밝히고 비율에 섞지 않는다", () => {
    render(<PremiseAuditNotice audit={FIXTURES.partial} />);
    const t = screen.getByTestId("premise-audit-notice").textContent ?? "";
    expect(t).toContain("path_invariance_zone");
    expect(t).toContain("판별력이 없는");
    // ★그런데 그것이 **경보를 만들지는 않는다** — 정상 부지는 여전히 무렌더다.
    const { container } = render(<PremiseAuditNotice audit={FIXTURES.clean} />);
    expect(container.firstChild).toBeNull();
  });

  it("★판별력 없는 관계가 **0건이면 그 줄을 아예 안 그린다**(빈 괄호 금지)", () => {
    // 생산자 B(`auto_zoning`)와 생산자 A 의 실패 경로는 `structurally_vacuous` 를 **안 낸다**.
    // 가드가 `>= 0` 으로 약화되면 «판별력이 없는 검사 0건()» 이 렌더된다(리뷰 MINOR-5).
    render(<PremiseAuditNotice audit={{ violations: [VIOLATION], checked: 6, registered: 6 }} />);
    const t = screen.getByTestId("premise-audit-notice").textContent ?? "";
    expect(t).not.toContain("판별력이 없는");
    expect(t).not.toContain("()");
  });

  it("★톤 계약 — **경보(위반)와 맥락(그 외)** 이 시각적으로 갈린다", () => {
    // 설계가 «경보 vs 맥락» 을 명시적으로 갈랐는데 그 축을 태우는 단언이 없었다(리뷰 MINOR-6).
    const cls = (a: PremiseAudit) => {
      const { container, unmount } = render(<PremiseAuditNotice audit={a} />);
      const c = (container.firstChild as HTMLElement).className;
      unmount();
      return c;
    };
    const err = cls(FIXTURES.violations);
    expect(err).toContain("status-error");
    // ★파티션형 — 나머지 세 상태는 **전부** 경보 톤이 아니어야 한다.
    for (const k of ["failed", "vacuous", "partial"] as const) {
      expect(cls(FIXTURES[k]), `${k} 가 경보 톤을 썼다`).not.toContain("status-error");
      expect(cls(FIXTURES[k])).toContain("status-warning");
    }
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
   *
   * ★사유를 **정정한다**(적대 리뷰 MEDIUM-5). 첫 판은 *"그 경로는 공허 축을 **못 본다**"* 라고
   * 적었는데 **거짓**이다 — `routers/auto_zoning.py:1947` 은 **위임이 성공한 경우에 한해**
   * 위반 유무와 무관하게 `{checked, registered, violations}` 를 싣는다. **데이터는 있다.**
   * ★★그 조건을 빠뜨린 첫 정정문도 **조건 없는 단정**이었다(2차 리뷰 MINOR-4):
   *   그 대입은 `if isinstance(top3, dict):` **안**이고 다시 `try:` **안**이라,
   *   `auto_recommend_top3` 가 터지면 `except` 가 시나리오를 degrade 하며
   *   **`premise_audit` 키를 아예 안 만든다** — **감사가 가장 필요한 실패 경로에 데이터가 없다.**
   *   ★*정정문이 원문보다 짧고 단정적이라 더 신뢰받는다*(§27-c).
   * 없는 것은 **프론트 소비처**다(전수: `premise_audit` 소비처는 이 카드 1곳).
   *
   * ★***«데이터가 없다»와 «소비처가 없다»는 처방이 다르다***(§29) — 첫 판 문구를 읽은 사람은
   * «백엔드부터 고쳐야 한다» 로 간다. 실제로는 `<PremiseAuditNotice audit={…} />` 한 줄이다.
   * 두 표면을 한 PR 에서 건드리면 회귀 범위가 겹쳐 별건으로 남긴다.
   */
  it.todo("통합분석(auto_zoning) 표면도 이 고지를 쓴다 — 데이터는 이미 있고 **소비처만** 없다");
});
