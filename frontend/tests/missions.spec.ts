import { test, expect } from "@playwright/test";
test("build, template, queue, explicit execution, history and CSV on Missions", async ({
  page,
}, testInfo) => {
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByRole("button", { name: "Missions", exact: true }).click();
  await page.getByLabel("Mission name").fill("Station wait");
  await page.getByLabel("Mission step type").selectOption("wait");
  await page.getByLabel("WAIT duration").fill("1");
  await page.getByRole("button", { name: "Add step", exact: true }).click();
  await page
    .getByRole("button", { name: "Save mission template", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Queue template", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("No active mission.", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Queue template", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Start next mission", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Start next mission", exact: true })
    .click();
  await expect(page.locator(".missions-page table tbody")).toContainText(
    "completed",
    { timeout: 8000 },
  );
  await page.getByLabel("Mission history result").selectOption("completed");
  await page.getByLabel("Search mission history").fill("Station wait");
  await expect(page.locator(".missions-page table tbody")).toContainText(
    "Station wait",
  );
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page
      .getByRole("button", { name: "Export mission history CSV", exact: true })
      .click(),
  ]);
  expect(download.suggestedFilename()).toBe("pbl4-missions.csv");
  await page.screenshot({
    path: testInfo.outputPath("missions.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "Queue template", exact: true })
    .click();
  await page.getByRole("button", { name: "Clear queue", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Confirm clear queue", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Keep queue", exact: true }).click();
  await page.getByRole("button", { name: "Clear queue", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm clear queue", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Start next mission", exact: true }),
  ).toBeDisabled();
});
