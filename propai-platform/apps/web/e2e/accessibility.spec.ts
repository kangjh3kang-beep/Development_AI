import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";

const routes = [
  { name: "login", path: "/en/login", withSession: false },
  { name: "dashboard", path: "/en", withSession: true },
  { name: "approval ops", path: "/en/approvals", withSession: true },
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
    await page.goto(route.path);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const criticalViolations = results.violations.filter(
      (violation) => violation.impact === "critical",
    );

    expect(criticalViolations).toHaveLength(0);
  });
}

test("keyboard navigation reaches the live login controls in order", async ({
  page,
}) => {
  await installReleaseHarness(page, { withSession: false });
  await page.goto("/en/login");

  const loginModeButton = page.getByRole("button", { name: /^Login$/ });
  const registerModeButton = page.getByRole("button", { name: /^Register admin$/ });
  const emailInput = page.getByLabel("Email");

  await loginModeButton.focus();
  await expect(loginModeButton).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(registerModeButton).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(emailInput).toBeFocused();
});
