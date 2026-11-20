import { defineConfig } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const data = mkdtempSync(join(tmpdir(), "pbl4-production-"));
process.env.PBL4_PRODUCTION_TEST_DATA = data;
export default defineConfig({
  testDir: "./production-tests",
  workers: 1,
  globalTeardown: "./production-tests/cleanup.ts",
  use: { baseURL: "http://127.0.0.1:18173", screenshot: "only-on-failure" },
  webServer: {
    command: "../start-dashboard.sh --no-build",
    url: "http://127.0.0.1:18173/api/health",
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15000 },
    env: {
      APP_MODE: "local",
      DASHBOARD_PORT: "18173",
      MISSION_DB_PATH: join(data, "missions.sqlite3"),
      ROBOT_CONFIG_PATH: join(data, "robot-config.json"),
    },
    timeout: 30000,
  },
});
