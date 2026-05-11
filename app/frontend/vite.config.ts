import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, "..", "..");

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    fs: { allow: [REPO_ROOT] }
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./tests/setup.ts"
  }
});
