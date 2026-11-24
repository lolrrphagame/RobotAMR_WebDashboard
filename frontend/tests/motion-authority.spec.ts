import { expect, test } from "@playwright/test";

test("stationary Operator saves caps, retains manual speeds and can STOP a paused mission", async ({
  page,
}) => {
  await page.goto("/settings");
  const section = page.getByRole("region", {
    name: "Motion Control & Speed Limits",
  });
  const authority = section.getByTestId("settings-motion-authority");
  const linearCap = section.getByLabel("Maximum linear speed (m/s)");
  const angularCap = section.getByLabel("Maximum angular speed (rad/s)");
  const save = section.getByRole("button", { name: "Save motion settings" });
  const open = (name: string) =>
    page.getByRole("button", { name, exact: true }).click();
  const navigation = page.getByTestId("navigation-status");
  const operatingMode = page.getByTestId("operating-mode");

  await expect(authority).toHaveText("STANDBY");
  await expect(linearCap).toHaveValue("0.13");
  await expect(angularCap).toHaveValue("0.8");
  await expect(save).toBeDisabled();
  await linearCap.fill("0.19");
  await save.click();
  expect(
    await linearCap.evaluate(
      (input: HTMLInputElement) => input.validity.rangeOverflow,
    ),
  ).toBe(true);
  await linearCap.fill("0.04");
  await angularCap.fill("0.2");
  await save.click();
  await expect(section.getByRole("status")).toHaveText(
    "Motion settings saved.",
  );
  await page.reload();
  await expect(linearCap).toHaveValue("0.04");
  await expect(angularCap).toHaveValue("0.2");

  await open("Manual Control");
  const manualLinear = page.getByLabel("Linear speed", { exact: false });
  const manualAngular = page.getByLabel("Angular speed", { exact: false });
  await manualLinear.fill("0.15");
  await manualAngular.fill("0.9");
  for (const [direction, expected] of [
    ["Forward", { linear: 0.15, angular: 0 }],
    ["Rotate left", { linear: 0, angular: 0.9 }],
  ] as const) {
    await page.getByRole("button", { name: direction, exact: true }).focus();
    await page.keyboard.down("Enter");
    await expect(operatingMode).toHaveText("MANUAL");
    await expect
      .poll(async () => {
        const frame = await (
          await page.request.get("/api/robot/status")
        ).json();
        return frame.diagnostics.motion.requested;
      })
      .toEqual(expected);
    await page.keyboard.up("Enter");
    await expect(operatingMode).toHaveText("STANDBY");
  }

  await open("Navigation");
  await page.getByLabel("X position (m)").fill("2");
  await page.getByLabel("Y position (m)").fill("1.2");
  await open("Plan path");
  await expect(navigation).toHaveText("ready");
  await open("Settings");
  await expect(authority).toHaveText("STANDBY");
  await expect(linearCap).toBeEnabled();
  await open("Navigation");
  await open("Start navigation");
  await expect(navigation).toHaveText("running");
  await open("Pause");
  await expect(navigation).toHaveText("paused");
  await open("Settings");
  await expect(authority).toHaveText("AUTONOMOUS");
  await expect(linearCap).toBeDisabled();
  await expect(save).toBeDisabled();
  await expect(section.getByText(/running or paused mission/)).toBeVisible();
  await open("Navigation");
  await open("Resume");
  await expect(navigation).toHaveText("running");
  await open("Pause");
  await expect(navigation).toHaveText("paused");
  await open("Manual Control");
  await expect(operatingMode).toHaveText("AUTONOMOUS");
  await expect(page.getByText(/Manual driving is locked/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeDisabled();
  await expect(manualLinear).toBeDisabled();
  await expect(manualAngular).toBeDisabled();
  await open("Stop simulated robot");
  await expect(operatingMode).toHaveText("STANDBY");
  await open("Settings");
  await expect(linearCap).toBeEnabled();
  await linearCap.fill("0.13");
  await angularCap.fill("0.8");
  await save.click();
  await expect(section.getByRole("status")).toHaveText(
    "Motion settings saved.",
  );
});

test("motion settings fit both themes and show save conflicts inline", async ({
  page,
}) => {
  await page.goto("/settings");
  const section = page.getByRole("region", {
    name: "Motion Control & Speed Limits",
  });
  const linear = section.getByLabel("Maximum linear speed (m/s)");
  const angular = section.getByLabel("Maximum angular speed (rad/s)");
  await expect(linear).toBeEnabled();
  for (const theme of ["Light", "Dark"]) {
    await page
      .getByRole("group", { name: "Settings theme" })
      .getByRole("radio", { name: `${theme} theme` })
      .check();
    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      theme.toLowerCase(),
    );
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      const first = await linear.boundingBox();
      const second = await angular.boundingBox();
      expect(first && second).toBeTruthy();
      if (width === 390)
        expect(second!.y).toBeGreaterThan(first!.y + first!.height);
      else expect(second!.x).toBeGreaterThan(first!.x + first!.width);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.route("**/api/configuration", (route) =>
    route.fulfill({
      status: 409,
      json: {
        detail:
          "Autonomous speed limits cannot change during a running or paused mission.",
      },
    }),
  );
  await linear.fill("0.07");
  await section.getByRole("button", { name: "Save motion settings" }).click();
  await expect(section.getByRole("alert")).toHaveText(
    /cannot change during a running or paused mission/,
  );
  await expect(linear).toHaveValue("0.07");
});

test("Navigation reports manual ownership and running or paused WAIT reservations", async ({
  page,
  request,
}) => {
  const open = (name: string) =>
    page.getByRole("button", { name, exact: true }).click();
  await page.goto("/navigation");
  const authority = page.getByTestId("control-authority");
  await expect(authority).toHaveText("STANDBY");
  const manual = await page.evaluateHandle(async () => {
    const socket = new WebSocket(`ws://${location.host}/ws/telemetry`);
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => resolve();
      socket.onerror = () => reject(new Error("Test operator socket failed"));
    });
    const drive = () =>
      socket.send(JSON.stringify({ type: "control", angular: 0.2 }));
    drive();
    const timer = window.setInterval(drive, 150);
    return { socket, timer };
  });
  try {
    await expect(authority).toHaveText("MANUAL");
    await expect(
      page.getByRole("button", { name: "Plan path" }),
    ).toBeDisabled();
  } finally {
    await manual.evaluate(({ socket, timer }) => {
      window.clearInterval(timer);
      socket.send(JSON.stringify({ type: "release" }));
      socket.close();
    });
    await manual.dispose();
  }
  await expect(authority).toHaveText("STANDBY");
  const queued = await request.post("/api/missions", {
    data: {
      name: "Authority WAIT test",
      steps: [{ kind: "wait", seconds: 25 }],
    },
  });
  expect(queued.ok()).toBe(true);
  await open("Missions");
  await open("Start next mission");
  await open("Navigation");
  const reservation = page.getByText(
    "Mission Operations reservation · WAIT step",
    { exact: true },
  );
  await expect(authority).toHaveText("AUTONOMOUS");
  await expect(reservation).toBeVisible();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await open("Pause");
  await expect(page.getByTestId("navigation-status")).toHaveText("paused");
  await expect(
    page.getByText("Autonomous paused — Simulation controller"),
  ).toBeVisible();
  await expect(reservation).toBeVisible();
  await open("Settings");
  const settings = page.getByRole("region", {
    name: "Motion Control & Speed Limits",
  });
  await expect(
    settings.getByRole("slider", { name: "Adjust maximum wheel speed" }),
  ).toBeDisabled();
  await expect(
    settings.getByRole("button", { name: "Restore Motion Defaults" }),
  ).toBeDisabled();
  await expect(
    settings.getByText(/including a running or paused mission or a WAIT step/),
  ).toBeVisible();
  await open("Navigation");
  await open("Resume");
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await expect(reservation).toBeVisible();
  await open("Cancel mission");
  await expect(authority).toHaveText("STANDBY");
  await expect(reservation).toHaveCount(0);
});
