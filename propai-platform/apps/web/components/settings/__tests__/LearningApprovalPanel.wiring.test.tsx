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
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
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

/** GET 호출 중 후보목록 경로만 추린다. */
function candidateCalls() {
  return getMock.mock.calls.filter((c) => String(c[0]).includes("/growth/learning/candidates"));
}

describe("AI 학습 사례 승인 화면 배선", () => {
  it("후보 목록 API 를 실제로 부른다(status=candidate 기본)", async () => {
    render(<LearningApprovalPanel />);
    await waitFor(() => expect(candidateCalls().length).toBeGreaterThan(0));
    const url = String(candidateCalls()[0][0]);
    expect(url).toContain("/growth/learning/candidates");
    expect(url).toContain("status=candidate");
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
    expect(postMock.mock.calls[0][1].body).toEqual({ example_id: "ex-cand-1", status: "active" });

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
    expect(postMock.mock.calls[0][1].body).toEqual({ example_id: "ex-cand-2", status: "rejected" });
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
        getMock.mock.calls.some((c) => String(c[0]).includes("/growth/learning/dataset")),
      ).toBe(true),
    );
    expect(createObjectURL).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("페이지 크기·시작 위치를 요청에 실어 보낸다", async () => {
    render(<LearningApprovalPanel />);
    await waitFor(() => expect(candidateCalls().length).toBeGreaterThan(0));
    const url = String(candidateCalls()[0][0]);
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=0");
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
      expect(candidateCalls().some((c) => String(c[0]).includes("offset=20"))).toBe(true),
    );
  });

  it("상태 탭을 바꾸면 그 status 로 다시 부른다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    await user.click(screen.getByRole("button", { name: "사용 중" }));
    await waitFor(() =>
      expect(candidateCalls().some((c) => String(c[0]).includes("status=active"))).toBe(true),
    );
  });

  it("서비스 필터를 입력하면 그 값으로 좁혀 다시 부른다", async () => {
    const user = userEvent.setup();
    render(<LearningApprovalPanel />);
    await screen.findAllByRole("listitem");

    await user.type(screen.getByLabelText("서비스 필터"), "avm");
    await waitFor(() =>
      expect(candidateCalls().some((c) => String(c[0]).includes("service=avm"))).toBe(true),
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

  it("후보가 0건이면 목업 대신 정직하게 비어 있다고 적는다", async () => {
    getMock.mockResolvedValue(listPayload([]));
    render(<LearningApprovalPanel />);
    await waitFor(() => expect(screen.getByText(/승인을 기다리는 사례가 아직 없습니다/)).toBeTruthy());
    expect(screen.queryAllByRole("listitem").length).toBe(0);
  });
});
