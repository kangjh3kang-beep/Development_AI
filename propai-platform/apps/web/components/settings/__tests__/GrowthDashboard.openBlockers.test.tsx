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

import { GrowthDashboard, InsightBlockers } from "../GrowthDashboard";

const LONG_REASON =
  "치유기가 이 타입에 분기를 두지 않습니다. 자동 치유 후보는 선언된 타입에 한정됩니다. / " +
  "생성 후 2시간 창을 벗어났습니다. 후보 조회는 그보다 오래된 항목을 다시 읽지 않고, " +
  "생성 시각을 갱신하는 경로가 없어 다시 후보가 될 수 없습니다. 사람이 확인(ack)하는 것 외에 탈출구가 없습니다.";

type Blockers = string[] | null | undefined;

function makeInsight(blockers: Blockers, reason: string | null = null) {
  const base = {
    id: "i1",
    insight_type: "error_cluster",
    severity: "critical",
    status: "open",
    window_start: null,
    window_end: null,
    metrics_json: {},
    narrative: "n1",
    recommended_action: null,
    created_at: "2026-09-01T00:00:00Z",
    open_blocker_reason: reason,
  } as Record<string, unknown>;
  // ★`undefined` 는 **키 자체를 넣지 않는다** — `open_blockers: undefined` 로 넣으면
  //   «부재»가 아니라 «명시적 undefined» 라 실제 API 응답과 모양이 달라진다.
  if (blockers !== undefined) base.open_blockers = blockers;
  return base as never;
}

function renderBlockers(blockers: Blockers, reason: string | null = null) {
  const { container } = render(<InsightBlockers insight={makeInsight(blockers, reason)} />);
  return container;
}

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

  it("★모르는 코드는 **코드 그대로** 나온다 — 목록이 상한이 되지 않게", () => {
    renderBlockers(["brand_new_code_2027"]);
    expect(screen.getByTestId("insight-blocker-brand_new_code_2027").textContent)
      .toBe("brand_new_code_2027");
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
