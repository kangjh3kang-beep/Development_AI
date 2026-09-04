import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PrivacyClient } from "@/components/mypage/PrivacyClient";
import { apiClient } from "@/lib/api-client";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ko/mypage/privacy",
}));

vi.mock("@/lib/api-client", () => ({
  ApiClientError: class ApiClientError extends Error {},
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

const CONSENTS = {
  current_policy_version: "2026-06-15",
  marketing_opt_in: true,
  consents: [
    { consent_type: "terms_of_service", agreed: true, policy_version: "2026-06-15", agreed_at: "2026-07-17T00:00:00Z" },
    { consent_type: "marketing", agreed: true, policy_version: "2026-06-15", agreed_at: "2026-07-17T00:00:00Z" },
  ],
};

describe("PrivacyClient", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("마케팅 수신동의를 철회(토글)하고 API로 변경을 보낸다(정보통신망법 §50④)", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(CONSENTS);
    vi.mocked(apiClient.post).mockResolvedValue({ message: "마케팅 정보 수신을 철회했습니다." });

    render(<PrivacyClient locale="ko" />);
    const toggle = await screen.findByRole("switch", { name: "마케팅 정보 수신 동의" });
    expect(toggle).toHaveAttribute("aria-checked", "true");

    await userEvent.click(toggle);
    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/me/consents/marketing",
        expect.objectContaining({ body: { agreed: false }, useMock: false }),
      );
    });
    expect(await screen.findByText("마케팅 정보 수신을 철회했습니다.")).toBeInTheDocument();
  });

  it("조회 실패를 '동의 이력 없음'이 아닌 오류로 표시한다", async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error("boom"));
    render(<PrivacyClient locale="ko" />);
    expect(await screen.findByText(/동의 이력을 불러오지 못했습니다/)).toBeInTheDocument();
    expect(screen.queryByText("동의 이력이 없습니다.")).toBeNull();
    // 오류 시 마케팅 토글도 표시하지 않는다(상태 미상).
    expect(screen.queryByRole("switch")).toBeNull();
  });
});
