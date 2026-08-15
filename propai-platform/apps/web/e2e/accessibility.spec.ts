import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";
import { gotoLive } from "./support/goto-live";

const routes = [
  { name: "login", path: "/en/login", withSession: false },
  { name: "dashboard", path: "/en", withSession: true },
  // ★`/en/approvals` 를 뺐다 — `d8f9c3da`(고아 라우트 정리)에서 **삭제된 라우트**다.
  //   404 페이지는 본문이 33자뿐이라 접근성 위반이 있을 수 없어, 이 감사는 대상이 사라진 뒤에도
  //   **조용히 초록**이었다(실측). 아래 `gotoLive` 가 앞으로 같은 일을 막는다.
  {
    name: "project contracts",
    path: `/en/projects/${RELEASE_PROJECT_ID}/contracts`,
    withSession: true,
  },
  { name: "offline fallback", path: "/offline", withSession: true },
];

for (const route of routes) {
  test(`critical accessibility audit stays clean for ${route.name}`, async ({
    page,
  }) => {
    await installReleaseHarness(page, { withSession: route.withSession });
    // ★404 면 여기서 실패한다 — 감사 대상이 실재하는지를 먼저 강제한다(공허한 초록 차단).
    await gotoLive(page, route.path);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const criticalViolations = results.violations.filter(
      (violation) => violation.impact === "critical",
    );

    expect(criticalViolations).toHaveLength(0);
  });
}

/**
 * ★2026-08-13 재작성 — 이 검사는 **없는 UI** 를 기다리고 있었다.
 *
 *   종전: `Login` / `Register admin` **모드 버튼**을 탭으로 훑었다.
 *   현재: 모드 전환이 **버튼이 아니라 라우트**(`/login` ↔ `/register`)로 바뀌어 그 버튼이
 *         렌더되지 않는다. 그래서 `locator.focus` 가 60초 타임아웃으로 죽고 있었다.
 *
 *   ★함정: 그 문자열은 `AuthWorkspaceClient` 의 copy 사전에 **남아만 있었다**
 *     (`modeLabels.login/register`, 소비처 0). grep 으로는 "있다"고 나와 드리프트가 가려졌다 —
 *     **문자열이 존재한다 ≠ 렌더된다.** 같은 커밋에서 그 죽은 copy 를 걷어낸다.
 *
 *   아래 순서는 **실측**이다(2026-08-13 `/en/login`):
 *     Skip to content → email → password → Run login → 비밀번호 찾기 → 소셜 3 → 신규 테넌트 링크
 */
test("keyboard navigation reaches the live login controls in order", async ({
  page,
}) => {
  await installReleaseHarness(page, { withSession: false });
  await page.goto("/en/login");

  const emailInput = page.getByLabel("Email");
  await expect(emailInput, "로그인 폼이 렌더되지 않았다 — 아래 탭 순서 검사가 공허해진다").toBeVisible();

  // 문서 첫 탭은 스킵 링크다(접근성 계약). 그다음이 로그인 컨트롤 체인.
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /skip to content/i })).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(emailInput).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Password")).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Run login" })).toBeFocused();

  // ★모드 전환은 이제 링크다 — 키보드로 **도달 가능**해야 한다(종전 버튼 계약의 대체물).
  //   몇 번째인지까지 고정하면 소셜 버튼이 하나 늘 때마다 깨진다 — 도달성만 잠근다.
  const registerLink = page.getByRole("link", { name: /create a new tenant/i });
  await expect(registerLink, "관리자 등록으로 가는 링크가 없다 — 모드 전환 경로가 사라졌다").toBeVisible();
  let reached = false;
  for (let i = 0; i < 8 && !reached; i += 1) {
    await page.keyboard.press("Tab");
    reached = await registerLink.evaluate((el) => el === document.activeElement);
  }
  expect(reached, "8번 탭 안에 등록 링크에 닿지 못했다 — 키보드로 모드 전환이 불가능하다").toBe(true);
});
