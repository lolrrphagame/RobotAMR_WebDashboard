import { test, expect } from "@playwright/test";
import { writeFileSync } from "node:fs";

test("all pages remain responsive with bounded sockets and measured browser resources", async ({
  page,
}, testInfo) => {
  await page.addInitScript(() => {
    const sockets = new Set<WebSocket>();
    const NativeSocket = window.WebSocket;
    class TrackedSocket extends NativeSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        sockets.add(this);
        this.addEventListener("close", () => sockets.delete(this));
      }
    }
    window.WebSocket = TrackedSocket;
    Object.defineProperty(window, "phase5cSockets", {
      get: () =>
        [...sockets]
          .filter((s) => s.readyState === WebSocket.OPEN)
          .map((s) => s.url),
    });
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/overview");
  await expect(page.getByText("Stream connected")).toBeVisible();
  const pages = [
    "Overview",
    "Manual Control",
    "Navigation",
    "Missions",
    "Sensors",
    "Diagnostics",
    "Settings",
  ];
  const counts: { page: string; sockets: number }[] = [];
  const liveSockets = () =>
    page.evaluate(
      () => (window as unknown as { phase5cSockets: string[] }).phase5cSockets,
    );
  // Warm lazy modules and chart caches before comparing retained JS heap.
  for (const name of pages) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByText("Stream connected")).toBeVisible();
    await expect
      .poll(async () => (await liveSockets()).length)
      .toBe(name === "Sensors" || name === "Navigation" ? 2 : 1);
  }
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");
  const metrics = async () => {
    await cdp.send("HeapProfiler.collectGarbage");
    const result = await cdp.send("Performance.getMetrics");
    return Object.fromEntries(result.metrics.map((m) => [m.name, m.value]));
  };
  // Compare the same live Overview view on both sides, not Settings versus charts.
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Left motor response", exact: true }),
  ).toBeVisible();
  await expect.poll(async () => (await liveSockets()).length).toBe(1);
  const before = await metrics();
  const cycles = Number(process.env.PBL4_BROWSER_CYCLES ?? "3");
  if (!Number.isInteger(cycles) || cycles < 1 || cycles > 12)
    throw Error("PBL4_BROWSER_CYCLES must be an integer from 1 to 12");
  for (let cycle = 0; cycle < cycles; cycle++) {
    for (const name of pages) {
      await page.getByRole("button", { name, exact: true }).click();
      await expect
        .poll(async () => (await liveSockets()).length)
        .toBe(name === "Sensors" || name === "Navigation" ? 2 : 1);
      counts.push({ page: name, sockets: (await liveSockets()).length });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
  }
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  const chartFrames = await page.evaluate(async () => {
    const start = performance.now();
    let frames = 0;
    await new Promise<void>((resolve) => {
      const sample = () => {
        frames++;
        if (performance.now() - start < 3000) requestAnimationFrame(sample);
        else resolve();
      };
      requestAnimationFrame(sample);
    });
    return { frames, elapsedMs: performance.now() - start };
  });
  const after = await metrics();
  const report = {
    browser: page.context().browser()!.version(),
    viewport: page.viewportSize(),
    pageTransitions: counts.length,
    socketCounts: counts,
    jsHeapBeforeMiB: before.JSHeapUsedSize / 1024 ** 2,
    jsHeapAfterMiB: after.JSHeapUsedSize / 1024 ** 2,
    jsHeapGrowthMiB: (after.JSHeapUsedSize - before.JSHeapUsedSize) / 1024 ** 2,
    taskCpuSeconds: after.TaskDuration - before.TaskDuration,
    chartRafHz: (chartFrames.frames / chartFrames.elapsedMs) * 1000,
    note: "Headless Chromium laptop sample, forced GC before heap samples; not a long-run leak proof or mobile/Pi benchmark.",
  };
  writeFileSync(
    testInfo.outputPath("phase5c-browser.json"),
    JSON.stringify(report, null, 2),
  );
  await testInfo.attach("phase5c-browser", {
    body: JSON.stringify(report),
    contentType: "application/json",
  });
  expect(report.jsHeapGrowthMiB).toBeLessThan(32);
  expect(errors).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const name of pages) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByText("Stream connected")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("slow mission polls do not overlap and are aborted on page exit", async ({
  page,
}) => {
  let started = 0;
  let release: () => void = () => {};
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/missions", async (route) => {
    started++;
    await blocked;
    try {
      await route.continue();
    } catch {
      /* aborted when leaving the page */
    }
  });
  await page.goto("/missions");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect.poll(() => started).toBe(1);
  await page.waitForTimeout(2300);
  expect(started).toBe(1);
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  release();
  await expect(page.getByTestId("operating-mode")).toBeVisible();
});

test("failed mission poll aborts its pending sibling and can retry", async ({
  page,
}) => {
  let failed = true;
  let seenAbort = false;
  const requests = new Set<import("@playwright/test").Request>();
  let release: () => void = () => {};
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/missions")
      requests.add(request);
  });
  page.on("requestfailed", (request) => {
    if (requests.has(request)) seenAbort = true;
  });
  await page.route("**/api/missions", async (route) => {
    if (failed) await blocked;
    try {
      await route.continue();
    } catch {
      /* aborted sibling */
    }
  });
  await page.route("**/api/missions/history?**", async (route) => {
    if (failed) await route.abort();
    else await route.continue();
  });
  await page.goto("/missions");
  await expect(page.getByText("Stream connected")).toBeVisible();
  await expect.poll(() => seenAbort).toBe(true);
  failed = false;
  release();
  await expect(
    page.getByRole("heading", { name: "Mission builder", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("TypeError: Failed to fetch", { exact: true }),
  ).toHaveCount(0, { timeout: 5000 });
});
