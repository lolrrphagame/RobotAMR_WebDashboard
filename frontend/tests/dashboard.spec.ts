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
  await expect(page.getByText("FUTURE PHASE", { exact: true })).toBeVisible();
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
