import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// PHANTOM dev proxy — FastAPI runs on :8000.
// /api routes proxy as HTTP; /ws proxies as a real WebSocket so the native-WS
// client doesn't trip CORS or upgrade-handshake issues in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});
