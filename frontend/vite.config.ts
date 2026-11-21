import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig(({ mode }) => {
  const target =
    loadEnv(mode, ".", "").VITE_PROXY_TARGET || "http://127.0.0.1:8000";
  const proxy = {
    "/api": target,
    "/ws": { target: target.replace(/^http/, "ws"), ws: true },
  };
  return {
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (
              /\/node_modules\/(react|react-dom|scheduler)\//.test(id) ||
              id.includes("commonjsHelpers")
            )
              return "react";
            if (id.includes("/node_modules/recharts/")) return "charts";
          },
        },
      },
    },
    plugins: [react(), tailwindcss()],
    server: { proxy },
    preview: { proxy },
  };
});
