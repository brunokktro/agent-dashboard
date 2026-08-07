import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // dev mode: the FastAPI backend runs on 7780
      "/api": "http://localhost:7780",
      "/ws": { target: "ws://localhost:7780", ws: true },
    },
  },
})
