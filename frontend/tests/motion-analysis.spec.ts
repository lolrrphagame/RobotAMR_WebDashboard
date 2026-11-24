import {
  expect,
  test,
  type Route,
  type WebSocketRoute,
} from "@playwright/test";
import type { HistoryRecord, Telemetry } from "../src/types";

const diagnosticsHistory = "**/api/diagnostics/history";

test("motion charts break at missing telemetry and reconnect with only the live backend session", async ({
  page,
  request,
}) => {
  const sockets: WebSocketRoute[] = [];
  const historyRequests: Route[] = [];
  await page.routeWebSocket("**/ws/telemetry", (socket) =>
    sockets.push(socket),
  );
  await page.route(diagnosticsHistory, (route) => {
    historyRequests.push(route);
  });
  const live = (await (
    await request.get("/api/robot/status")
  ).json()) as Telemetry;
  await page.goto("/diagnostics");
  await page.getByRole("tab", { name: "Motion Analysis" }).click();
  await expect(page.getByText("No valid samples in this window.")).toHaveCount(
    3,
  );
  await expect.poll(() => sockets.length).toBe(1);
  await expect.poll(() => historyRequests.length).toBe(1);

  const now = Date.now();
  const stamp = (offset: number) => new Date(now + offset).toISOString();
  const row = (
    offset: number,
    values: Partial<HistoryRecord> = {},
  ): HistoryRecord => ({
    timestamp: stamp(offset),
    session_id: "phase-5e2-a",
    requested_linear: 0.3,
    ...values,
  });
  const fixtureMotion = {
    ...live.diagnostics.motion,
    requested: { linear: 0.2, angular: 0.5 },
    limited: { linear: 0.05, angular: 0.4 },
    measured: { linear: 0.05, angular: 0.2 },
  };
  const fixture = {
    ...live,
    timestamp: stamp(0),
    session_id: "phase-5e2-a",
    linear_velocity: 0.05,
    angular_velocity: 0.2,
    diagnostics: { ...live.diagnostics, motion: fixtureMotion },
    motors: live.motors.map((motor) => ({ ...motor, tracking_error_rpm: 0 })),
  };
  sockets[0].send(JSON.stringify(fixture));
  await expect(
    page.getByText("1 retained samples in this window", { exact: true }),
  ).toBeVisible();
  await historyRequests[0].fulfill({
    json: {
      session_id: "phase-5e2-a",
      samples: [
        row(-20_000, { left_error_rpm: 7 }),
        row(-600, {
          limited_linear: 0.1,
          linear_velocity: 0.04,
          left_error_rpm: -3,
        }),
        row(-500, {
          limited_linear: 0.1,
          linear_velocity: 0.08,
          left_error_rpm: 4,
          right_error_rpm: -4,
        }),
        row(-400, { linear_velocity: 0.08 }),
        row(-100, {
          limited_linear: 0.08,
          linear_velocity: 0.08,
          left_error_rpm: 0,
          right_error_rpm: 8,
        }),
        row(0, { left_error_rpm: 33 }),
        row(-50, { session_id: "past-session", left_error_rpm: 56 }),
      ],
    },
  });
  const selector = page.getByLabel("History window");
  await expect(selector.locator("option")).toHaveText([
    "10 seconds",
    "30 seconds",
    "60 seconds",
  ]);
  await expect(
    page.getByText("6 retained samples in this window", { exact: true }),
  ).toBeVisible();
  await selector.selectOption("10");
  await expect(
    page.getByText("5 retained samples in this window", { exact: true }),
  ).toBeVisible();
  const statistics = (label: string) =>
    page.getByRole("row", { name: new RegExp(`^${label}`) }).getByRole("cell");
  await expect(statistics("Left wheel")).toHaveText([
    "4",
    "1.75",
    "2.50",
    "4.00",
  ]);
  await expect(statistics("Right wheel")).toHaveText([
    "3",
    "4.00",
    "5.16",
    "8.00",
  ]);
  await expect(statistics("Body linear velocity")).toHaveText([
    "4",
    "0.0200",
    "0.0316",
    "0.0600",
  ]);
  await expect(statistics("Body angular velocity")).toHaveText([
    "1",
    "0.2000",
    "0.2000",
    "0.2000",
  ]);
  const wheelChart = page.getByRole("region", {
    name: "Signed wheel tracking error",
  });
  await expect(
    wheelChart.locator(".recharts-reference-line-line"),
  ).toHaveAttribute("stroke", "var(--chart-axis)");
  await expect(wheelChart.getByText("0", { exact: true })).toBeVisible();
  await expect(
    wheelChart.locator("path.recharts-line-curve").first(),
  ).toHaveAttribute("d", /M.*M/);

  await sockets[0].close({ code: 1001, reason: "Simulated restart" });
  await expect(page.getByText(/Disconnected or stale stream/)).toBeVisible();
  await expect(statistics("Left wheel")).toHaveText([
    "4",
    "1.75",
    "2.50",
    "4.00",
  ]);
  await expect.poll(() => sockets.length).toBe(2);
  await expect.poll(() => historyRequests.length).toBe(2);
  sockets[1].send(
    JSON.stringify({
      ...fixture,
      session_id: "phase-5e2-b",
      timestamp: stamp(3000),
      motors: fixture.motors.map((motor, index) => ({
        ...motor,
        tracking_error_rpm: index === 0 ? 1 : null,
      })),
    }),
  );
  await expect(statistics("Left wheel")).toHaveText([
    "1",
    "1.00",
    "1.00",
    "1.00",
  ]);
  await historyRequests[1].fulfill({
    json: {
      session_id: "phase-5e2-a",
      samples: [row(3000, { left_error_rpm: 42 })],
    },
  });
  await expect(statistics("Left wheel")).toHaveText([
    "1",
    "1.00",
    "1.00",
    "1.00",
  ]);
  await expect(statistics("Right wheel")).toHaveText(["0", "Unavailable"]);
  await expect(
    page.getByText("1 retained samples in this window", { exact: true }),
  ).toBeVisible();
});

test("tuning changes only on save and real simulator traces fit both themes", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(45_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/settings");
  const settings = page.getByRole("region", {
    name: "Motion Control & Speed Limits",
  });
  const rpm = settings.getByLabel("Maximum wheel speed (RPM)", { exact: true });
  const acceleration = settings.getByLabel("Wheel acceleration (RPM/s)", {
    exact: true,
  });
  const wheelSlider = settings.getByRole("slider", {
    name: "Adjust maximum wheel speed",
  });
  const save = settings.getByRole("button", { name: "Save motion settings" });
  const restore = settings.getByRole("button", {
    name: "Restore Motion Defaults",
  });
  const theme = (name: string) =>
    page
      .getByRole("group", { name: "Dashboard theme" })
      .getByRole("radio", { name: `${name} theme` })
      .check();
  const open = (name: string) =>
    page.getByRole("button", { name, exact: true }).click();
  await expect(rpm).toHaveValue("40");
  await expect(acceleration).toHaveValue("60");
  await expect(save).toBeDisabled();
  const original = await (await request.get("/api/configuration")).json();
  await wheelSlider.fill("18");
  await acceleration.fill("12");
  await expect(rpm).toHaveValue("18");
  expect(
    (await (await request.get("/api/configuration")).json()).wheel_constraints,
  ).toEqual(original.wheel_constraints);
  await save.click();
  await expect(settings.getByRole("status")).toHaveText(
    "Motion settings saved.",
  );
  await expect(
    settings.getByRole("row", { name: "Autonomous linear speed" }),
  ).toContainText("0.082 m/s");
  await expect(
    settings.getByRole("row", { name: "Wheel speed" }),
  ).toContainText("18 RPM");
  await theme("Light");
  await settings.screenshot({
    path: testInfo.outputPath("phase5e2-settings-light.png"),
  });

  await open("Manual Control");
  await expect(
    page.getByText("18 RPM wheel limit · simulation only"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Forward", exact: true }).focus();
  await page.keyboard.down("Enter");
  await expect
    .poll(
      async () =>
        (await (await request.get("/api/robot/status")).json()).motors[0]
          .actual_rpm,
    )
    .toBeGreaterThan(6);
  await page.keyboard.up("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");

  await open("Navigation");
  const authority = page.getByTestId("control-authority");
  await expect(authority).toHaveText("STANDBY");
  await page.getByLabel("X position (m)").fill("2.4");
  await page.getByLabel("Y position (m)").fill("1.2");
  await open("Plan path");
  await expect(page.getByTestId("navigation-status")).toHaveText("ready");
  await expect(authority).toHaveText("STANDBY");
  await open("Start navigation");
  await expect(authority).toHaveText("AUTONOMOUS");
  await expect(
    page.getByText("Autonomous active — Simulation controller"),
  ).toBeVisible();
  const motion = page.getByRole("region", { name: "Navigation motion" });
  await expect(motion).toContainText("18 RPM");
  await expect(motion).toContainText("wheel RPM saturation");
  await expect(
    motion.getByRole("table", { name: "Body velocity" }),
  ).toHaveCount(1);
  await page.screenshot({
    path: testInfo.outputPath("phase5e2-navigation-light.png"),
    fullPage: true,
  });
  await open("Pause");
  await expect(
    page.getByText("Autonomous paused — Simulation controller"),
  ).toBeVisible();
  await expect(authority).toHaveText("AUTONOMOUS");
  await open("Cancel mission");
  await expect(authority).toHaveText("STANDBY");

  await open("Diagnostics");
  await page.getByRole("tab", { name: "Motion Analysis" }).click();
  await page.getByLabel("History window").selectOption("30");
  for (const name of ["Dark", "Light"]) {
    await theme(name);
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 900 });
      const linear = page.getByRole("region", { name: "Linear velocity" });
      const angular = page.getByRole("region", { name: "Angular velocity" });
      await expect(linear.locator("svg.recharts-surface")).toBeVisible();
      await expect(angular.locator("svg.recharts-surface")).toBeVisible();
      const first = (await linear.boundingBox())!;
      const second = (await angular.boundingBox())!;
      if (width === 1440)
        expect(second.x).toBeGreaterThan(first.x + first.width);
      else expect(second.y).toBeGreaterThan(first.y + first.height);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      if (
        (name === "Light" && width === 390) ||
        (name === "Dark" && width === 1440)
      ) {
        await page.screenshot({
          path: testInfo.outputPath(
            `phase5e2-analysis-${name.toLowerCase()}-${width}.png`,
          ),
          fullPage: true,
        });
      }
    }
  }
  await page.getByRole("tab", { name: "Motors", exact: true }).click();
  const integrations = page.getByRole("region", { name: "Integration status" });
  await expect(integrations).toContainText("Simulation");
  await expect(
    integrations.getByText("Not connected", { exact: true }),
  ).toHaveCount(3);
  await expect(
    page.getByRole("columnheader", { name: "Firmware control error" }),
  ).toBeVisible();

  await open("Settings");
  await restore.click();
  await expect(settings.getByRole("status")).toHaveText(
    "Motion defaults restored.",
  );
  await expect(rpm).toHaveValue("40");
  await expect(acceleration).toHaveValue("60");
  const restored = await (await request.get("/api/configuration")).json();
  expect(restored.home).toEqual(original.home);
  expect(restored.waypoints).toEqual(original.waypoints);
  expect(errors).toEqual([]);
});
