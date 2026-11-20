import { test, expect } from "@playwright/test";
test("observer UI does not send control commands and login failure is visible", async ({
  page,
}) => {
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({ json: { role: "observer", csrf: "", mode: "lan" } }),
  );
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ status: 401, json: { detail: "Invalid credentials" } }),
  );
  await page.goto("/");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect(
    page.getByText("Read-only observer", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Forward", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Set Current Pose as Home", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Operator password").fill("wrong");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Authentication failed");
});
