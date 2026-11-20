import { expect, test, type WebSocketRoute } from "@playwright/test";

test("telemetry, hold-to-drive, release, focus loss and page changes", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Mission overview" }),
  ).toBeVisible();
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  const forward = page.getByRole("button", { name: "Forward", exact: true });
  await forward.hover();
  await page.mouse.down();
  await expect(page.getByTestId("operating-mode")).toHaveText("MANUAL");
  await page.mouse.up();
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  await forward.focus();
  await page.keyboard.down("Space");
  await expect(page.getByTestId("operating-mode")).toHaveText("MANUAL");
  await page.keyboard.up("Space");
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  await page.keyboard.down("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("MANUAL");
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  await page.keyboard.up("Enter");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByText("0.0435 m", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  await expect(page.getByTestId("navigation-map")).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile layout has no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeAttached();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeEnabled();
});

test("disconnected service clears controls and marks telemetry stale", async ({
  page,
}) => {
  let stream: WebSocketRoute | undefined;
  let unavailable = false;
  await page.routeWebSocket("**/ws/telemetry", (ws) => {
    if (unavailable) {
      ws.close();
      return;
    }
    ws.connectToServer();
    stream = ws;
  });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  unavailable = true;
  await stream!.close({ code: 1001, reason: "Test telemetry outage" });
  await expect(page.getByText("Disconnected", { exact: true })).toBeAttached({
    timeout: 10000,
  });
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText(/Last telemetry is stale and hidden/),
  ).toBeVisible();
  unavailable = false;
  await expect(page.getByText("Stream connected")).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
});

test("navigation map, heading, waypoints, arbitration and synchronized pose", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  const map = page.getByTestId("navigation-map");
  await expect(map).toBeVisible();
  // Use the SVG screen transform, independent of viewport size/zoom.
  const point = await map.evaluate((node) => {
    const matrix = (node as SVGSVGElement).getScreenCTM()!;
    const p = new DOMPoint(2, -1).matrixTransform(matrix);
    return { x: p.x, y: p.y };
  });
  await page.mouse.click(point.x, point.y);
  await expect(page.getByLabel("X position (m)")).toHaveValue("2");
  await page.getByLabel("Target heading", { exact: true }).fill("90");
  await page
    .getByRole("button", { name: "Save waypoint A", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Add A to sequence", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Add A to sequence", exact: true })
    .click();
  await page.getByRole("button", { name: "Plan path", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("ready");
  await expect(page.getByTestId("planned-path")).not.toHaveAttribute(
    "points",
    "",
  );
  await page.screenshot({
    path: testInfo.outputPath("navigation-desktop.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Start navigation", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await expect
    .poll(async () =>
      page.getByTestId("virtual-robot").getAttribute("transform"),
    )
    .not.toContain("translate(1 -1)");
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("paused");
  const stoppedPose = await page.getByTestId("robot-position").textContent();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByTestId("robot-position")).toHaveText(stoppedPose!);
  await expect(page.getByTestId("operating-mode")).toHaveText("AUTONOMOUS");
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("paused");
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await page
    .getByRole("button", { name: "STOP · CANCEL ALL MOTION", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("idle");
  await page.getByRole("button", { name: "Return home", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await page
    .getByRole("button", { name: "Cancel mission", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("idle");
  expect(errors).toEqual([]);
});

test("navigation mobile map tools and invalid destinations", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeAttached();
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  await expect(page.getByTestId("navigation-map")).toBeVisible();
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await page.getByRole("button", { name: "Zoom out", exact: true }).click();
  await page
    .getByRole("button", { name: "Reset map view", exact: true })
    .click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("navigation-mobile.png"),
    fullPage: true,
  });
  await page.getByLabel("X position (m)").fill("3.4");
  await page.getByLabel("Y position (m)").fill("2");
  await page
    .getByRole("button", { name: "Start navigation", exact: true })
    .click();
  await expect(
    page.getByText(/Destination .*footprint clearance/),
  ).toBeVisible();
  await expect(page.getByTestId("navigation-status")).not.toHaveText("running");
});
