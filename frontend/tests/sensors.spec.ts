import { expect, test, type WebSocketRoute } from "@playwright/test";

test("Sensor Center renders simulated scans, a clear camera placeholder and optional map overlay", async ({
  page,
  request,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByRole("button", { name: "Sensors", exact: true }).click();
  await expect(page.getByTestId("lidar-status")).toHaveText("READY");
  await expect(
    page.getByRole("heading", { name: "2D LiDAR Visualization" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Front Camera Monitor" }),
  ).toBeVisible();
  await expect(page.getByTestId("camera-preview")).toContainText(
    "NOT CONNECTED",
  );
  await expect(page.getByTestId("camera-preview")).toContainText(
    "STATIC TEST PATTERN",
  );
  await expect(page.locator(".camera-preview img")).toHaveCount(0);
  const camera = await (await request.get("/api/sensors/camera")).json();
  expect(camera.timestamp).toBeNull();
  expect(camera.metadata.fps).toBeNull();
  const lidar = await (await request.get("/api/sensors/lidar")).json();
  await expect(page.getByTestId("lidar-min-distance")).toHaveText(
    `${lidar.metadata.min_obstacle_distance.toFixed(2)} m`,
  );
  await expect(
    page.getByTestId("lidar-returns").locator("circle"),
  ).not.toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("sensor-center-desktop.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  await expect(page.getByTestId("navigation-map")).toBeVisible();
  await expect(page.getByTestId("navigation-lidar-overlay")).toHaveCount(0);
  await page.getByLabel("Show simulated LiDAR", { exact: true }).check();
  await expect(page.getByTestId("navigation-lidar-overlay")).toBeAttached();
  const pose = await page.getByTestId("robot-position").textContent();
  await page.getByLabel("Show simulated LiDAR", { exact: true }).uncheck();
  await expect(page.getByTestId("navigation-lidar-overlay")).toHaveCount(0);
  await expect(page.getByTestId("robot-position")).toHaveText(pose!);
  expect(errors).toEqual([]);
});

test("quiet scan stream becomes stale and hides points while control telemetry stays online", async ({
  page,
}) => {
  let freeze = false;
  await page.routeWebSocket("**/ws/sensors", (ws) => {
    const server = ws.connectToServer();
    server.onMessage((message) => {
      if (!freeze) ws.send(message);
    });
  });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByRole("button", { name: "Sensors", exact: true }).click();
  await expect(page.getByTestId("lidar-status")).toHaveText("READY");
  freeze = true;
  await expect(page.getByTestId("lidar-status")).toHaveText("STALE", {
    timeout: 5000,
  });
  await expect(page.getByTestId("lidar-returns")).toHaveCount(0);
  await expect(
    page.getByText("Stale · points hidden", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Stream connected")).toBeVisible();
  freeze = false;
  await expect(page.getByTestId("lidar-status")).toHaveText("READY");
});

test("sensor disconnect does not pause an autonomous mission and stream reconnects", async ({
  page,
  request,
}) => {
  let stream: WebSocketRoute | undefined;
  let unavailable = false;
  await page.routeWebSocket("**/ws/sensors", (ws) => {
    if (unavailable) {
      ws.close();
      return;
    }
    ws.connectToServer();
    stream = ws;
  });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  await page.getByLabel("X position (m)").fill("2");
  await page.getByLabel("Y position (m)").fill("2");
  await page
    .getByRole("button", { name: "Start navigation", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await page.getByRole("button", { name: "Sensors", exact: true }).click();
  await expect(page.getByTestId("lidar-status")).toHaveText("READY");
  unavailable = true;
  await stream!.close({ code: 1001, reason: "Test sensor transport outage" });
  await expect(page.getByTestId("lidar-status")).toHaveText("DISCONNECTED");
  await expect(page.getByTestId("lidar-returns")).toHaveCount(0);
  await expect(page.getByText("Stream connected")).toBeVisible();
  const frame = await (await request.get("/api/robot/status")).json();
  expect(frame.navigation.status).toBe("running");
  unavailable = false;
  await expect(page.getByTestId("lidar-status")).toHaveText("READY", {
    timeout: 8000,
  });
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await page
    .getByRole("button", { name: "STOP · CANCEL ALL MOTION", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("idle");
});

test("malformed sensor frames produce a visible error and never draw measurements", async ({
  page,
  request,
}) => {
  const summary = await (await request.get("/api/sensors")).json();
  const lidar = await (await request.get("/api/sensors/lidar")).json();
  const camera = await (await request.get("/api/sensors/camera")).json();
  lidar.metadata.min_obstacle_distance = { invalid: "not a range" };
  await page.routeWebSocket("**/ws/sensors", (ws) => {
    ws.send(
      JSON.stringify({
        type: "sensors",
        simulation: true,
        session_id: summary.session_id,
        lidar,
        camera,
      }),
    );
  });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByRole("button", { name: "Sensors", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Invalid simulated sensor payload",
  );
  await expect(page.getByTestId("lidar-returns")).toHaveCount(0);
  await expect(page.getByTestId("camera-preview")).toContainText(
    "NOT CONNECTED",
  );
});

test("sensor page and map overlay are responsive on mobile", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeAttached();
  await page.getByRole("button", { name: "Sensors", exact: true }).click();
  await expect(page.getByTestId("lidar-status")).toHaveText("READY");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("sensor-center-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Navigation", exact: true }).click();
  await page.getByLabel("Show simulated LiDAR", { exact: true }).check();
  await expect(page.getByTestId("navigation-lidar-overlay")).toBeAttached();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
