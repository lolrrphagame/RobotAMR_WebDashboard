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
          manualChunks: { charts: ["recharts"], react: ["react", "react-dom"] },
        },
      },
    },
    plugins: [react(), tailwindcss()],
    server: { proxy },
    preview: { proxy },
  };
});
