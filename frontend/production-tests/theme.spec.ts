import { test, expect } from "@playwright/test";

test("production bootstrap resolves preference before React executes", async ({
  browser,
}) => {
  for (const theme of ["light", "dark"] as const) {
    const context = await browser.newContext({
      colorScheme: theme === "light" ? "dark" : "light",
    });
    const page = await context.newPage();
    await page.addInitScript(
      (value) => localStorage.setItem("pbl4-theme", value),
      theme,
    );
    await page.route("**/assets/*.js", (route) => route.abort());
    await page.goto("/navigation", { waitUntil: "domcontentloaded" });
    await expect(page.locator("#root")).toBeEmpty();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    expect(
      await page
        .locator("html")
        .evaluate((el) => getComputedStyle(el).colorScheme),
    ).toBe(theme);
    expect(
      await page
        .locator("html")
        .evaluate((el) => getComputedStyle(el).backgroundColor),
    ).toBe(theme === "light" ? "rgb(243, 246, 250)" : "rgb(8, 15, 28)");
    await context.close();
  }
});

for (const theme of ["light", "dark"] as const) {
  test(`${theme}: production page refresh, themed maps/charts and visual evidence`, async ({
    page,
  }, testInfo) => {
    test.setTimeout(120000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/overview");
    await expect(page.getByText("Stream connected")).toBeVisible();
    await page
      .getByRole("radio", {
        name: `${theme === "light" ? "Light" : "Dark"} theme`,
      })
      .check();
    for (const name of [
      "Overview",
      "Manual Control",
      "Navigation",
      "Missions",
      "Sensors",
      "Diagnostics",
      "Settings",
    ]) {
      await page.getByRole("button", { name, exact: true }).click();
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        name === "Overview" ? "Mission overview" : name,
      );
      await expect(
        page.getByText("Loading view…", { exact: true }),
      ).toHaveCount(0);
      await page.mouse.move(0, 0);
      if (name === "Missions")
        await expect(page.locator(".missions-page")).toBeVisible();
      if (name === "Diagnostics")
        await expect(
          page.getByRole("tab", { name: "Motors", exact: true }),
        ).toBeVisible();
      if (name === "Sensors")
        await expect(
          page.getByTestId("lidar-returns").locator("circle").first(),
        ).toBeVisible();
      if (name === "Navigation") {
        await expect(page.getByTestId("navigation-map")).toBeVisible();
        await page.getByLabel("X position (m)").fill("2");
        await page.getByLabel("Y position (m)").fill("1");
        await page.getByLabel("Target heading", { exact: true }).fill("30");
        await page
          .getByRole("button", { name: "Save waypoint A", exact: true })
          .click();
        await page.getByLabel("Y position (m)").fill("2");
        await page
          .getByRole("button", { name: "Plan path", exact: true })
          .click();
        await expect(page.getByTestId("planned-path")).toBeVisible();
        await page.getByLabel("Show simulated LiDAR", { exact: true }).check();
      }
      if (name === "Overview") {
        await expect(page.locator(".recharts-surface").first()).toBeVisible();
        await page
          .locator(".chart")
          .first()
          .hover({ position: { x: 150, y: 80 } });
        await expect(
          page.locator(".recharts-tooltip-wrapper").first(),
        ).toBeVisible();
        const tooltip = await page
          .locator(".recharts-tooltip-wrapper")
          .first()
          .boundingBox();
        const panel = await page.locator(".chart-panel").first().boundingBox();
        expect(tooltip!.y + tooltip!.height).toBeLessThanOrEqual(
          panel!.y + panel!.height,
        );
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({
          path: testInfo.outputPath(`${theme}-chart-tooltip.png`),
          fullPage: true,
        });
        await page.mouse.move(0, 0);
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({
        path: testInfo.outputPath(
          `${theme}-${name.toLowerCase().replaceAll(" ", "-")}.png`,
        ),
        fullPage: true,
      });
      if (name === "Navigation")
        await page
          .getByRole("button", {
            name: "STOP · CANCEL ALL MOTION",
            exact: true,
          })
          .click();
      if (name === "Missions") {
        // Only the temporary production-test database is used for visual fixtures.
        await page.getByLabel("Mission name").fill(`${theme} theme inspection`);
        await page.getByLabel("Mission step type").selectOption("wait");
        await page.getByLabel("WAIT duration").fill("1");
        await page
          .getByRole("button", { name: "Add step", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Save mission template", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Queue template", exact: true })
          .last()
          .click();
        await page
          .getByRole("button", { name: "Clear queue", exact: true })
          .click();
        await expect(
          page.getByRole("button", {
            name: "Confirm clear queue",
            exact: true,
          }),
        ).toBeVisible();
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({
          path: testInfo.outputPath(`${theme}-mission-confirmation.png`),
          fullPage: true,
        });
        await page
          .getByRole("button", { name: "Confirm clear queue", exact: true })
          .click();
      }
      if (name === "Diagnostics") {
        for (const tab of ["System Health", "Communication", "Events"]) {
          await page.getByRole("tab", { name: tab, exact: true }).click();
          await page.evaluate(() => window.scrollTo(0, 0));
          await page.screenshot({
            path: testInfo.outputPath(
              `${theme}-diagnostics-${tab.toLowerCase().replaceAll(" ", "-")}.png`,
            ),
            fullPage: true,
          });
        }
      }
    }
    for (const path of ["/navigation", "/missions"]) {
      await page.goto(path);
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      await expect(page.getByText("Stream connected")).toBeVisible();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("button", { name: "Navigation", exact: true }).click();
    await expect(page.getByTestId("navigation-map")).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: testInfo.outputPath(`${theme}-mobile-navigation.png`),
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });
}
