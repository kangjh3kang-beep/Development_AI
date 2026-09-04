/**
 * AI 학습 사례 승인 화면 — 배선 락(2026-08-19).
 *
 * 【이 락이 잡으려는 결함】
 * "사람이 승인해야만 도는 게이트인데 사람에게 문이 없다." 백엔드는 학습 사례를
 * status='candidate' 로만 쌓고, AI 프롬프트는 status='active' 만 읽는다. 승인 API 는
 * 있었지만 그걸 **부르는 화면이 0개**라 자가학습이 구조적으로 영원히 비어 있었다.
 *
 * 【왜 소스 grep 이 아니라 렌더인가】
 * 이 저장소는 소스 검사가 "주석 처리 + 임포트 유지" 변이에 두 번 뚫렸다(CLAUDE.md §A.3).
 * 그래서 여기서는 **실제로 렌더하고 실제로 클릭해서** 어떤 요청이 나가는지를 본다.
 *
 * 【공허 진리 방지】
 * 단언 앞에 "행이 실제로 그려졌다"를 먼저 세운다. 목록이 0건이면 "위반 0"이 참이 되는데
 * 그건 통과가 아니라 검사가 죽은 것이다.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a), post: (...a: unknown[]) => postMock(...a) },
  ApiClientError: class ApiClientError extends Error {
    status: number;
    payload: unknown;
    constructor(message: string, status: number, payload?: unknown) {
      super(message);
      this.status = status;
      this.payload = payload;
    }
  },
}));

import LearningApprovalPanel from "../LearningApprovalPanel";

/** 권리 확인된 후보와 권리 미확인 후보 — 두 모집단이 다른 값을 낸다. */
const CANDIDATES = [
  {
    id: "ex-cand-1",
    service: "avm",
    analysis_type: "avm_valuation",
    status: "candidate",
    tenant_id: "tenant-A",
    content_hash: "hash-1",
    input_summary: "역삼동 대지 감정 입력요약",
    input_summary_truncated: false,
    good_output: "후보-미승인-본문",
    good_output_truncated: true,
    created_at: "2026-08-18T10:00:00+00:00",
    train_allowed: true,
    rights_scope: "train_ok",
  },
  {
    id: "ex-cand-2",
    service: "permit",
    analysis_type: "permit_ai",
    status: "candidate",
    tenant_id: "tenant-B",
    content_hash: "hash-2",
    input_summary: "인허가 입력요약",
    input_summary_truncated: false,
    good_output: "권리미확인-본문",
    good_output_truncated: false,
    created_at: "2026-08-17T10:00:00+00:00",
    train_allowed: false,
    rights_scope: null,
  },
];

function listPayload(items = CANDIDATES) {
  return { items, total: items.length, statuses: ["candidate"], service: null, tenant_id: null, limit: 20, offset: 0 };
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  getMock.mockResolvedValue(listPayload());
  postMock.mockResolvedValue({ example_id: "ex-cand-1", status: "active" });
});

afterEach(() => {
  vi.restoreAllMocks();
});

/**
 * promote 응답을 **붙잡아 둔다**(요청이 비행 중인 상태를 실제로 만든다).
 * 반환 배열의 n번째를 호출하면 n번째 POST 가 그때 끝난다.
 * ★가드(in-flight 잠금)는 "요청이 아직 안 끝났을 때"만 관찰 가능하다 — 즉시 resolve 하는
 *   목으로는 그 상태를 만들 수 없어 검사가 공허해진다.
 */
function holdPromoteResponses(): Array<() => void> {
  const release: Array<() => void> = [];
  postMock.mockImplementation(
    () =>
      new Promise((resolve) => {
        release.push(() => resolve({ example_id: "x", status: "active" }));
      }),
  );
  return release;
}

/** 호출 URL 에서 쿼리스트링을 뗀 **경로 세그먼트**만 남긴다. */
function pathOf(call: unknown[]): string {
  return String(call[0]).split("?")[0];
}

/**
 * GET 호출 중 후보목록 경로만 추린다.
 *
 * ★`includes` 가 아니라 **정확 일치**다(2026-08-19 적대리뷰 M1b). 부분문자열로 보면
 *   `/candidates` → `/candidatesX` 같은 **접미 오타**가 그대로 통과한다(리뷰어 실측:
 *   34/34 SURVIVED). 프로덕션에서는 404 다. 정확 일치로 두면 접미 오타 시 이 목록이
 *   비고, 이 함수를 쓰는 모든 케이스가 한꺼번에 빨강이 된다(파생 잠금).
 */
function candidateCalls() {
  return getMock.mock.calls.filter((c) => pathOf(c) === "/growth/learning/candidates");
}

/** 호출 URL 의 쿼리 파라미터를 **파싱해서** 본다(부분문자열 대조 금지 — 값이 접두인 다른
 *  파라미터에 걸리거나 접미 오타를 놓친다). */
function qOf(call: unknown[]): URLSearchParams {
  return new URLSearchParams(String(call[0] ?? "").split("?")[1]);
}

describe("AI 학습 사례 승인 화면 배선", () => {
  it("후보 목록 API 를 실제로 부른다(status=candidate 기본)", async () => {
    render(<LearningApprovalPanel />);
    await waitFor(() => expect(candidateCalls().length).toBeGreaterThan(0));
    const url = String(candidateCalls()[0][0]);
    // 경로는 **정확히** — 접미 오타(/candidatesX)는 프로덕션 404 다.
    expect(url.split("?")[0]).toBe("/growth/learning/candidates");
    expect(new URLSearchParams(url.split("?")[1]).get("status")).toBe("candidate");
  });

  it("승인 버튼이 그 항목의 id 로 promote 를 부른다(한 번에 한 건)", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);

    // ★공허 진리 가드 — 행이 실제로 그려졌는지 먼저 세운다.
    const rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBe(CANDIDATES.length);

    const firstRow = rows[0];
    expect(within(firstRow).getByText("후보-미승인-본문")).toBeTruthy();

    await user.click(within(firstRow).getByRole("button", { name: "승인" }));

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    expect(postMock.mock.calls[0][0]).toBe("/growth/learning/promote");
    expect(postMock.mock.calls[0][1].body).toEqual({
      example_id: "ex-cand-1",
      status: "active",
      // 권리가 확인된 행이므로 인수 없이 승인된다(대조군은 아래 권리 게이트 케이스).
      acknowledge_unverified_rights: false,
    });

    // ★한 번 눌러 한 건만 처리한다 — 목록 전체가 함께 승인되면 사람 승인이 아니다.
    expect(postMock).toHaveBeenCalledTimes(1);
  });

  it("거부 버튼은 rejected 로 보낸다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBeGreaterThan(0);

    await user.click(within(rows[1]).getByRole("button", { name: "거부" }));

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    expect(postMock.mock.calls[0][1].body).toEqual({
      example_id: "ex-cand-2",
      status: "rejected",
      acknowledge_unverified_rights: false, // 거부는 권리와 무관하다
    });
  });

  it("일괄/전체 승인 경로가 없다 — 승인·거부 버튼은 항목 수만큼만 존재한다", async () => {
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBe(2); // 전제

    // 사람이 센 목록이 아니라 렌더 결과에서 **파생**한다 — 새 일괄 버튼이 생기면 수가 어긋난다.
    expect(screen.getAllByRole("button", { name: "승인" }).length).toBe(rows.length);
    expect(screen.getAllByRole("button", { name: "거부" }).length).toBe(rows.length);
    for (const label of [/전체/, /모두/, /일괄/, /자동/]) {
      expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
  });

  it("학습 권리가 확인되지 않은 후보를 숨기지 않고 경고와 함께 보여준다", async () => {
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");

    // ★숨기면 관리자는 "후보가 없다"고 오독한다 — 건수가 줄지 않아야 한다.
    expect(rows.length).toBe(CANDIDATES.length);
    expect(within(rows[1]).getByText(/학습 사용 권리가 확인되지 않은 자료/)).toBeTruthy();
    // 권리 확인된 행에는 경고가 없다(위양성 가드 — 대조군).
    expect(within(rows[0]).queryByText(/학습 사용 권리가 확인되지 않은 자료/)).toBeNull();
  });

  /* ---------------------------------------------------------------- */
  /*  학습권리 게이트 (2026-08-19 적대리뷰 HIGH)                        */
  /*  ★두 모집단이 **다른 UI 상태**를 낸다: 권리 확인된 행은 곧바로     */
  /*    승인 가능, 미확인 행은 인수 체크 전까지 승인 불가.              */
  /* ---------------------------------------------------------------- */

  it("권리 미확인 행은 확인 체크 전에는 승인할 수 없다", async () => {
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBe(2); // 전제

    // 권리 확인된 행(대조군) — 처음부터 승인 가능하고 인수 체크 자체가 없다.
    expect(within(rows[0]).getByRole("button", { name: "승인" })).toHaveProperty(
      "disabled",
      false,
    );
    expect(within(rows[0]).queryByRole("checkbox")).toBeNull();

    // 권리 미확인 행 — 승인 잠김. 거부는 안전한 방향이라 열려 있어야 한다.
    expect(within(rows[1]).getByRole("button", { name: "승인" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(within(rows[1]).getByRole("button", { name: "거부" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("확인 책임을 인수하면 승인이 열리고 그 사실을 서버로 보낸다", async () => {
    const user = userEvent.setup();
    postMock.mockResolvedValue({
      example_id: "ex-cand-2",
      status: "active",
      rights_acknowledged: true,
    });
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");

    await user.click(within(rows[1]).getByRole("checkbox"));

    const approve = within(rows[1]).getByRole("button", { name: "승인" });
    expect(approve).toHaveProperty("disabled", false);
    await user.click(approve);

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(1));
    expect(postMock.mock.calls[0][1].body).toEqual({
      example_id: "ex-cand-2",
      status: "active",
      acknowledge_unverified_rights: true, // ★서버가 이 값 없이는 409 로 거부한다
    });
    // 인수 사실을 화면에도 남긴다(조용히 넘어가면 관리자가 무엇을 했는지 모른다).
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toMatch(/확인 책임을 인수/),
    );
  });

  it("인수 체크를 되돌리면 승인이 다시 잠긴다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    const box = within(rows[1]).getByRole("checkbox");

    await user.click(box);
    expect(within(rows[1]).getByRole("button", { name: "승인" })).toHaveProperty(
      "disabled",
      false,
    );
    await user.click(box);
    expect(within(rows[1]).getByRole("button", { name: "승인" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("한 행을 인수해도 다른 행은 잠긴 채로 남는다(행 단위 문턱)", async () => {
    const user = userEvent.setup();
    getMock.mockResolvedValue(
      listPayload([
        { ...CANDIDATES[1], id: "ex-a", content_hash: "h-a" },
        { ...CANDIDATES[1], id: "ex-b", content_hash: "h-b" },
      ]),
    );
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBe(2);

    await user.click(within(rows[0]).getByRole("checkbox"));
    expect(within(rows[0]).getByRole("button", { name: "승인" })).toHaveProperty(
      "disabled",
      false,
    );
    // ★인수가 화면 전체에 번지면 그건 일괄 승인이다 — 행 단위여야 한다.
    expect(within(rows[1]).getByRole("button", { name: "승인" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  /* ---------------------------------------------------------------- */
  /*  상태값 배선 — 변이 재분류에서 나온 진짜 구멍(2026-08-19)          */
  /*  ★탭의 `key` 는 표시 문구가 아니라 **백엔드로 가는 상태값**이다.   */
  /*    문구로 뭉뚱그렸더니 `candidate`/`rejected` 를 바꾸는 변이가      */
  /*    살아남았다(그 탭을 누르면 서버가 400 을 낸다).                  */
  /* ---------------------------------------------------------------- */

  it("모든 상태 탭이 백엔드 어휘 그대로 요청한다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    // ★사람이 센 탭 목록을 쓰지 않는다 — 렌더된 탭 버튼에서 **파생**한다.
    //   비교 대상은 백엔드 어휘(learning_loop._VALID_STATUSES)라 컴포넌트와 독립이다.
    const tabButtons = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-pressed") !== null);
    expect(tabButtons.length, "상태 탭이 0개 — 검사가 공허하다").toBe(3);

    for (const btn of tabButtons) await user.click(btn);

    const asked = new Set(candidateCalls().map((c) => qOf(c).get("status")));
    expect(asked).toEqual(new Set(["candidate", "active", "rejected"]));
  });

  it("거부됨 목록도 렌더하고 그 상태로 표시한다", async () => {
    getMock.mockResolvedValue(
      listPayload([{ ...CANDIDATES[0], id: "ex-rej", status: "rejected" }]),
    );
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBe(1); // 전제

    const badge = within(rows[0]).getByText("거부됨");
    // 상태별 색 분기가 실제로 갈리는지 — 토큰 이름으로 본다(색 리터럴 아님).
    expect(badge.className).toContain("status-error");
    // 이미 처리된 건이라 승인/거부 버튼이 없다.
    expect(within(rows[0]).queryByRole("button", { name: "승인" })).toBeNull();
    expect(within(rows[0]).queryByRole("button", { name: "거부" })).toBeNull();
  });

  it("대조군 — 승인 대기 배지는 거부됨과 다른 토큰을 쓴다", async () => {
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    const badge = within(rows[0]).getByText("승인 대기");
    expect(badge.className).not.toContain("status-error");
  });

  it("어느 테넌트에 주입될지 화면에 보인다", async () => {
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(within(rows[0]).getByText(/tenant-A/)).toBeTruthy();
    expect(within(rows[1]).getByText(/tenant-B/)).toBeTruthy();
  });

  it("일부만 표시된 본문은 잘렸다고 알린다", async () => {
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(within(rows[0]).getByText(/일부만 표시/)).toBeTruthy();
    expect(within(rows[1]).queryByText(/일부만 표시/)).toBeNull(); // 대조군
  });

  it("학습셋 다운로드가 dataset 엔드포인트를 부른다", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:stub");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    getMock.mockImplementation((path: string) =>
      String(path).includes("/growth/learning/dataset")
        ? Promise.resolve({ message: '{"messages":[]}' })
        : Promise.resolve(listPayload()),
    );

    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");
    await user.click(screen.getByRole("button", { name: "승인된 학습셋 내려받기" }));

    await waitFor(() =>
      expect(
        getMock.mock.calls.some((c) => pathOf(c) === "/growth/learning/dataset"),
      ).toBe(true),
    );
    expect(createObjectURL).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("페이지 크기·시작 위치를 요청에 실어 보낸다", async () => {
    render(<LearningApprovalPanel />);
    await waitFor(() => expect(candidateCalls().length).toBeGreaterThan(0));
    const q = new URLSearchParams(String(candidateCalls()[0][0]).split("?")[1]);
    expect(q.get("limit")).toBe("20");
    expect(q.get("offset")).toBe("0");
  });

  it("다음 페이지로 이동하면 offset 을 올려 다시 부른다", async () => {
    const user = userEvent.setup();
    // total 이 한 페이지를 넘어야 페이지 이동 버튼이 그려진다 — 그 상태를 만들어서 검사한다.
    getMock.mockResolvedValue({ ...listPayload(), total: 45 });
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    const next = screen.getByRole("button", { name: "다음" });
    expect(screen.getByRole("button", { name: "이전" })).toHaveProperty("disabled", true);
    await user.click(next);

    await waitFor(() =>
      expect(candidateCalls().some((c) => qOf(c).get("offset") === "20")).toBe(true),
    );
  });

  it("이전 페이지로 돌아가면 offset 이 되돌아온다", async () => {
    const user = userEvent.setup();
    getMock.mockResolvedValue({ ...listPayload(), total: 45 });
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    await user.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() =>
      expect(candidateCalls().some((c) => qOf(c).get("offset") === "20")).toBe(true),
    );
    const afterNext = candidateCalls().length;

    await user.click(screen.getByRole("button", { name: "이전" }));
    await waitFor(() => expect(candidateCalls().length).toBeGreaterThan(afterNext));
    expect(qOf(candidateCalls().at(-1) ?? []).get("offset")).toBe("0");
  });

  it("마지막 페이지에서는 다음으로 더 갈 수 없다", async () => {
    const user = userEvent.setup();
    getMock.mockResolvedValue({ ...listPayload(), total: 25 }); // 2페이지 분량
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    expect(screen.getByRole("button", { name: "다음" })).toHaveProperty("disabled", false);
    await user.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "다음" })).toHaveProperty("disabled", true),
    );
  });

  it("상태 탭을 바꾸면 그 status 로 다시 부르고 그 상태를 배지로 보여준다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    // 탭을 바꾸면 백엔드가 그 상태의 행을 준다 — 배지 문구도 함께 바뀌어야 한다.
    getMock.mockResolvedValue(
      listPayload([{ ...CANDIDATES[0], id: "ex-active-1", status: "active" }]),
    );
    await user.click(screen.getByRole("button", { name: "사용 중" }));
    await waitFor(() =>
      expect(candidateCalls().some((c) => qOf(c).get("status") === "active")).toBe(true),
    );
    const rows = await screen.findAllByRole("listitem");
    expect(within(rows[0]).getByText("사용 중")).toBeTruthy();
    // 이미 승인된 건에는 승인/거부 버튼을 그리지 않는다(재전이 금지 — 백엔드도 409 로 막는다).
    expect(within(rows[0]).queryByRole("button", { name: "승인" })).toBeNull();
  });

  it("권한이 없으면 관리자 권한이 필요하다고 알린다(빈 화면으로 침묵하지 않는다)", async () => {
    const { ApiClientError } = await import("@/lib/api-client");
    getMock.mockRejectedValue(new ApiClientError("forbidden", 403, null));
    render(<LearningApprovalPanel />);
    await waitFor(() =>
      expect(screen.getByText(/총괄관리자 권한이 필요합니다/)).toBeTruthy(),
    );
    expect(screen.getByText(/403/)).toBeTruthy();
  });

  it("서비스 필터를 입력하면 그 값으로 좁혀 다시 부른다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    const input = screen.getByLabelText("서비스 필터") as HTMLInputElement;
    await user.type(input, "avm");
    expect(input.value).toBe("avm"); // 제어 입력 — 입력값이 화면에 남아야 한다
    await waitFor(() =>
      expect(candidateCalls().some((c) => qOf(c).get("service") === "avm")).toBe(true),
    );
  });

  it("행마다 현재 상태를 한국어로 보여준다", async () => {
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(within(rows[0]).getByText("승인 대기")).toBeTruthy();
  });

  it("승인 결과를 화면에 알리고 목록을 다시 읽는다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    const before = candidateCalls().length;

    await user.click(within(rows[0]).getByRole("button", { name: "승인" }));

    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/승인했습니다/));
    // 승인 후 목록을 다시 읽어야 그 건이 '승인 대기'에서 빠진 것이 화면에 반영된다.
    expect(candidateCalls().length).toBeGreaterThan(before);
  });

  it("승인 요청은 목업을 타지 않는다(무목업 — 실 API 만)", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    await user.click(within(rows[0]).getByRole("button", { name: "승인" }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][1].useMock).toBe(false);
  });

  /* ---------------------------------------------------------------- */
  /*  in-flight 가드 — "요청이 몇 번 나가는가"를 정하는 코드도 배선이다  */
  /*  (2026-08-19 F3). `busy` Set 은 내가 R2 에서 직접 바꾼 배선인데     */
  /*  잠금이 0건이었다 — 지우면 POST 가 1회→3회가 되는데도 전부 초록.   */
  /* ---------------------------------------------------------------- */

  it("승인 버튼을 연타해도 요청은 한 번만 나간다", async () => {
    const user = userEvent.setup();
    const release = holdPromoteResponses();
    render(<LearningApprovalPanel />);
    const rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBeGreaterThan(0); // 전제

    const btn = within(rows[0]).getByRole("button", { name: "승인" });
    expect(btn).toHaveProperty("disabled", false); // 클릭 전 대조군

    await user.click(btn);
    // 응답을 붙잡아 뒀으므로 여전히 비행 중 — 이때 버튼이 잠겨 있어야 한다.
    expect(btn).toHaveProperty("disabled", true);
    expect(btn.textContent).toContain("처리 중");

    await user.click(btn);
    await user.click(btn);
    expect(postMock).toHaveBeenCalledTimes(1); // ★연타 3회 → 요청 1회

    release[0]();
    await waitFor(() => expect(btn).toHaveProperty("disabled", false));
  });

  it("한 행의 처리가 끝나도 아직 처리 중인 다른 행은 잠긴 채로 남는다", async () => {
    // ★이 케이스가 busyId(화면당 한 칸)와 busy Set(행 단위)을 **가른다**:
    //   단일 문자열이면 A 의 finally 가 가드를 통째로 풀어 **B 가 비행 중인데 열린다**.
    const user = userEvent.setup();
    getMock.mockResolvedValue(
      listPayload([
        { ...CANDIDATES[0], id: "ex-a", content_hash: "h-a" },
        { ...CANDIDATES[0], id: "ex-b", content_hash: "h-b" },
      ]),
    );
    const release = holdPromoteResponses();
    render(<LearningApprovalPanel />);
    let rows = await screen.findAllByRole("listitem");
    expect(rows.length).toBe(2); // 전제

    const a = within(rows[0]).getByRole("button", { name: "승인" });
    const b = within(rows[1]).getByRole("button", { name: "승인" });
    await user.click(a);
    await user.click(b);
    expect(postMock).toHaveBeenCalledTimes(2);
    expect(a).toHaveProperty("disabled", true);
    expect(b).toHaveProperty("disabled", true);

    release[0]!(); // A 만 끝난다
    rows = await screen.findAllByRole("listitem");
    await waitFor(() =>
      expect(within(rows[0]).getByRole("button", { name: "승인" })).toHaveProperty(
        "disabled",
        false,
      ),
    );

    // ★B 는 아직 비행 중이므로 잠긴 채여야 한다(행 단위 가드).
    const bAfter = within(rows[1]).getByRole("button", { name: /승인|처리 중/ });
    expect(bAfter).toHaveProperty("disabled", true);
    await user.click(bAfter);
    expect(postMock).toHaveBeenCalledTimes(2); // 중복 요청 없음
  });

  /* ---------------------------------------------------------------- */
  /*  부채 — 산문이 아니라 초록 안에 보이게 남긴다(CLAUDE.md C.13)      */
  /* ---------------------------------------------------------------- */

  it.todo(
    "학습권리 레지스트리가 learning_examples 키공간으로 시딩되면 주입 지점" +
      "(base_interpreter._load_fewshot)에도 게이트를 걸고 여기서 검사한다",
  );
  /* ---------------------------------------------------------------- */
  /*  다운로드 계약 — 부채 상환(2026-08-23)                            */
  /* ---------------------------------------------------------------- */

  it("★내려받기는 **파일명·MIME 계약**을 지킨다 — 확장자가 틀리면 학습 도구가 못 읽는다", async () => {
    // 이 파일은 사람이 받아서 **학습 파이프라인에 넣는** 산출물이다. 확장자(.jsonl)나
    // MIME(x-ndjson)이 바뀌면 받는 쪽이 조용히 실패한다 — 화면은 "내려받았습니다"라고 말한다.
    const user = userEvent.setup();
    let blobType: string | null = null;
    // ★jsdom 에는 `URL.createObjectURL` 이 **없다**(spyOn 이 "does not exist" 로 실패한다).
    //   이 파일의 기존 관례대로 `stubGlobal` 로 갈아끼운다.
    const createObjectURL = vi.fn((blob: Blob) => {
      blobType = blob.type;
      return "blob:stub";
    });
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });

    let downloadName: string | null = null;
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        downloadName = this.download;
      });

    getMock.mockImplementation((path: string) =>
      String(path).includes("/growth/learning/dataset")
        ? Promise.resolve({ message: '{"a":1}\n{"b":2}\n' })
        : Promise.resolve(listPayload()),
    );

    try {
      render(<LearningApprovalPanel />);
      await user.click(await screen.findByRole("button", { name: /승인된 학습셋 내려받기/ }));

      // ★전제 — 다운로드 경로가 실제로 발화했는지 먼저 본다(공허한 참 방지).
      await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
      expect(click, "앵커 클릭이 없다 — 다운로드가 시작되지 않았다").toHaveBeenCalledTimes(1);

      expect(downloadName, "파일명 계약이 깨졌다").toBe("learning_dataset_active.jsonl");
      expect(blobType, "MIME 계약이 깨졌다 — 받는 쪽이 조용히 실패한다").toBe(
        "application/x-ndjson",
      );
      // 누수 방지 — 만든 URL 은 반드시 회수한다.
      expect(revokeObjectURL, "objectURL 을 회수하지 않는다(메모리 누수)").toHaveBeenCalledWith(
        "blob:stub",
      );
    } finally {
      click.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it("★음성대조 — 승인된 사례가 없으면 **빈 파일임을 말한다**(받아 놓고 모르면 안 된다)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:stub"), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    getMock.mockImplementation((path: string) =>
      String(path).includes("/growth/learning/dataset")
        ? Promise.resolve({ message: "" })
        : Promise.resolve(listPayload()),
    );
    try {
      render(<LearningApprovalPanel />);
      await user.click(await screen.findByRole("button", { name: /승인된 학습셋 내려받기/ }));
      expect(await screen.findByText(/파일이 비어 있습니다/)).toBeInTheDocument();
    } finally {
      click.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it.todo(
    "후속(이 PR 밖): 프로덕션 learning_examples 의 기존 status='active' 행을 실측한다 — " +
      "있으면 권리 인수 이력을 소급 기록해야 한다(INSERT 는 'candidate' 하드코딩이고 " +
      "UPDATE 는 promote 하나뿐이라 0건일 것으로 보이나 미측정)",
  );
  it.todo(
    "후속(이 PR 밖): orphan_routes.py 의 is_consumed 가 주석·문자열에 뚫린다 — " +
      "이 화면은 doors 테스트로 자체 보완했으나 도구 자체가 전역 약점이다(별건)",
  );

  it("후보가 0건이면 목업 대신 정직하게 비어 있다고 적는다", async () => {
    getMock.mockResolvedValue(listPayload([]));
    render(<LearningApprovalPanel />);
    await waitFor(() => expect(screen.getByText(/승인을 기다리는 사례가 아직 없습니다/)).toBeTruthy());
    expect(screen.queryAllByRole("listitem").length).toBe(0);
  });
});
