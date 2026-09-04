/**
 * `/settings/learning` 페이지 — **문이 실제로 열리는지**(2026-08-19).
 *
 * ★페이지 파일이 존재한다는 것만으로는 부족하다. 껍데기만 남고 승인 패널이 빠지면
 *   "문은 있는데 방이 비어 있는" 상태가 되고, 그건 이 캠페인이 고치는 결함
 *   ("사람 승인 게이트인데 사람에게 문이 없다")과 실질적으로 같다.
 *   그래서 여기서는 페이지를 **렌더해서** 패널이 실제로 붙어 후보 목록을 부르는지 본다.
 *   (`__tests__` 는 밑줄로 시작해 Next 라우팅에서 제외되는 비공개 폴더다.)
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: { get: (...a: unknown[]) => getMock(...a), post: vi.fn() },
  ApiClientError: class ApiClientError extends Error {
    status = 0;
  },
}));

import LearningApprovalAdminPage from "../page";

beforeEach(() => {
  getMock.mockReset();
  getMock.mockResolvedValue({
    items: [],
    total: 0,
    statuses: ["candidate"],
    service: null,
    tenant_id: null,
    limit: 20,
    offset: 0,
  });
});

describe("/settings/learning 페이지", () => {
  it("승인 패널을 실제로 붙여 후보 목록을 부른다", async () => {
    render(<LearningApprovalAdminPage />);

    expect(screen.getByRole("heading", { name: "AI 학습 사례 승인" })).toBeTruthy();
    // ★패널이 빠지면 이 호출이 사라진다 — 껍데기만 남은 화면을 잡는다.
    await waitFor(() =>
      expect(
        // ★경로는 정확히 본다 — 부분문자열이면 `/candidatesX` 접미 오타가 통과한다(404).
        getMock.mock.calls.some(
          (c) => String(c[0]).split("?")[0] === "/growth/learning/candidates",
        ),
      ).toBe(true),
    );
  });

  it("자동 승인이 아님을 화면에서 밝힌다", async () => {
    render(<LearningApprovalAdminPage />);
    // 목록 로딩이 끝난 뒤 단언한다(로딩 중 상태 갱신이 act 밖에서 일어나는 것 방지).
    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(screen.getByText(/자동 승인은 하지 않습니다/)).toBeTruthy();
  });
});
