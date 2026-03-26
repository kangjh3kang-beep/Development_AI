import { expect, test } from "@playwright/test";
import {
  installReleaseHarness,
  RELEASE_PROJECT_ID,
  RELEASE_PROJECT_NAME,
} from "./support/release-harness";

test("project release chain covers finance, report, design, and BIM", async ({
  page,
}) => {
  await installReleaseHarness(page);

  await page.goto("/en/projects");
  await expect(page.getByText(RELEASE_PROJECT_NAME)).toBeVisible();
  await expect(page.getByRole("link", { name: "Open project" })).toHaveAttribute(
    "href",
    `/en/projects/${RELEASE_PROJECT_ID}`,
  );

  await page.goto(`/en/projects/${RELEASE_PROJECT_ID}`);
  await expect(page).toHaveURL(new RegExp(`/en/projects/${RELEASE_PROJECT_ID}$`));

  await expect(page.getByRole("link", { name: "Finance" })).toHaveAttribute(
    "href",
    `/en/projects/${RELEASE_PROJECT_ID}/finance`,
  );
  await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/finance`);
  await expect(page).toHaveURL(
    new RegExp(`/en/projects/${RELEASE_PROJECT_ID}/finance$`),
  );
  await page.getByPlaceholder("Address").fill("Seoul Mapo-gu 100");
  await page.getByPlaceholder("Area (sqm)").fill("9800");
  await page.getByRole("button", { name: "Run finance analysis" }).click();
  await expect(page.getByText("MEDIUM")).toBeVisible();
  await expect(
    page.getByText("The jeonse ratio remains below the highest-risk band."),
  ).toBeVisible();

  await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/report`);
  await page.getByPlaceholder("Report project name").fill(RELEASE_PROJECT_NAME);
  await page.getByRole("button", { name: "Generate investor report" }).click();
  await expect(
    page.getByText("Prime Seoul office exposure with strong leasing momentum."),
  ).toBeVisible({ timeout: 15_000 });

  await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/design`);
  await page.getByPlaceholder(/^Area \(sqm\)$/).fill("9800");
  await page.getByRole("button", { name: "Generate floor plan" }).click();
  await expect(page.getByText("sdxl")).toBeVisible({ timeout: 15_000 });
  await page.getByPlaceholder(/^Total area \(sqm\)$/).fill("9800");
  await page.getByRole("button", { name: "Generate IFC and carbon" }).click();
  await expect(page.getByText("IFC4")).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByText("Reduce concrete intensity in the wall package."),
  ).toBeVisible({ timeout: 15_000 });

  await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/bim`);
  await page.getByPlaceholder(/^Total area \(sqm\)$/).fill("9800");
  await page.getByRole("button", { name: "Generate BIM quantities" }).click();
  await expect(page.getByText("threejs_buffergeometry")).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText("IfcWall: 2")).toBeVisible({ timeout: 15_000 });
});

test("permit to contract to e-sign cutover chain stays intact", async ({
  page,
}) => {
  await installReleaseHarness(page);

  await page.goto("/en/digital-twin");
  await expect(page.getByRole("heading", { name: "Digital twin, risk, and permit readiness" })).toBeVisible();
  await page.getByPlaceholder("Manual project UUID").fill(RELEASE_PROJECT_ID);
  await expect(page.getByText(`Current target: ${RELEASE_PROJECT_NAME}`)).toBeVisible();

  await page.getByRole("button", { name: "Save status snapshot" }).click();
  await expect(page.getByText("watch")).toBeVisible();

  await page.getByRole("button", { name: "Analyze unified risk" }).click();
  await expect(
    page.getByText("Unified risk grade C with manageable downside."),
  ).toBeVisible();

  await page.getByRole("button", { name: "Submit permit package" }).click();
  await expect(page.getByText(/SEUMTER-20260326-REL01-ABC123/)).toBeVisible();

  await page.goto(`/en/projects/${RELEASE_PROJECT_ID}/contracts`);
  await expect(
    page.getByRole("heading", { name: RELEASE_PROJECT_NAME, exact: true }),
  ).toBeVisible();
  await page.getByLabel("Signer name").fill("Release Signer");
  await page.getByLabel("Signer email").fill("signer@propai.dev");
  await page.getByRole("button", { name: "Send e-sign request" }).click();

  await expect(page.getByText(/Sign status: requested/)).toBeVisible();
});
