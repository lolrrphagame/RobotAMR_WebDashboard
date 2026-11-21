import { test, expect } from "@playwright/test";
test("authenticated observer UI disables controls and settings", async ({
  page,
}) => {
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      json: {
        authenticated: true,
        username: "viewer",
        role: "observer",
        csrf: "",
        mode: "lan",
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(
    page.getByText("Read-only observer", { exact: true }),
  ).toBeVisible();
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
});
test("anonymous login never mounts dashboard and invalid credentials are visible", async ({
  page,
}) => {
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      json: {
        authenticated: false,
        username: null,
        role: null,
        csrf: "",
        mode: "lan",
      },
    }),
  );
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ status: 401, json: { detail: "Invalid credentials" } }),
  );
  const sockets: string[] = [];
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.goto("/navigation");
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  await page.getByLabel("Username", { exact: true }).fill("unknown");
  await page.getByLabel("Password", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Sign In", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Invalid username or password",
  );
  expect(sockets.filter((url) => url.includes("/ws/"))).toEqual([]);
});
