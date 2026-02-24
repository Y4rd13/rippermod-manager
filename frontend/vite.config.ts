import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { execSync } from "child_process";
import { resolve } from "path";
import { defineConfig } from "vite";

function getGitVersion(): string {
  try {
    return execSync("git describe --tags --always", { encoding: "utf-8" }).trim();
  } catch {
    return "dev";
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(getGitVersion()),
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  server: {
    port: 1420,
    strictPort: true,
  },
  envPrefix: ["VITE_"],
});
