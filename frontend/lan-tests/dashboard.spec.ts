import { test, expect } from "@playwright/test";

test("trusted HTTPS observer, operator login, WSS, STOP, refresh and logout", async ({ page }) => {
  const errors: string[] = [];
  const sockets: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.goto("/overview");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(page.getByText("Read-only observer", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Forward", exact: true })).toBeDisabled();
  // Browser fetch uses validated TLS and the actual session cookie policy.
  expect(await page.evaluate(async () => (await fetch("/api/missions", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  })).status)).toBe(401);
  await page.getByLabel("Operator password").fill("isolated-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Authorized operator", { exact: true })).toBeVisible();
  await expect(page.getByText("Stream connected")).toBeVisible();
  const forward = page.getByRole("button", { name: "Forward", exact: true });
  await expect(forward).toBeEnabled();
  await forward.focus();
  await page.keyboard.down("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("MANUAL");
  await page.getByRole("button", { name: "Stop simulated robot", exact: true }).click();
  await page.keyboard.up("Enter");
  await expect(page.getByTestId("operating-mode")).toHaveText("STANDBY");
  for (const path of ["/navigation", "/missions"]) {
    await page.goto(path);
    await expect(page.getByText("Stream connected")).toBeVisible();
    await page.reload();
    await expect(page.getByText("Authorized operator", { exact: true })).toBeVisible();
    await expect(page.getByText("Stream connected")).toBeVisible();
  }
  await page.goto("/sensors");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect.poll(() => sockets.some((url) => url.endsWith("/ws/sensors"))).toBe(true);
  expect(sockets.every((url) => url.startsWith("wss://127.0.0.1:18443/"))).toBe(true);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByText("Read-only observer", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("HTTPS mission owner disconnect pauses and reconnect never resumes", async ({ page }) => {
  await page.goto("/navigation");
  await page.getByLabel("Operator password").fill("isolated-browser-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Authorized operator", { exact: true })).toBeVisible();
  await expect(page.getByText("Stream connected")).toBeVisible();
  await page.getByLabel("X position (m)").fill("2");
  await page.getByLabel("Y position (m)").fill("2");
  await page.getByRole("button", { name: "Start navigation", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("running");
  await page.reload();
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(page.getByTestId("navigation-status")).toHaveText("paused");
  await page.getByRole("button", { name: "STOP · CANCEL ALL MOTION", exact: true }).click();
  await expect(page.getByTestId("navigation-status")).toHaveText("idle");
});
