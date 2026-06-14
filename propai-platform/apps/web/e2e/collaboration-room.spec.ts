import { expect, test } from "@playwright/test";
import { installReleaseHarness, RELEASE_PROJECT_ID } from "./support/release-harness";

/**
 * SP2-4 스모크: 프로젝트 회의방 탭 — 명부 로드 + 협력업체 초대 폼이 크래시 없이 동작.
 *
 * /api/v2/collaboration/* 를 목킹(members→[], invite→토큰). 워크스페이스 렌더 + 이메일 입력→
 * 초대 발급→토큰 노출 + pageerror 0 가드. tsc/build로 안 잡히는 라우트·store 회귀 보호.
 */
const INVITE = {
  id: "inv-1",
  project_id: RELEASE_PROJECT_ID,
  email: "vendor@traffic.co",
  project_role: "external_reviewer",
  scope_categories: ["traffic"],
  status: "pending",
  expires_at: "2026-06-28T00:00:00Z",
  invite_token: "TESTTOKEN_ABC123",
};

test.describe("프로젝트 회의방 스모크", () => {
  test("회의방 진입 → 협력업체 초대 발급 → 토큰 노출 무크래시", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(String(e?.message ?? e)));

    await installReleaseHarness(page);
    await page.route("**/api/v2/collaboration/**", (route) => {
      const req = route.request();
      if (req.method() === "POST" && req.url().includes("/invites")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(INVITE),
        });
      }
      // GET members → 빈 명부
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    });

    await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/collaboration`);

    const ws = page.getByTestId("collab-workspace");
    await ws.waitFor({ state: "visible", timeout: 45_000 });
    await expect(page.getByTestId("collab-invite-email")).toBeVisible();

    // 유효 이메일 입력 → 발급 버튼 활성 → 발급 → 토큰 노출
    await page.getByTestId("collab-invite-email").fill("vendor@traffic.co");
    const submit = page.getByTestId("collab-invite-submit");
    await expect(submit).toBeEnabled();
    await submit.click();

    const token = page.getByTestId("collab-invite-token");
    await expect(token).toBeVisible({ timeout: 15_000 });
    await expect(token).toContainText("TESTTOKEN_ABC123");

    expect(pageErrors, `uncaught page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  });
});
