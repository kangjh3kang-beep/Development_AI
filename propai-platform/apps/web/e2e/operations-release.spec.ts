import { expect, test } from "@playwright/test";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
} from "./support/release-harness";

test("maintenance, tenant, and digital twin routes stay executable", async ({
  page,
}) => {
  await installReleaseHarness(page);

  await page.goto("/en/maintenance");
  await expect(page.getByText("Predictive maintenance")).toBeVisible();
  await page.getByPlaceholder("Manual project UUID").fill(RELEASE_PROJECT_ID);
  await page.getByRole("button", { name: "Run maintenance analysis" }).click();
  await expect(
    page.getByText("Schedule HVAC inspection within 48 hours."),
  ).toBeVisible({ timeout: 15_000 });

  await page.goto("/en/tenant");
  await expect(page.getByText("Tenant experience")).toBeVisible();
  await page.getByPlaceholder("Manual project UUID").fill(RELEASE_PROJECT_ID);
  await page.getByRole("button", { name: "Analyze feedback" }).click();
  await expect(
    page.getByText(
      "A same-day maintenance follow-up has been scheduled for the tenant.",
    ),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Calculate health" }).click();
  await expect(page.getByText(/NPS: 41.2/i)).toBeVisible({ timeout: 15_000 });

  await page.goto("/en/digital-twin");
  await expect(
    page.getByText("Digital twin, risk, and permit readiness"),
  ).toBeVisible();
});

test("agent and approval operations share the same release queue context", async ({
  page,
}) => {
  await installReleaseHarness(page);

  await page.goto("/en/agent");
  await expect(
    page.getByText("Domain agent orchestration workspace"),
  ).toBeVisible();
  await expect(page.getByText("Execution history")).toBeVisible();

  await page
    .getByRole("navigation", { name: "Operations navigation" })
    .getByRole("link", { name: "Approval Ops" })
    .click();
  await expect(page).toHaveURL(/\/en\/approvals$/);
  await expect(
    page.getByRole("heading", { name: "Approval operations center" }).first(),
  ).toBeVisible();
  await page
    .getByLabel("Bulk decision note (optional)")
    .fill("Approved after approval center review.");
  await page.getByRole("button", { name: "Approve all pending" }).click();

  await expect(
    page.getByText("No approval items match the current filters."),
  ).toBeVisible();
  await expect(
    page.getByText(/Capital structure analysis completed with confidence 74%/i),
  ).toBeVisible();
});

test("kdx and feasibility release surfaces stay browser-executable", async ({
  page,
}) => {
  await installReleaseHarness(page);

  await page.goto("/en/dashboard/kdx");
  await expect(page.getByText("KDX Monitoring Center")).toBeVisible();
  await expect(page.getByRole("banner").getByText("connected")).toBeVisible();

  await page.goto("/en/feasibility");
  await expect(page.getByText("Feasibility and LCC")).toBeVisible();
  await page.getByRole("button", { name: "Run live feasibility" }).click();
  await expect(page.getByText(/₩1,450,000,000/)).toBeVisible();
  await expect(page.getByText("60m")).toBeVisible();
});
