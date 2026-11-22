import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { verifyLoginThemes, verifySessionThemes } from "./theme";
async function signIn(page: Page, role = "operator") {
  await page.getByLabel("Username", { exact: true }).fill(role);
  await page
    .getByLabel("Password", { exact: true })
    .fill(
      role === "operator"
        ? "isolated-browser-password"
        : "isolated-observer-password",
    );
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(
    page.getByText(
      role === "operator" ? "Authorized operator" : "Read-only observer",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.getByText("Stream connected")).toBeVisible();
}

test("anonymous sees only login; authenticated Observer monitors without controls", async ({
  page,
}, testInfo) => {
  const sockets: string[] = [];
  const chartRequests: string[] = [];
  page.on("websocket", (socket) => sockets.push(socket.url()));
  page.on("request", (request) => {
    if (/\/assets\/(charts-|RpmChart-)/.test(request.url()))
      chartRequests.push(request.url());
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/navigation");
  await expect(
    page.getByRole("heading", { name: "Sign in to your workspace" }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  expect(sockets).toEqual([]);
  expect(chartRequests).toEqual([]);
  expect(
    await page.evaluate(async () => (await fetch("/api/map")).status),
  ).toBe(401);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("login-mobile.png") });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const bounds = await page.locator(".login-shell").boundingBox();
  expect(bounds?.x).toBe(0);
  expect(bounds?.width).toBe(1440);
  await page.screenshot({ path: testInfo.outputPath("login-desktop.png") });
  await verifyLoginThemes(page, testInfo);
  await signIn(page, "observer");
  await verifySessionThemes(page, "observer");
  await expect(page.getByTestId("navigation-map")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "STOP · CANCEL ALL MOTION", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Stop simulated robot", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Set Current Pose as Home", exact: true }),
  ).toBeDisabled();
  expect(
    await page.evaluate(
      async () =>
        (
          await fetch("/api/missions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          })
        ).status,
    ),
  ).toBe(403);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(async () => (await fetch("/api/robot/status")).status),
  ).toBe(401);
  await page.reload();
  await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
});

test("trusted HTTPS operator login, WSS, STOP, refresh and logout", async ({
  page,
}) => {
  const errors: string[] = [];
  const sockets: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.goto("/overview");
  await signIn(page);
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeEnabled();
  await verifySessionThemes(page, "operator");
  const forward = page.getByRole("button", { name: "Forward", exact: true });
  await expect(forward).toBeEnabled();
  await forward.focus();
  await page.keyboard.down("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("MANUAL");
  await page
    .getByRole("button", { name: "Stop simulated robot", exact: true })
    .click();
  await page.keyboard.up("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  for (const path of ["/navigation", "/missions"]) {
    await page.goto(path);
    await expect(page.getByText("Stream connected")).toBeVisible();
    await page.reload();
    await expect(
      page.getByText("Authorized operator", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Stream connected")).toBeVisible();
  }
  await page.goto("/sensors");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect
    .poll(() => sockets.some((url) => url.endsWith("/ws/sensors")))
    .toBe(true);
  expect(sockets.every((url) => url.startsWith("wss://127.0.0.1:18443/"))).toBe(
    true,
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("HTTPS owner refresh pauses and reconnect never resumes", async ({
  page,
}) => {
  await page.goto("/navigation");
  await signIn(page);
  await page.getByLabel("X position (m)").fill("2");
  await page.getByLabel("Y position (m)").fill("2");
  await page
    .getByRole("button", { name: "Start navigation", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await page.reload();
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(page.getByTestId("navigation-status")).toHaveText("paused");
  await page
    .getByRole("button", { name: "STOP · CANCEL ALL MOTION", exact: true })
    .click();
  await expect(page.getByTestId("navigation-status")).toHaveText("idle");
});

test("disabling an Observer closes streams and clears every private view", async ({
  page,
}) => {
  await page.goto("/sensors");
  await signIn(page, "observer");
  const store = join(process.env.PBL4_LAN_TEST_DATA!, "accounts.json");
  const env = { ...process.env };
  delete env.PYTHONPATH;
  const update = (action: string) =>
    execFileSync(
      "../backend/.venv/bin/python",
      ["-m", "app.accounts", "--store", store, action, "observer"],
      { cwd: "../backend", env },
    );
  try {
    update("disable");
    await expect(page.getByLabel("Username", { exact: true })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Main navigation" }),
    ).toHaveCount(0);
    expect(
      await page.evaluate(async () => (await fetch("/api/sensors")).status),
    ).toBe(401);
  } finally {
    update("enable");
  }
});
