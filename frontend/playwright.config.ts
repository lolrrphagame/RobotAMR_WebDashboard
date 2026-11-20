import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:15173", screenshot: "only-on-failure" },
  webServer: [
    {
      command:
        "cd ../backend && env -u PYTHONPATH ROBOT_CONFIG_PATH=:memory: ALLOWED_ORIGINS=http://127.0.0.1:15173 .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18000",
      url: "http://127.0.0.1:18000/api/health",
      reuseExistingServer: false,
    },
    {
      command:
        "VITE_PROXY_TARGET=http://127.0.0.1:18000 npm run dev -- --port 15173 --strictPort",
      url: "http://127.0.0.1:15173",
      reuseExistingServer: false,
    },
  ],
});
