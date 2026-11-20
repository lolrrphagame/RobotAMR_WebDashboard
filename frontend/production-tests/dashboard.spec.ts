import { test, expect } from "@playwright/test";
test("built dashboard same-origin WS, page refresh and safe controls", async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const sockets: string[] = [];
  page.on("websocket", (ws) => sockets.push(ws.url()));
  await page.goto("/navigation");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(page.getByTestId("navigation-map")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("navigation-map")).toBeVisible();
  await page.getByRole("button", { name: "Missions", exact: true }).click();
  await expect(page).toHaveURL(/\/missions$/);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Mission builder", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  const forward = page.getByRole("button", { name: "Forward", exact: true });
  await expect(forward).toBeEnabled();
  await forward.hover();
  await page.mouse.down();
  await expect(page.getByTestId("operating-mode")).toHaveText("MANUAL");
  await page.mouse.up();
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  await forward.focus();
  await page.keyboard.down("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("MANUAL");
  await page
    .getByRole("button", { name: "Stop simulated robot", exact: true })
    .click();
  await page.keyboard.up("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  expect(
    sockets.some((url) => url === "ws://127.0.0.1:18173/ws/telemetry"),
  ).toBe(true);
  const html = await (await request.get("/")).text();
  expect(html).not.toContain("/@vite");
  expect(html).not.toContain("/src/");
  expect((await request.get("/docs")).status()).toBe(404);
  expect(errors).toEqual([]);
});

test("production navigation disconnect pauses instead of auto-resuming", async ({
  page,
  request,
}) => {
  const context = await page.context().browser()!.newContext();
  const tab = await context.newPage();
  await tab.goto("http://127.0.0.1:18173/navigation");
  await expect(tab.getByText("Stream connected")).toBeVisible();
  await tab.getByLabel("X position (m)").fill("2");
  await tab.getByLabel("Y position (m)").fill("2");
  await tab
    .getByRole("button", { name: "Start navigation", exact: true })
    .click();
  await expect(tab.getByTestId("navigation-status")).toHaveText("running");
  await context.close();
  await expect
    .poll(
      async () =>
        (await (await request.get("/api/robot/status")).json()).navigation
          .status,
    )
    .toBe("paused");
  await page.goto("/navigation");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(page.getByTestId("navigation-status")).toHaveText("paused");
  await page
    .getByRole("button", { name: "STOP · CANCEL ALL MOTION", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("idle");
});

test("refreshing Missions pauses the same execution without duplicating it", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/missions", {
    data: { name: "Refresh safety", steps: [{ kind: "wait", seconds: 60 }] },
  });
  expect(created.status()).toBe(200);
  await page.goto("/missions");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page
    .getByRole("button", { name: "Start next mission", exact: true })
    .click();
  await expect(page.getByTestId("operation-status")).toContainText("RUNNING");
  const before = await (await request.get("/api/missions")).json();
  await page.reload();
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(page.getByTestId("operation-status")).toContainText("PAUSED", {
    timeout: 8000,
  });
  const after = await (await request.get("/api/missions")).json();
  expect(after.active.id).toBe(before.active.id);
  expect(after.queue).toHaveLength(0);
  await page
    .getByRole("button", { name: "Cancel active mission", exact: true })
    .click();
  await expect(page.getByTestId("operation-status")).toHaveCount(0);
  const history = await (await request.get("/api/missions/history")).json();
  expect(
    history.records.filter((r: { id: string }) => r.id === before.active.id),
  ).toHaveLength(1);
});
