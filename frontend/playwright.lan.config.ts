import { defineConfig } from "@playwright/test";
import { mkdtempSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const existing = process.env.PBL4_LAN_TEST_DATA;
const data = existing ?? mkdtempSync(join(tmpdir(), "pbl4-lan-browser-"));
try {
  const env = { ...process.env };
  delete env.PYTHONPATH;
  if (!existing) execFileSync("../backend/.venv/bin/python", ["lan-tests/setup.py", data], { env });
} catch (error) {
  rmSync(data, { recursive: true, force: true });
  throw error;
}
process.env.PBL4_LAN_TEST_DATA = data;
// Node test workers verify HTTPS using the same temporary CA as Chromium.
process.env.NODE_EXTRA_CA_CERTS = join(data, "ca.crt");

export default defineConfig({
  testDir: "./lan-tests",
  workers: 1,
  globalTeardown: "./lan-tests/cleanup.ts",
  use: {
    baseURL: "https://127.0.0.1:18443",
    ignoreHTTPSErrors: false,
    screenshot: "only-on-failure",
    launchOptions: { env: { ...process.env, XDG_DATA_HOME: join(data, "browser-data") } },
  },
  webServer: {
    command: `../start-dashboard-lan.sh --config ${join(data, "lan.env")}`,
    // A TCP readiness check does not bypass client TLS verification.
    port: 18443,
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 25000 },
    timeout: 30000,
    env: { PBL4_LAN_TEST_DATA: data },
  },
});
