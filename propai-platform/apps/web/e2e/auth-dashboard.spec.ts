import { expect, test } from "@playwright/test";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";

test("auth to dashboard release cutover chain stays live-first", async ({
  page,
}) => {
  await installReleaseHarness(page, { withSession: false });

  await page.goto("/en/login");
  await page.getByLabel("Email").fill("ops@propai.dev");
  await page.getByLabel("Password").fill("super-secret-password");
  await page.getByRole("button", { name: "Run login" }).click();

  await expect(
    page.getByText("Login succeeded and the browser session has been stored."),
  ).toBeVisible();
  await expect(page.getByText("Release Operator")).toBeVisible();

  await page.getByRole("button", { name: "Open dashboard" }).click();

  await expect(page).toHaveURL(/\/en$/);
  await expect(page.getByText("Connections")).toBeVisible();
  await expect(page.getByText("PropAI API 30.0.0 (production)")).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Operations navigation" })
      .getByRole("link", { name: "Approval Ops" }),
  ).toHaveAttribute("href", "/en/approvals");
  await expect(page.getByRole("link", { name: "Open project" })).toHaveAttribute(
    "href",
    `/en/projects/${RELEASE_PROJECT_ID}`,
  );
});
