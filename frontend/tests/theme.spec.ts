import { expect, test } from "@playwright/test";

test("System follows OS changes; explicit choices persist and synchronize Settings", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const root = page.locator("html");
  const themes = page.getByRole("group", {
    name: "Dashboard theme",
    exact: true,
  });
  await expect(
    themes.getByRole("radio", { name: "System theme" }),
  ).toBeChecked();
  await expect(root).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(root).toHaveAttribute("data-theme", "dark");
  await themes.getByRole("radio", { name: "Light theme" }).check();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(root).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const settings = page.getByRole("group", {
    name: "Settings theme",
    exact: true,
  });
  await expect(
    settings.getByRole("radio", { name: "Light theme" }),
  ).toBeChecked();
  await settings.getByRole("radio", { name: "Dark theme" }).check();
  await expect(themes.getByRole("radio", { name: "Dark theme" })).toBeChecked();
  await page.reload();
  await expect(root).toHaveAttribute("data-theme", "dark");
  expect(await page.evaluate(() => localStorage.getItem("pbl4-theme"))).toBe(
    "dark",
  );
  // Native radio keyboard navigation does not invoke the Manual Control Space STOP handler.
  await themes.getByRole("radio", { name: "Dark theme" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    themes.getByRole("radio", { name: "System theme" }),
  ).toBeChecked();
});

test("invalid or unavailable storage falls back safely; cross-tab preferences update", async ({
  browser,
}) => {
  const context = await browser.newContext({ colorScheme: "light" });
  const first = await context.newPage();
  await first.addInitScript(() =>
    localStorage.setItem("pbl4-theme", "invalid"),
  );
  await first.goto("/");
  await expect(first.locator("html")).toHaveAttribute(
    "data-theme-preference",
    "system",
  );
  const second = await context.newPage();
  await second.goto("/");
  await second.getByRole("radio", { name: "Dark theme" }).check();
  await expect(first.locator("html")).toHaveAttribute("data-theme", "dark");
  await context.close();

  const blocked = await browser.newContext({ colorScheme: "light" });
  const page = await blocked.newPage();
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new DOMException("Storage blocked", "SecurityError");
      },
    });
  });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("radio", { name: "Dark theme" }).check();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await blocked.close();
});

test("theme changes preserve the telemetry connection and send no robot commands", async ({
  page,
}) => {
  let sockets = 0;
  const commands: string[] = [];
  page.on("websocket", (ws) => {
    if (!ws.url().endsWith("/ws/telemetry")) return;
    sockets++;
    ws.on("framesent", ({ payload }) => {
      const frame = JSON.parse(String(payload));
      if (frame.type !== "heartbeat") commands.push(frame.type);
    });
  });
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeEnabled();
  await page.evaluate(
    () =>
      new Promise<void>((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
      ),
  );
  const previous = sockets;
  commands.length = 0;
  for (const name of ["Light", "Dark", "System", "Light"]) {
    await page.getByRole("radio", { name: `${name} theme` }).check();
  }
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  expect(sockets).toBe(previous);
  expect(commands).toEqual([]);
});

for (const theme of ["light", "dark"] as const) {
  test(`${theme}: every page fits desktop, laptop, tablet and mobile`, async ({
    page,
  }) => {
    await page.goto("/");
    await page
      .getByRole("radio", {
        name: `${theme === "light" ? "Light" : "Dark"} theme`,
      })
      .check();
    for (const size of [
      { width: 1440, height: 1000 },
      { width: 1280, height: 720 },
      { width: 768, height: 1024 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(size);
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
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        if (name === "Missions")
          await expect(page.locator(".missions-page")).toBeVisible();
        if (name === "Diagnostics")
          await expect(
            page.getByRole("tab", { name: "Motors", exact: true }),
          ).toBeVisible();
        if (name === "Settings")
          await expect(
            page.getByRole("heading", {
              name: "Theme preference",
              exact: true,
            }),
          ).toBeVisible();
        if (name === "Navigation")
          await expect(page.getByTestId("navigation-map")).toBeVisible();
        if (name === "Sensors")
          await expect(page.getByTestId("lidar-polar")).toBeVisible();
        if (name === "Overview")
          await expect(page.locator(".recharts-surface").first()).toBeVisible();
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          )
          .toBe(true);
      }
    }
  });
}

test("theme keyboard selection preserves a running navigation mission and STOP", async ({
  page,
}) => {
  await page.goto("/navigation");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByLabel("X position (m)").fill("2");
  await page.getByLabel("Y position (m)").fill("2");
  await page
    .getByRole("button", { name: "Start navigation", exact: true })
    .click();
  try {
    await expect(page.getByTestId("navigation-status")).toHaveText("running");
    for (const name of ["Light", "Dark"]) {
      const radio = page.getByRole("radio", { name: `${name} theme` });
      await radio.focus();
      await page.keyboard.press("Space");
      await expect(radio).toBeChecked();
      await expect(page.getByTestId("navigation-status")).toHaveText("running");
    }
  } finally {
    await page
      .getByRole("button", { name: "STOP · CANCEL ALL MOTION", exact: true })
      .click();
  }
  await expect(page.getByTestId("navigation-status")).toHaveText("idle");
});

test("semantic text and status pairs meet AA contrast; reduced motion is respected", async ({
  page,
}) => {
  await page.goto("/");
  for (const theme of ["Light", "Dark"]) {
    await page.getByRole("radio", { name: `${theme} theme` }).check();
    const ratios = await page.evaluate(() => {
      const styles = getComputedStyle(document.documentElement);
      const value = (name: string) =>
        styles.getPropertyValue(`--${name}`).trim();
      const luminance = (hex: string) => {
        const rgb = hex
          .slice(1)
          .match(/../g)!
          .slice(0, 3)
          .map((x) => parseInt(x, 16) / 255)
          .map((x) =>
            x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4,
          );
        return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
      };
      return [
        ["text-primary", "surface-panel"],
        ["text-secondary", "surface-app"],
        ["text-muted", "surface-panel"],
        ["text-subtle", "surface-inset"],
        ["text-subtle", "surface-raised"],
        ["accent-text", "accent-soft"],
        ["success", "success-soft"],
        ["warning", "warning-soft"],
        ["danger", "danger-soft"],
        ["danger", "danger-hover"],
        ["info", "info-soft"],
        ["violet", "violet-soft"],
        ["button-primary-text", "button-primary-bg"],
        ["chart-axis", "surface-panel"],
        ["text-inverse", "login-button"],
        ["text-inverse", "login-button-hover"],
      ].map(([fg, bg]) => {
        const a = luminance(value(fg)),
          b = luminance(value(bg));
        return {
          pair: `${fg}/${bg}`,
          ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
        };
      });
    });
    for (const { pair, ratio } of ratios)
      expect(ratio, `${theme} ${pair}`).toBeGreaterThanOrEqual(4.5);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page
      .getByRole("button", { name: "Overview", exact: true })
      .evaluate((el) => getComputedStyle(el).transitionDuration),
  ).toBe("1e-05s");
});
