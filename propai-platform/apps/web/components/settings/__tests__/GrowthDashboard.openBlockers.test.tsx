/**
 * ★**화면이 「왜 아직 열려 있는가」를 읽는가** — 사유는 실리는데 **소비처가 0곳**이었다.
 *
 * 【무엇이 있었나 · 라이브 실측 2026-09-13T00:4xZ (admin · offset 페이지네이션 + id dedupe)】
 * `status=open` **고유 705건**(동시각 서버 `total`=707 · 수집 707행 · **중복 2**) 중
 * **693건(98.3%)이 `window_expired`** — 즉 **구조적으로 닫힐 수 없다**. 창 안은 **12건**뿐이다.
 * `critical` **10건은 19~48일 전**(`feasibility` 폴백률 100% · `/tiles/vworld/wms` 503 시간당 2,349건 …).
 * `#1039` 가 `open_blockers`·`open_blocker_reason` 을 **훌륭한 문장으로** 실어 놨는데
 * **읽는 화면이 0곳**이었다 — 운영자는 「critical 10」만 보고 **48일 전 고착 기록**과
 * **지금 벌어지는 일**을 구별할 수 없었다.
 * ★그 PR 의 논거가 *「사유가 있는데 프로덕션 소비처 0」* 이었으므로 이것은
 *   ***소비처 0 을 한 층 위로 옮긴 것***이다(그 PR 리뷰 MAJOR-3 가 `.todo` 로 남겼다).
 *
 * 【★상태는 셋이 아니라 넷이다】`.todo` 는 「빈 배열 / null」 둘만 말했지만 타입이
 *   `open_blockers?: string[] | null` 이라 **부재(`undefined`)** 가 따로 있고,
 *   **web 은 api 와 따로 배포**되므로 도달 가능하다(구판 api · mock).
 *   ***부재를 「차단 사유 없음」으로 그리면 모르는 것을 안다고 주장하는 것이다.***
 *
 * 【어휘 제약 — 필드 저자(`sid=68ed1a1d`)와 합의】빈 배열에 **「치유 대기·예정」을 쓰지 않는다**.
 *   `open_blockers()` 는 `LIMIT 200` 절단·메타가드·닫기 실패를 **재지 않으므로** 그렇게 쓰면
 *   화면이 **완료를 약속**하게 된다. 잰 것만 말한다 — **「차단 사유 없음」**.
 *
 * 【이 파일이 잠그는 것】
 * · 네 상태가 **각각 다른 출력**을 낸다(한 칸으로 뭉치면 실패)
 * · `undefined` 가 **「차단 사유 없음」으로 읽히지 않는다**(양방향 대조군)
 * · `null` 은 **아무것도 안 그린다**(「해당 없음」도 주장이다)
 * · 사유 문장이 **잘리지 않는다**
 * · 모르는 코드가 **사라지지 않는다**(목록이 상한이 되지 않게)
 * · ★**배선** — 컴포넌트가 아니라 **대시보드 렌더 결과**에서 사유가 나온다
 *   (함수를 잠그는 것과 **그 함수가 불리는 것**은 다르다)
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a), post: vi.fn() },
  ApiClientError: class extends Error { status = 500 },
}));
vi.mock("@/lib/use-is-admin", () => ({ useIsAdmin: () => true }));

import { GrowthDashboard, InsightBlockers, type GrowthInsight } from "../GrowthDashboard";

const LONG_REASON =
  "치유기가 이 타입에 분기를 두지 않습니다. 자동 치유 후보는 선언된 타입에 한정됩니다. / " +
  "생성 후 2시간 창을 벗어났습니다. 후보 조회는 그보다 오래된 항목을 다시 읽지 않고, " +
  "생성 시각을 갱신하는 경로가 없어 다시 후보가 될 수 없습니다. 사람이 확인(ack)하는 것 외에 탈출구가 없습니다.";

type Blockers = string[] | null | undefined;

/** ★타입을 받는다 — 스텁도 계약이다. `as never` 로 우회하면 필수 필드가 늘어도 조용하다(§33). */
function makeInsight(
  blockers: Blockers,
  reason: string | null = null,
  status: GrowthInsight["status"] = "open",
): GrowthInsight {
  const base: GrowthInsight = {
    id: "i1",
    insight_type: "error_cluster",
    severity: "critical",
    status,
    window_start: null,
    window_end: null,
    metrics_json: {},
    narrative: "n1",
    recommended_action: null,
    created_at: "2026-09-01T00:00:00Z",
    open_blocker_reason: reason,
  };
  // ★`undefined` 는 **키 자체를 넣지 않는다.** 이유는 «모양이 달라진다»가 아니라 **위생**이다 —
  //   이 소비처에서 `obj.k` 는 두 경우를 구별하지 못하고 JSON 은 명시적 `undefined` 를 싣지도
  //   못한다(독립 리뷰 MINOR-3 가 내 초판의 과장된 근거를 정정했다). 그래도 **실제 응답과 같은
  //   모양**으로 두는 편이 다음 사람을 덜 헷갈리게 한다.
  if (blockers !== undefined) base.open_blockers = blockers;
  return base;
}

function renderBlockers(
  blockers: Blockers,
  reason: string | null = null,
  status: GrowthInsight["status"] = "open",
) {
  const { container } = render(
    <InsightBlockers insight={makeInsight(blockers, reason, status)} />,
  );
  return container;
}

/** ★합의된 어휘 제약 — **치유를 약속하는 말**. `open_blockers()` 가 `LIMIT 200` 절단·메타가드·
 *  닫기 실패를 **안 재므로** 화면이 완료를 약속하면 거짓이 된다(필드 저자 `sid=68ed1a1d`). */
const PROMISE_WORDS = ["치유 예정", "치유 대기", "곧 치유", "치유됩니다"];

describe("InsightBlockers — 네 상태가 각각 다른 출력을 낸다", () => {
  it("★★부재(undefined) 는 「판정 정보 없음」이고 **「차단 사유 없음」이 아니다**", () => {
    const c = renderBlockers(undefined);
    // 공허 방지 — 무언가는 그려져야 아래 단언이 공짜가 아니다.
    expect(c.textContent!.trim().length).toBeGreaterThan(0);
    expect(screen.getByTestId("insight-blockers-unknown")).toBeTruthy();
    // ★본판정 — 모르는 것을 «없다»로 말하지 않는다.
    expect(c.textContent).not.toContain("차단 사유 없음");
  });

  it("★대조군 — 빈 배열은 **「차단 사유 없음」이고**, 치유를 약속하지 않는다", () => {
    const c = renderBlockers([]);
    expect(screen.getByTestId("insight-blockers-none")).toBeTruthy();
    expect(c.textContent).toContain("차단 사유 없음");
    // ★어휘 제약: 완료를 약속하는 말을 쓰지 않는다.
    expect(c.textContent).not.toContain("치유 대기");
    expect(c.textContent).not.toContain("치유 예정");
  });

  it("★★열려 있지 않은 카드에는 **부재를 말하지 않는다** — 그 문장 자체가 거짓이 된다", () => {
    // 두 모집단: 같은 「부재」인데 status 로 갈린다(픽스처가 단일 모집단이면 이 유도가 무잠금).
    expect(renderBlockers(undefined, null, "open").textContent).toContain("판정 정보 없음");
    expect(renderBlockers(undefined, null, "acknowledged").textContent).toBe("");
  });

  it("★null 은 **아무것도 그리지 않는다** — 「해당 없음」도 주장이다", () => {
    const c = renderBlockers(null);
    expect(c.textContent).toBe("");
    expect(screen.queryByTestId("insight-blockers-none")).toBeNull();
    expect(screen.queryByTestId("insight-blockers-unknown")).toBeNull();
    expect(screen.queryByTestId("insight-blockers-list")).toBeNull();
  });

  it("★막힌 경우 — 코드 라벨과 **사유 전문**이 함께 나온다(자르지 않는다)", () => {
    const c = renderBlockers(["type_not_handled", "window_expired"], LONG_REASON);
    expect(screen.getByTestId("insight-blockers-list")).toBeTruthy();
    expect(screen.getByTestId("insight-blocker-type_not_handled")).toBeTruthy();
    expect(screen.getByTestId("insight-blocker-window_expired")).toBeTruthy();
    // ★사유를 **전문** 그대로 — 이 문장이 이 화면의 존재 이유다.
    expect(screen.getByTestId("insight-blocker-reason").textContent).toBe(LONG_REASON);
    expect(c.textContent).not.toContain("차단 사유 없음");
  });

  it("★★네 출력이 **서로 다르다** — 한 칸으로 뭉치면 이 단언이 죽는다", () => {
    const texts = [
      renderBlockers(undefined).textContent,
      renderBlockers([]).textContent,
      renderBlockers(null).textContent,
      renderBlockers(["window_expired"], "R").textContent,
    ];
    expect(new Set(texts).size).toBe(4);
  });

  it.each([
    ["부재", undefined as Blockers],
    ["빈 배열", [] as Blockers],
    ["막힘", ["type_not_handled", "window_expired"] as Blockers],
  ])("★★어휘 제약이 **%s 분기에도** 걸린다 — 어느 상태도 치유를 약속하지 않는다", (_n, b) => {
    const c = renderBlockers(b, "사유 전문");
    // ★초판은 이 제약을 `[]` 분기에만 걸었다. 그런데 **완료를 약속」이 실제로 해로운 자리는
    //   막혀 있는 쪽**이다(독립 리뷰 MAJOR-1 ②).
    for (const w of PROMISE_WORDS) expect(c.textContent).not.toContain(w);
  });

  it("★모르는 코드는 **코드 그대로** 나온다 — 목록이 상한이 되지 않게", () => {
    renderBlockers(["brand_new_code_2027"]);
    expect(screen.getByTestId("insight-blocker-brand_new_code_2027").textContent)
      .toBe("brand_new_code_2027");
  });

  // ★★★**리터럴 핀** — 초판은 `not.toContain("_")` 로 «원시 코드가 아니다」만 봤다.
  //   그건 **삭제 축만** 잡는다. 독립 리뷰가 실측으로 반증했다:
  //     · 라벨을 「치유 예정」으로 바꾸기          → `::VERDICT=SURVIVED`
  //     · 두 코드의 라벨을 맞바꾸기                → `::VERDICT=SURVIVED`
  //   ★★그리고 내가 §6 에 인용한 「기계 kill」은 **센티넬 인공물**이었다 —
  //     변이 도구의 치환 문자열 `__MUTATED__` 가 **밑줄을 품어** `not.toContain("_")` 에
  //     걸린 것뿐이다. *잡히도록 보장된 변이를 골라 거짓 CAUGHT 를 본 것*이다.
  //   ⇒ 문구를 **핀**한다. 표현이 아니라 **계약**이다 — 운영자가 판단 근거로 읽는 문장이고,
  //     백엔드 형제가 같은 판단을 이미 내렸다(`healing_rules.py` 의 코드 리터럴 핀).
  it.each([
    ["type_not_handled", "치유기에 이 타입 분기 없음"],
    ["window_expired", "후보 창 경과"],
    ["action_not_healable", "권장 조치가 치유 대상 아님"],
  ])("★등록된 코드 %s 는 **정확히 그 문장**으로 나온다(핀)", (code, label) => {
    renderBlockers([code]);
    expect(screen.getByTestId(`insight-blocker-${code}`).textContent).toBe(label);
  });

  it("★★두 라벨을 **맞바꿔도** 잡힌다 — 핀이 없으면 이 축이 통째로 열린다", () => {
    renderBlockers(["type_not_handled", "window_expired"]);
    // 각 배지가 **자기 코드의** 문장을 단다(핀이 서로 다름을 같은 실행에서 확인).
    const a = screen.getByTestId("insight-blocker-type_not_handled").textContent!;
    const b = screen.getByTestId("insight-blocker-window_expired").textContent!;
    expect(a).toContain("치유기에 이 타입 분기 없음");
    expect(b).toContain("후보 창 경과");
    expect(a).not.toContain("후보 창 경과");
  });

  it("★★사유 배지 사이에 **텍스트 구분자**가 있다 — CSS 에만 의존하지 않는다", () => {
    const c = renderBlockers(["type_not_handled", "window_expired"]);
    // 구분자가 없으면 DOM 텍스트에서 「…분기 없음후보 창 경과」로 **붙는다**(리뷰 MEDIUM-1 실측).
    expect(c.textContent).not.toContain("없음후보 창 경과");
    expect(c.textContent).toContain("·");
  });
});

describe("★배선 — 대시보드 렌더 결과에서 사유가 나온다", () => {
  beforeEach(() => { getMock.mockReset(); });
  afterEach(() => { vi.clearAllMocks(); });

  function mountWith(items: unknown[]) {
    getMock.mockImplementation((path: string) => {
      if (typeof path === "string" && path.includes("/growth/insights")) {
        return Promise.resolve({
          items,
          total: items.length,
          actionable_counts: { critical: items.length, warn: 0, info: 0 },
        });
      }
      return Promise.resolve({});
    });
    render(<GrowthDashboard />);
  }

  it("★★컴포넌트만 잠그면 **호출부는 무잠금**이다 — 카드에서 실제로 나오는지 본다", async () => {
    mountWith([makeInsight(["type_not_handled", "window_expired"], LONG_REASON)]);
    // 공허 방지 선단언 — 카드 자체가 렌더됐는지 먼저.
    expect(await screen.findByText("n1")).toBeTruthy();
    // ★본판정 — 사유가 **화면에** 있다.
    expect((await screen.findByTestId("insight-blocker-reason")).textContent).toBe(LONG_REASON);
  });

  it("★대조군 — `null`(열려 있지 않음)이면 카드는 그려지되 blocker 블록은 **없다**", async () => {
    mountWith([makeInsight(null)]);
    expect(await screen.findByText("n1")).toBeTruthy();   // 카드는 있다
    expect(screen.queryByTestId("insight-blockers-list")).toBeNull();
    expect(screen.queryByTestId("insight-blockers-none")).toBeNull();
    expect(screen.queryByTestId("insight-blockers-unknown")).toBeNull();
  });
});
