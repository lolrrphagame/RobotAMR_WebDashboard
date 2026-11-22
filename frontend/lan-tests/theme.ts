import { expect, type Page, type TestInfo } from "@playwright/test";

export async function verifyLoginThemes(page: Page, info: TestInfo) {
  for (const name of ["Light", "Dark"]) {
    await page.getByRole("radio", { name: `${name} theme` }).check();
    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      name.toLowerCase(),
    );
    for (const size of [
      { width: 1440, height: 1000 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(size);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: info.outputPath(`${name.toLowerCase()}-login-${size.width}.png`),
        fullPage: true,
      });
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}

export async function verifySessionThemes(
  page: Page,
  role: "operator" | "observer",
) {
  const sockets: string[] = [];
  const record = (ws: import("@playwright/test").WebSocket) =>
    sockets.push(ws.url());
  page.on("websocket", record);
  const cookies = await page.context().cookies();
  try {
    for (const name of ["Light", "Dark", "System"])
      await page.getByRole("radio", { name: `${name} theme` }).check();
    expect(await page.context().cookies()).toEqual(cookies);
    expect(sockets).toEqual([]);
    expect(await page.evaluate(() => Object.entries(localStorage))).toEqual([
      ["pbl4-theme", "system"],
    ]);
    const stop = page.getByRole("button", {
      name:
        role === "observer"
          ? "STOP · CANCEL ALL MOTION"
          : "Stop simulated robot",
      exact: true,
    });
    if (role === "observer") await expect(stop).toBeDisabled();
    else await expect(stop).toBeEnabled();
  } finally {
    page.off("websocket", record);
  }
}
